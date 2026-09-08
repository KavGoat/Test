"""The document model: a PDF held in memory, plus the four edits the editor makes.

Everything that touches the PDF itself lives here, and nothing here imports Qt —
the same split PDF4QT keeps between its rendering library and its applications.
The UI asks this module for images and hands back geometry in *display points*:
PDF user-space units with the page's own ``/Rotate`` already applied, so the
coordinates the user sees on screen are the coordinates used throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional

import pymupdf

# Annotations the user never drags: pop-up notes belong to their parent
# annotation, and links are navigation rather than markup.
HIDDEN_SUBTYPES = frozenset({pymupdf.PDF_ANNOT_POPUP, pymupdf.PDF_ANNOT_LINK})

A4_POINTS = (595.0, 842.0)

# The colour new rectangles are drawn in — the usual markup red.
RECTANGLE_COLOUR = (0.85, 0.16, 0.16)
RECTANGLE_WIDTH = 1.5


@dataclass(frozen=True)
class Markup:
    """One annotation on a page, in display points."""

    xref: int
    subtype: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


@dataclass(frozen=True)
class Raster:
    """A rendered image, ready to be wrapped in a QImage.

    ``x`` and ``y`` are where the image belongs in the rendered page, in pixels;
    for a whole page that is always the origin.
    """

    samples: bytes
    width: int
    height: int
    stride: int
    alpha: bool
    x: int = 0
    y: int = 0


class DocumentError(RuntimeError):
    """A PDF could not be opened or saved."""


class PdfDocument:
    """A PDF opened for editing.

    The file is read into memory and the file handle closed, so the document can
    always be saved back over the file it came from.
    """

    def __init__(self) -> None:
        self._doc = pymupdf.open()
        self.path: Optional[str] = None
        self.modified = False

    # ------------------------------------------------------------------ state

    @property
    def page_count(self) -> int:
        return self._doc.page_count

    @property
    def is_empty(self) -> bool:
        return self._doc.page_count == 0

    def page_size(self, index: int) -> tuple[float, float]:
        """The page's visible size in points, rotation applied."""
        rect = self._doc[index].rect
        return rect.width, rect.height

    # ------------------------------------------------------------- open, save

    def open(self, path: str) -> None:
        try:
            with open(path, "rb") as handle:
                data = handle.read()
            doc = pymupdf.open(stream=data, filetype="pdf")
        except Exception as exc:  # noqa: BLE001 - any failure is the same to us
            raise DocumentError(f"Could not open {path}: {exc}") from exc
        if doc.needs_pass:
            doc.close()
            raise DocumentError(f"{path} is password protected.")
        self._doc.close()
        self._doc = doc
        self.path = path
        self.modified = False

    def save(self, path: Optional[str] = None) -> None:
        target = path or self.path
        if target is None:
            raise DocumentError("The document has no file name yet.")
        try:
            self._doc.save(target, garbage=3, deflate=True)
        except Exception as exc:  # noqa: BLE001
            raise DocumentError(f"Could not save {target}: {exc}") from exc
        self.path = target
        self.modified = False

    def close(self) -> None:
        self._doc.close()
        self._doc = pymupdf.open()
        self.path = None
        self.modified = False

    # --------------------------------------------------------------- rendering

    def render_page(self, index: int, zoom: float = 1.0) -> Raster:
        """The page *without* its annotations — those are drawn separately so
        they can be picked up and moved."""
        page = self._doc[index]
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), annots=False)
        return Raster(bytes(pixmap.samples), pixmap.width, pixmap.height,
                      pixmap.stride, bool(pixmap.alpha))

    def render_thumbnail(self, index: int, longest_edge: int = 140) -> Raster:
        width, height = self.page_size(index)
        zoom = longest_edge / max(width, height, 1.0)
        page = self._doc[index]
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), annots=True)
        return Raster(bytes(pixmap.samples), pixmap.width, pixmap.height,
                      pixmap.stride, bool(pixmap.alpha))

    def render_markup(self, index: int, xref: int, zoom: float = 1.0) -> Optional[Raster]:
        """The annotation on its own, transparent everywhere else."""
        page = self._doc[index]  # keep the page alive while the annotation is used
        annot = self._find(page, xref)
        if annot is None:
            return None
        try:
            pixmap = annot.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=True)
        except Exception:  # noqa: BLE001 - annotation without an appearance
            return None
        if not pixmap.width or not pixmap.height:
            return None
        box = pixmap.irect
        return Raster(bytes(pixmap.samples), pixmap.width, pixmap.height,
                      pixmap.stride, True, int(box[0]), int(box[1]))

    # ----------------------------------------------------------------- markups

    def markups(self, index: int) -> list[Markup]:
        page = self._doc[index]
        rotation = page.rotation_matrix
        found: list[Markup] = []
        for annot in self._annots(page):
            if annot.type[0] in HIDDEN_SUBTYPES:
                continue
            rect = annot.rect * rotation
            found.append(Markup(annot.xref, annot.type[1],
                                rect.x0, rect.y0, rect.x1, rect.y1))
        return found

    def move_markup(self, index: int, xref: int, dx: float, dy: float) -> bool:
        """Shift an existing annotation by ``dx``/``dy`` display points.

        The annotation's ``/Rect`` is rewritten directly rather than through
        ``Annot.set_rect``, which re-applies the border padding on every call and
        so would creep the markup a point further with each drag.
        """
        page = self._doc[index]  # keep the page alive while the annotation is used
        if self._find(page, xref) is None:
            return False
        try:
            kind, raw = self._doc.xref_get_key(xref, "Rect")
            if kind != "array":
                return False
            x0, y0, x1, y1 = (float(value) for value in raw.strip("[]").split())
        except ValueError:
            return False
        # Display points -> unrotated page points -> PDF user space. Only the
        # linear part applies: this is a direction, not a position.
        matrix = page.derotation_matrix * page.transformation_matrix
        pdf_dx = dx * matrix.a + dy * matrix.c
        pdf_dy = dx * matrix.b + dy * matrix.d
        self._doc.xref_set_key(xref, "Rect", "[%g %g %g %g]" % (
            x0 + pdf_dx, y0 + pdf_dy, x1 + pdf_dx, y1 + pdf_dy))
        # Dropping the page reference is what makes the edit visible: the next
        # ``doc[index]`` then re-reads the page and picks up the new rectangle.
        del page
        self.modified = True
        return True

    def add_rectangle(self, index: int, rect: tuple[float, float, float, float]) -> int:
        """Add a rectangle annotation, given its corners in display points."""
        page = self._doc[index]
        box = pymupdf.Rect(*rect).normalize() * page.derotation_matrix
        annot = page.add_rect_annot(box)
        annot.set_colors(stroke=RECTANGLE_COLOUR)
        annot.set_border(width=RECTANGLE_WIDTH)
        annot.update()
        self.modified = True
        return annot.xref

    # ------------------------------------------------------------------- pages

    def insert_page(self, index: int) -> None:
        """Insert a blank page at ``index``, matching the size of its neighbour."""
        if self._doc.page_count:
            neighbour = min(max(index - 1, 0), self._doc.page_count - 1)
            width, height = self.page_size(neighbour)
        else:
            width, height = A4_POINTS
        self._doc.new_page(pno=index, width=width, height=height)
        self.modified = True

    def delete_page(self, index: int) -> None:
        if self._doc.page_count <= 1:
            raise DocumentError("A PDF must keep at least one page.")
        self._doc.delete_page(index)
        self.modified = True

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _annots(page: "pymupdf.Page") -> Iterator["pymupdf.Annot"]:
        annot = page.first_annot
        while annot is not None:
            yield annot
            annot = annot.next

    def _find(self, page: "pymupdf.Page", xref: int) -> Optional["pymupdf.Annot"]:
        """Look an annotation up on a page the caller holds a reference to.

        The page has to outlive the annotation: an ``Annot`` whose page has been
        collected takes MuPDF down with it.
        """
        for annot in self._annots(page):
            if annot.xref == xref:
                return annot
        return None
