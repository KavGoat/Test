"""What comes out of the printer.

A calculation sheet that looks right on screen and prints wrong is worse than
useless, so these tests read the produced PDF back and check the geometry, the
page count and the actual text on the page.
"""
import pytest
from PySide6.QtPdf import QPdfDocument

from markforge.core.document import LANDSCAPE
from markforge.io import export as export_io

A4_W, A4_H = 595.276, 841.89          # points, ISO 216
TOLERANCE = 1.5                       # Qt rounds the media box to 1/20 pt


class Printed:
    """A produced PDF, read back with Qt's own reader."""

    def __init__(self, path: str):
        self.path = path
        self.document = QPdfDocument()
        assert self.document.load(path) == QPdfDocument.Error.None_, \
            f"{path} is not a readable PDF"

    @property
    def pages(self) -> int:
        return self.document.pageCount()

    def size(self, index: int = 0):
        size = self.document.pagePointSize(index)
        return size.width(), size.height()

    def text(self) -> str:
        """Every word a reader shows, wherever the file happens to keep it.

        An exported markup is a real annotation with its own appearance, so
        what it says is not in the page's own content stream. Qt's reader only
        gives back the page, so the annotations are read as well and added to
        it: between them they are what somebody opening the file actually sees.
        """
        return "\n".join([self.document.getAllText(i).text()
                           for i in range(self.pages)] + self.markup_text())

    def markup_text(self) -> list[str]:
        """What each markup on each page says, out of its appearance."""
        from pypdf import PdfReader
        from pypdf._page import PageObject
        from pypdf.generic import NameObject

        said = []
        reader = PdfReader(self.path, strict=False)
        for page in reader.pages:
            for annotation in self.annotations(page):
                look = annotation.get("/AP")
                if not look or "/N" not in look:
                    continue
                form = look["/N"]
                form = form.get_object() if hasattr(form, "get_object") else form
                reading = PageObject.create_blank_page(pdf=reader, width=1, height=1)
                reading[NameObject("/Contents")] = form
                if "/Resources" in form:
                    reading[NameObject("/Resources")] = form["/Resources"]
                said.append(reading.extract_text())
        return said

    @staticmethod
    def annotations(page) -> list:
        found = page.get("/Annots")
        if found is None:
            return []
        return [entry.get_object() for entry in found.get_object()]

    def markups(self, index: int = 0) -> list:
        """The annotations on one page — what a reader lets somebody move."""
        from pypdf import PdfReader

        reader = PdfReader(self.path, strict=False)
        return self.annotations(reader.pages[index])


def _pdf(document, tmp_path, name="out.pdf") -> Printed:
    path = str(tmp_path / name)
    export_io.export_pdf(document, path)
    return Printed(path)


def test_a_new_document_prints_one_a4_page(window, tmp_path):
    printed = _pdf(window.document, tmp_path)
    assert printed.pages == 1
    width, height = printed.size()
    assert width == pytest.approx(A4_W, abs=TOLERANCE)
    assert height == pytest.approx(A4_H, abs=TOLERANCE)


def test_every_page_of_the_document_is_printed(window, tmp_path):
    window.add_page()
    window.add_page()
    assert _pdf(window.document, tmp_path).pages == 3


def test_a_landscape_a3_page_prints_at_a3(window, tmp_path):
    page = window.current_page()
    page.setup.apply_size("A3")
    page.setup.orientation = LANDSCAPE
    width, height = _pdf(window.document, tmp_path).size()
    assert width == pytest.approx(1190.55, abs=2.0)
    assert height == pytest.approx(841.89, abs=2.0)


def test_pages_of_different_sizes_keep_their_own_size(window, tmp_path):
    window.add_page()
    window.document.pages[1].setup.apply_size("A3")
    printed = _pdf(window.document, tmp_path)
    assert printed.size(0)[0] == pytest.approx(A4_W, abs=TOLERANCE)
    assert printed.size(1)[0] == pytest.approx(841.89, abs=2.0)


def test_a_page_range_prints_only_those_pages(window, tmp_path):
    window.add_page()
    window.add_page()
    path = str(tmp_path / "range.pdf")
    export_io.export_pdf(window.document, path, pages=window.document.pages[1:])
    assert Printed(path).pages == 2


def test_markup_text_reaches_the_page(window, tmp_path):
    window.select_tool("text")
    _drag(window, 100, 100, 340, 150)
    box = window.view.editing_item()
    box.set_text("CHECK PUNCHING SHEAR")
    window.view.end_item_edit()
    assert "PUNCHING" in _pdf(window.document, tmp_path).text()


def test_a_measurement_prints_the_dimension_it_reads(window, tmp_path):
    from markforge.core.document import PageScale
    window.current_page().scale = PageScale.from_ratio(50)
    window.select_tool("measure_length")
    _drag(window, 100, 400, 236, 400)
    window.view.end_item_edit()
    assert "2.4" in _pdf(window.document, tmp_path).text()


def test_the_print_path_survives_a_second_run(window, tmp_path):
    """QPrinter refuses layout changes mid-job; this is the crash that found."""
    from PySide6.QtPrintSupport import QPrinter
    window.add_page()
    window.document.pages[1].setup.apply_size("A3")
    window.document.pages[1].setup.orientation = LANDSCAPE
    for attempt in range(2):
        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(str(tmp_path / f"printed_{attempt}.pdf"))
        export_io.print_document(window.document, printer)
        assert Printed(str(tmp_path / f"printed_{attempt}.pdf")).pages == 2


# -- helper ------------------------------------------------------------------

def _drag(window, x0, y0, x1, y1):
    from tests.test_usability import drag
    drag(window.view, x0, y0, x1, y1)


# ---------------------------------------------------------------------------
# Running headers, footers and a logo
# ---------------------------------------------------------------------------

def _logo(document, width=120, height=60, colour=0xFFDD2222) -> str:
    """Put a solid-colour logo in the document and return its asset key."""
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QImage

    image = QImage(width, height, QImage.Format_ARGB32)
    image.fill(colour)
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return document.add_asset(bytes(buffer.data()), "png")


def _counts(image, colour=(0xDD, 0x22, 0x22)) -> int:
    from PySide6.QtGui import qBlue, qGreen, qRed
    found = 0
    for y in range(0, image.height(), 2):
        for x in range(0, image.width(), 2):
            pixel = image.pixel(x, y)
            if (abs(qRed(pixel) - colour[0]) < 24 and abs(qGreen(pixel) - colour[1]) < 24
                    and abs(qBlue(pixel) - colour[2]) < 24):
                found += 1
    return found


def test_the_page_number_and_date_reach_the_paper(window, tmp_path):
    from datetime import datetime

    window.document.title = "Beam checks"
    window.document.settings.show_footer = True
    window.document.settings.footer_left = "{title}"
    window.document.settings.footer_right = "Page {page} of {pages} · {date}"
    window.add_page()

    text = _pdf(window.document, tmp_path).text()
    assert "Beam checks" in text
    assert "Page 1 of 2" in text and "Page 2 of 2" in text
    assert datetime.now().strftime("%Y-%m-%d") in text


def test_a_logo_is_printed_in_the_slot_it_was_put_in(window):
    settings = window.document.settings
    settings.logo_key = _logo(window.document)
    settings.logo_slot = "header_left"
    settings.show_header = True
    settings.header_right = "S1"

    frame = window.document.pages[0].frame
    image = frame.render_image(dpi=96.0)
    assert _counts(image) > 20                       # the logo is on the page

    left_half = _counts(image.copy(0, 0, image.width() // 2, image.height()))
    right_half = _counts(image.copy(image.width() // 2, 0,
                                    image.width() // 2, image.height()))
    assert left_half > 20 and right_half == 0        # …on the left, where asked


def test_a_logo_in_the_footer_prints_at_the_bottom(window):
    settings = window.document.settings
    settings.logo_key = _logo(window.document)
    settings.logo_slot = "footer_right"
    settings.show_footer = True

    image = window.document.pages[0].frame.render_image(dpi=96.0)
    top = _counts(image.copy(0, 0, image.width(), image.height() // 2))
    bottom = _counts(image.copy(0, image.height() // 2,
                                image.width(), image.height() // 2))
    assert bottom > 20 and top == 0


def test_the_logo_height_is_what_was_asked_for(window):
    from markforge.core.document import MM_TO_PT

    settings = window.document.settings
    settings.logo_key = _logo(window.document)
    settings.logo_slot = "header_left"
    settings.show_header = True
    frame = window.document.pages[0].frame

    small = settings.logo_height_mm = 8.0
    frame.load_logo()
    band = frame._band(_header_box(frame), "header", 42.0)
    rect = frame._logo_rect(band, "header_left")
    assert rect.height() == pytest.approx(small * MM_TO_PT, abs=0.5)
    assert rect.width() == pytest.approx(rect.height() * 2, abs=1.0)   # 120×60


def test_a_logo_never_spills_past_the_margin(window):
    settings = window.document.settings
    settings.logo_key = _logo(window.document)
    settings.logo_slot = "header_left"
    settings.logo_height_mm = 60.0            # taller than the margin
    settings.show_header = True
    frame = window.document.pages[0].frame
    margin = frame.page.setup.content_rect_pt[1]
    band = frame._band(_header_box(frame), "header", margin)
    assert band.height() <= margin
    assert band.top() >= 0
    assert frame._logo_rect(band, "header_left").height() <= band.height()


def _header_box(frame):
    from PySide6.QtCore import QRectF
    left, top, width, _height = frame.page.setup.content_rect_pt
    return QRectF(left, top - 18, width, 14)


def test_header_text_steps_aside_for_the_logo(window):
    frame = window.document.pages[0].frame
    settings = window.document.settings
    settings.show_header = True
    settings.logo_key = _logo(window.document)
    settings.logo_slot = "header_left"
    box = _header_box(frame)
    band = frame._band(box, "header", 42.5)
    rect = frame._logo_rect(band, "header_left")
    assert rect.width() > 0
    # the same slot as the logo starts after it; the other side is untouched
    assert band.left() + rect.width() <= band.adjusted(rect.width() + 4, 0, 0, 0).left()


def test_the_logo_and_its_place_are_saved_with_the_document(window, tmp_path):
    from markforge.core.document import Document
    from markforge.io import project as project_io

    settings = window.document.settings
    settings.logo_key = _logo(window.document)
    settings.logo_slot = "footer_center"
    settings.logo_height_mm = 12.5
    path = str(tmp_path / "logo.pdf")
    project_io.save_document(window.document, path)

    reopened = Document()
    project_io.load_document(reopened, path)
    assert reopened.settings.logo_slot == "footer_center"
    assert reopened.settings.logo_height_mm == pytest.approx(12.5)
    assert reopened.asset(reopened.settings.logo_key)


# ---------------------------------------------------------------------------
# Bookmarks, a contents block, and links that work in the exported PDF
# ---------------------------------------------------------------------------

def _outline_titles(path: str) -> list[str]:
    """The bookmark names in a PDF, as a reader would see them.

    Read through the outline itself rather than by hunting the bytes for one
    particular spelling of ``/Title``: how a writer spaces and encodes a string
    is its own business, and a test that depends on it is testing the writer
    rather than the bookmark.
    """
    import pymupdf

    document = pymupdf.open(path)
    try:
        return [title for _level, title, _page in document.get_toc(simple=True)]
    finally:
        document.close()


def _link_count(path: str) -> int:
    import pymupdf

    document = pymupdf.open(path)
    try:
        return sum(len(page.get_links()) for page in document)
    finally:
        document.close()


def _a_pdf_with_an_index(path: str) -> None:
    """Three sheets, an outline over them, and a link from one to another."""
    import pymupdf

    document = pymupdf.open()
    for number in range(3):
        page = document.new_page(width=595, height=842)
        page.insert_text(pymupdf.Point(70, 120), f"SHEET {number + 1}", fontsize=14)
    document.set_toc([[1, "Cover", 1], [2, "Plan", 2], [1, "Details", 3]])
    document[0].insert_link({"kind": pymupdf.LINK_GOTO,
                             "from": pymupdf.Rect(50, 50, 200, 80),
                             "page": 2, "to": pymupdf.Point(0, 700)})
    document.save(path)
    document.close()


def test_an_exported_drawing_keeps_the_index_and_links_it_came_with(
        window, tmp_path):
    """A drawing set's outline is its sheet index; its links are how you move.

    Exporting places each source page onto the sheet it goes out as, and
    placing a page draws it — it does not bring the outline that pointed at it
    or the links that were on it. Both have to be carried over deliberately, or
    a two-hundred-page set comes out of the export with no way round it.
    """
    from markforge.io import pdfio

    source = str(tmp_path / "set.pdf")
    _a_pdf_with_an_index(source)
    window.open_path(source)
    window.rebuild_scenes()

    path = str(tmp_path / "exported.pdf")
    export_io.export_pdf(window.document, path, resolution=150)

    assert _outline_titles(path) == ["Cover", "Plan", "Details"]
    assert _link_count(path) == 1
    assert pdfio.page_count(path) == 3


def test_a_bookmark_added_to_a_drawing_set_joins_its_index(window, tmp_path):
    """The index it came with is the document's index now, so this adds to it.

    There is one list of bookmarks and everything reads from it — the panel,
    a contents block, the exported outline — so a bookmark added to an opened
    drawing set takes its place in that list rather than replacing it or
    living somewhere parallel to it.
    """
    source = str(tmp_path / "set.pdf")
    _a_pdf_with_an_index(source)
    window.open_path(source)
    window.rebuild_scenes()
    window.document.add_bookmark("My own note", 0, 400.0)

    path = str(tmp_path / "exported.pdf")
    export_io.export_pdf(window.document, path, resolution=150)

    # In page order, and down the page within a page: the added one sits after
    # "Cover" because it points further down the same sheet.
    assert _outline_titles(path) == ["Cover", "My own note", "Plan", "Details"]
    assert _link_count(path) == 1, "and the links it came with are still there"


def test_a_bookmark_lands_where_on_the_page_it_points(window, tmp_path):
    """Near the top of the sheet means near the top of the sheet.

    A ``/XYZ`` destination is written measuring up from the bottom of the page
    and everything here measures down from the top, so somewhere the two have
    to be reconciled — and doing it twice is the same as not doing it at all,
    except that it looks right until somebody clicks the bookmark and lands at
    the wrong end of a title sheet.
    """
    import pymupdf

    height = window.document.pages[0].height_pt
    window.document.add_bookmark("Near the top", 0, 100.0)
    path = str(tmp_path / "bookmarked.pdf")
    export_io.export_pdf(window.document, path, resolution=150)

    document = pymupdf.open(path)
    try:
        entry = document.get_toc(simple=False)[0]
        landed = entry[3]["to"].y
        assert abs(landed - 100.0) < 2, \
            f"asked for 100pt down a {height:.0f}pt page, landed at {landed:.0f}"
    finally:
        document.close()


def test_a_document_without_bookmarks_is_unchanged(window, tmp_path):
    path = str(tmp_path / "plain.pdf")
    export_io.export_pdf(window.document, path)
    assert _outline_titles(path) == []
    assert Printed(path).pages == 1


def _null_painter(window):
    """A painter over a throwaway image, for laying a block out off-screen."""
    from PySide6.QtGui import QImage, QPainter

    image = QImage(600, 800, QImage.Format_ARGB32)
    painter = QPainter(image)
    window._contents_painter = (image, painter)         # keep them alive
    return painter


def test_every_markup_goes_out_as_a_markup(window, tmp_path):
    """Opened elsewhere, each one is still an annotation to pick up and move."""
    window.select_tool("rect")
    _drag(window, 100, 100, 260, 200)
    window.select_tool("ellipse")
    _drag(window, 300, 100, 420, 200)
    window.select_tool("polyline")
    _drag(window, 100, 300, 300, 380)

    printed = _pdf(window.document, tmp_path, "live.pdf")
    kinds = [str(mark["/Subtype"]) for mark in printed.markups()]
    assert sorted(kinds) == ["/Circle", "/PolyLine", "/Square"]
    for mark in printed.markups():
        assert "/AP" in mark, "a markup with no appearance would show as nothing"
        assert "/Rect" in mark


def test_an_exported_markup_is_not_also_painted_into_the_sheet(window, tmp_path):
    """Painted as well as placed, it would leave a ghost the moment it moved."""
    window.select_tool("rect")
    _drag(window, 100, 100, 260, 200)
    box = window.document.pages[0].frame.ordered_markups()[0]
    box.style.stroke = "#2f9e44"

    from PySide6.QtCore import QSize
    from PySide6.QtPdf import QPdfDocumentRenderOptions

    printed = _pdf(window.document, tmp_path, "ghost.pdf")

    def greens(with_markups: bool) -> int:
        options = QPdfDocumentRenderOptions()
        if with_markups:
            options.setRenderFlags(QPdfDocumentRenderOptions.RenderFlag.Annotations)
        image = printed.document.render(0, QSize(595, 842), options)
        return sum(1 for y in range(image.height()) for x in range(image.width())
                   if image.pixelColor(x, y).green() > 110
                   and image.pixelColor(x, y).red() < 120
                   and image.pixelColor(x, y).alpha() > 0)

    assert greens(True) > 100, "the rectangle should be there as an annotation"
    # A handful of stray pixels come off the antialiased page furniture, so
    # what is being asked is whether the rectangle is in the sheet, and a
    # rectangle is hundreds of pixels of green.
    assert greens(False) < greens(True) / 10, \
        "and not painted into the page as well"


def test_an_exported_markup_carries_who_made_it_and_what_it_says(window, tmp_path):
    window.select_tool("rect")
    _drag(window, 100, 100, 260, 200)
    box = window.document.pages[0].frame.ordered_markups()[0]
    box.author = "R. Kavanagh"
    box.comment = "Check this splice"
    box.subject = "Query"

    mark = _pdf(window.document, tmp_path, "said.pdf").markups()[0]
    assert str(mark["/T"]) == "R. Kavanagh"
    assert str(mark["/Contents"]) == "Check this splice"
    assert str(mark["/Subj"]) == "Query"


def test_bookmarks_still_work_when_the_markups_are_live(window, tmp_path):
    """The links go in after the annotations and must not displace them."""
    window.document.add_bookmark("Beam design", 0, 40.0)
    window.select_tool("rect")
    _drag(window, 100, 100, 260, 200)

    path = str(tmp_path / "both.pdf")
    export_io.export_pdf(window.document, path)
    assert _outline_titles(path) == ["Beam design"]
    assert len(Printed(path).markups()) == 1


def test_flattened_content_stays_part_of_the_sheet(window, tmp_path):
    """Flattening is the decision that it is the page now, so it is painted in."""
    window.select_tool("rect")
    _drag(window, 100, 100, 260, 200)
    window.select_tool("ellipse")
    _drag(window, 300, 100, 420, 200)
    box, oval = window.document.pages[0].frame.ordered_markups()
    window._flatten_items([box], recoverable=True)

    printed = _pdf(window.document, tmp_path, "flat.pdf")
    kinds = [str(mark["/Subtype"]) for mark in printed.markups()]
    assert kinds == ["/Circle"], \
        "only the ellipse is still a markup; the rectangle is the page now"


def test_a_contents_line_is_a_working_link_in_the_exported_pdf(window, tmp_path):
    """A contents block prints the bookmarks; each line has to go to its page.

    The outline was held; the links were not, so the block could have exported
    as a list of page numbers nobody could click.
    """
    from markforge.items.contents import ContentsItem

    window.add_page()
    window.add_page()
    window.document.add_bookmark("Foundation plan", 1, 40.0)
    window.document.add_bookmark("Roof framing", 2, 60.0)
    window.go_to_page(0)
    window.select_tool("contents")
    _drag(window, 60, 400, 400, 560)
    block = next(i for i in window.document.pages[0].frame.markups()
                 if isinstance(i, ContentsItem))
    assert block.rows, "the block lists the bookmarks it found"

    path = str(tmp_path / "contents.pdf")
    export_io.export_pdf(window.document, path)

    from pypdf import PdfReader
    reader = PdfReader(path)
    links = [entry.get_object() for entry in (reader.pages[0].get("/Annots") or [])
             if str(entry.get_object().get("/Subtype")) == "/Link"]
    assert len(links) == len(block.rows), \
        f"{len(block.rows)} contents lines, {len(links)} links"
    for link in links:
        destination = link.get("/Dest") or link.get("/A", {}).get("/D")
        assert destination, "a link with nowhere to go is not a link"
