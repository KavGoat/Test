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
