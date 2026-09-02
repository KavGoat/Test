"""Importing PDF pages as page backgrounds, using Qt's own PDF module."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QBuffer, QIODevice, QSize
from PySide6.QtGui import QImage
from PySide6.QtPdf import QPdfDocument, QPdfDocumentRenderOptions

from ..core.document import PT_TO_MM, LANDSCAPE, PORTRAIT, Page, PageSetup

# An A0 sheet at 300 dpi is 140 megapixels; Qt will not allocate it, and even
# when it does the PNG encoder can fail. 48 megapixels is A0 at about 100 dpi
# and A4 at 600, which is more than enough to read a drawing.
MAX_PIXELS = 48_000_000

FIT_ORIGINAL = "original"       # page takes the PDF page's own size
FIT_A4 = "a4"                   # scale into A4
FIT_CURRENT = "current"         # scale into the document's current page size


@dataclass
class PdfPageInfo:
    index: int
    width_pt: float
    height_pt: float


class PdfSource:
    """A loaded PDF, ready to render pages into page backgrounds."""

    def __init__(self, path: str):
        self.path = path
        self.doc = QPdfDocument()
        status = self.doc.load(path)
        if status != QPdfDocument.Error.None_:
            raise OSError(f"Could not open {path}: {status.name}")

    @property
    def page_count(self) -> int:
        return self.doc.pageCount()

    def page_info(self, index: int) -> PdfPageInfo:
        size = self.doc.pagePointSize(index)
        return PdfPageInfo(index, size.width(), size.height())

    def render_png(self, index: int, dpi: float = 150.0) -> tuple[bytes, PdfPageInfo]:
        """Render one page to PNG bytes, at *dpi* or the most that will fit.

        A big drawing sheet at a high dpi runs into limits — the image cannot
        be allocated, or it can be allocated but not encoded — and both used to
        end with an empty asset and a page that simply came out blank. The
        request is scaled down to something that will fit, and anything that
        still fails is raised rather than swallowed.
        """
        info = self.page_info(index)
        scale = self._scale_for(info, dpi)
        width = max(int(round(info.width_pt * scale)), 1)
        height = max(int(round(info.height_pt * scale)), 1)
        options = QPdfDocumentRenderOptions()
        image = self.doc.render(index, QSize(width, height), options)
        if image.isNull():
            raise OSError(f"Could not render page {index + 1} of this PDF")
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        if not image.save(buffer, "PNG") or buffer.data().isEmpty():
            raise OSError(f"Page {index + 1} rendered but could not be stored — "
                          "try a lower dpi")
        return bytes(buffer.data()), info

    @staticmethod
    def _scale_for(info: PdfPageInfo, dpi: float) -> float:
        """Points-to-pixels, held under a size Qt can actually allocate."""
        scale = max(dpi, 24.0) / 72.0
        pixels = (info.width_pt * scale) * (info.height_pt * scale)
        if pixels > MAX_PIXELS:
            scale *= (MAX_PIXELS / pixels) ** 0.5
        return max(scale, 24.0 / 72.0)

    def close(self) -> None:
        self.doc.close()


def setup_for(info: PdfPageInfo, fit: str, template: Optional[PageSetup]) -> PageSetup:
    """Choose the page geometry for an imported PDF page."""
    if fit == FIT_ORIGINAL:
        setup = PageSetup(size_name="Custom",
                          width_mm=info.width_pt * PT_TO_MM,
                          height_mm=info.height_pt * PT_TO_MM,
                          orientation=PORTRAIT)
        setup.margin_left = setup.margin_top = setup.margin_right = setup.margin_bottom = 0.0
        return setup
    if fit == FIT_CURRENT and template is not None:
        setup = PageSetup.from_dict(template.to_dict())
    else:
        setup = PageSetup.from_name("A4")
    setup.orientation = LANDSCAPE if info.width_pt > info.height_pt else PORTRAIT
    return setup


def import_pages(document, path: str, indices: list[int], fit: str = FIT_ORIGINAL,
                 dpi: float = 150.0, at: Optional[int] = None) -> list[Page]:
    """Load the chosen PDF pages into *document* as new pages."""
    source = PdfSource(path)
    template = document.pages[at - 1].setup if at else (
        document.pages[-1].setup if document.pages else None)
    created: list[Page] = []
    try:
        for offset, index in enumerate(indices):
            data, info = source.render_png(index, dpi)
            key = document.add_asset(data, "png")
            page = Page(setup_for(info, fit, template))
            page.background_key = key
            page.source_note = f"{path.rsplit('/', 1)[-1]} page {index + 1}"
            page.label = page.source_note
            position = None if at is None else at + offset
            if position is None:
                document.pages.append(page)
            else:
                document.pages.insert(position, page)
            created.append(page)
    finally:
        source.close()
    document.modified = True
    return created


def render_preview(path: str, index: int, box: int = 560):
    """A page rendered small, for showing what an import will bring in."""
    source = PdfSource(path)
    try:
        info = source.page_info(index)
        longest = max(info.width_pt, info.height_pt, 1.0)
        return source.doc.render(index, QSize(
            max(int(info.width_pt / longest * box), 1),
            max(int(info.height_pt / longest * box), 1)),
            QPdfDocumentRenderOptions())
    finally:
        source.close()


def page_count(path: str) -> int:
    source = PdfSource(path)
    try:
        return source.page_count
    finally:
        source.close()


def parse_page_range(text: str, maximum: int) -> list[int]:
    """Turn ``1-3,7`` into zero-based page indices."""
    text = (text or "").strip()
    if not text or text.lower() == "all":
        return list(range(maximum))
    indices: list[int] = []
    for chunk in text.replace(" ", "").split(","):
        if not chunk:
            continue
        if "-" in chunk:
            start, _, end = chunk.partition("-")
            try:
                first = max(int(start), 1)
                last = min(int(end or maximum), maximum)
            except ValueError:
                continue
            indices.extend(range(first - 1, last))
        else:
            try:
                value = int(chunk)
            except ValueError:
                continue
            if 1 <= value <= maximum:
                indices.append(value - 1)
    seen: set[int] = set()
    ordered = []
    for index in indices:
        if index not in seen:
            seen.add(index)
            ordered.append(index)
    return ordered


def import_image(document, path: str, fit: str = FIT_ORIGINAL,
                 at: Optional[int] = None) -> Page:
    """Put a photo or a scan on a page of its own, the way a PDF page goes in."""
    image = QImage(path)
    if image.isNull():
        raise OSError(f"Could not read {path}")
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise OSError(f"Could not read {path}")
    key = document.add_asset(bytes(buffer.data()), "png")
    # An image has pixels, not points. Read it at 96 dpi, which is what a
    # screen-shot or a phone photo is usually taken to be.
    info = PdfPageInfo(0, image.width() * 72.0 / 96.0, image.height() * 72.0 / 96.0)
    template = document.pages[at - 1].setup if at else (
        document.pages[-1].setup if document.pages else None)
    page = Page(setup_for(info, fit, template))
    page.background_key = key
    page.source_note = path.rsplit("/", 1)[-1]
    page.label = page.source_note
    if at is None:
        document.pages.append(page)
    else:
        document.pages.insert(at, page)
    document.modified = True
    return page
