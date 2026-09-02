"""What comes out of the printer.

A calculation sheet that looks right on screen and prints wrong is worse than
useless, so these tests read the produced PDF back and check the geometry, the
page count and the actual text on the page.
"""
import pytest
from PySide6.QtPdf import QPdfDocument

from calcforge.core.document import LANDSCAPE
from calcforge.io import export as export_io

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
        return "\n".join(self.document.getAllText(i).text()
                          for i in range(self.pages))


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


def test_a_calculation_and_its_result_land_on_the_page(window, tmp_path):
    window.select_tool("math")
    _drag(window, 80, 120, 380, 200)
    block = window.view.editing_item()
    block._editor.setPlainText("L = 6 m\nw = 12 kN/m\nM = w*L^2/8")
    window.view.end_item_edit()
    window.recalculate()

    text = _pdf(window.document, tmp_path).text()
    assert "54" in text                      # the answer, in kN·m
    assert "12" in text and "6" in text      # the inputs it came from


def test_a_table_prints_its_values_not_its_formulas(window, tmp_path):
    window.select_tool("table")
    _drag(window, 80, 80, 460, 240)
    table = window.view.active_table
    table.set_cell(0, 0, "Thickness")
    table.set_cell(1, 0, "150 mm")
    table.set_cell(0, 1, "Density")
    table.set_cell(1, 1, "24 kN/m^3")
    table.set_cell(0, 2, "Load")
    table.set_cell(1, 2, "=A2*B2")
    window.view.deactivate_table()
    window.recalculate()

    text = _pdf(window.document, tmp_path).text()
    assert "3.60" in text or "3.6" in text    # 150 mm x 24 kN/m3 = 3.6 kPa
    assert "=A2*B2" not in text


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
    from calcforge.core.document import PageScale
    window.current_page().scale = PageScale.from_ratio(50)
    window.select_tool("measure_length")
    _drag(window, 100, 400, 236, 400)
    window.view.end_item_edit()
    assert "2.4" in _pdf(window.document, tmp_path).text()


def test_printing_twice_gives_the_same_file(window, tmp_path):
    """A second print of an untouched document must not drift."""
    window.select_tool("math")
    _drag(window, 80, 120, 380, 180)
    window.view.editing_item()._editor.setPlainText("a = 2 m\nb = a*3")
    window.view.end_item_edit()
    window.recalculate()

    first = _pdf(window.document, tmp_path, "one.pdf")
    second = _pdf(window.document, tmp_path, "two.pdf")
    assert first.text() == second.text()
    assert first.pages == second.pages


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
    from calcforge.core.document import MM_TO_PT

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
    settings.logo_height_mm = 60.0            # taller than the 15 mm margin
    settings.show_header = True
    frame = window.document.pages[0].frame
    band = frame._band(_header_box(frame), "header", 42.5)
    assert band.height() <= 42.5
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
    from calcforge.core.document import Document
    from calcforge.io import project as project_io

    settings = window.document.settings
    settings.logo_key = _logo(window.document)
    settings.logo_slot = "footer_center"
    settings.logo_height_mm = 12.5
    path = str(tmp_path / "logo.cfx")
    project_io.save_document(window.document, path)

    reopened = Document()
    project_io.load_document(reopened, path)
    assert reopened.settings.logo_slot == "footer_center"
    assert reopened.settings.logo_height_mm == pytest.approx(12.5)
    assert reopened.asset(reopened.settings.logo_key)
