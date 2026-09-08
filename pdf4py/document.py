"""The document model: a PDF held in memory, plus the four edits the editor makes.

Everything that touches the PDF itself lives here, and nothing here imports Qt —
the same split PDF4QT keeps between its rendering library and its applications.
The UI asks this module for images and hands back geometry in *display points*:
PDF user-space units with the page's own ``/Rotate`` already applied, so the
coordinates the user sees on screen are the coordinates used throughout.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterator, Optional

import pymupdf

# MuPDF writes its own diagnostics straight to stderr. A file with a damaged
# xref produces thousands of "cannot find object in xref" lines, which floods
# the console, is slow enough on Windows to be felt, and tells the user nothing
# they can act on. Collect the messages instead and report them once.
pymupdf.TOOLS.mupdf_display_errors(False)
pymupdf.TOOLS.mupdf_display_warnings(False)


def _drain_messages() -> str:
    try:
        return pymupdf.TOOLS.mupdf_warnings(reset=True) or ""
    except Exception:  # noqa: BLE001 - diagnostics must never break the app
        return ""


# Annotations the user never drags: pop-up notes belong to their parent
# annotation, and links are navigation rather than markup.
HIDDEN_SUBTYPES = frozenset({pymupdf.PDF_ANNOT_POPUP, pymupdf.PDF_ANNOT_LINK})

# Markups drawn at a fixed size — a sticky note is an icon, not a box, and
# stretching it only stretches the icon.
FIXED_SIZE_SUBTYPES = frozenset({pymupdf.PDF_ANNOT_TEXT,
                                 pymupdf.PDF_ANNOT_FILE_ATTACHMENT,
                                 pymupdf.PDF_ANNOT_SOUND})

# Markups that carry text of their own, which the user can rewrite.
TEXT_SUBTYPES = frozenset({pymupdf.PDF_ANNOT_FREE_TEXT, pymupdf.PDF_ANNOT_TEXT})

A4_POINTS = (595.0, 842.0)

# A markup smaller than this is a mis-drag, not a resize.
MIN_MARKUP_SIZE = 3.0

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
    #: The xref every markup in this group hangs off, or 0 when ungrouped.
    leader: int = 0
    #: A callout's leader line: two or three points, the arrow tip first.
    callout: tuple[tuple[float, float], ...] = ()
    #: The markup's own words, for the kinds that carry any.
    text: str = ""
    resizable: bool = True
    editable_text: bool = False

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def rect(self) -> tuple[float, float, float, float]:
        return self.x0, self.y0, self.x1, self.y1


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
        self.repaired = False
        self.warnings = ""

    # ------------------------------------------------------------------ state

    @property
    def page_count(self) -> int:
        return self._doc.page_count

    @property
    def is_empty(self) -> bool:
        return self._doc.page_count == 0

    def page_size(self, index: int) -> tuple[float, float]:
        """The page's visible size in points, rotation applied."""
        try:
            rect = self._doc[index].rect
        except Exception:  # noqa: BLE001 - a page too damaged to measure
            _drain_messages()
            return A4_POINTS
        return rect.width, rect.height

    # ------------------------------------------------------------- open, save

    def open(self, path: str) -> None:
        _drain_messages()
        try:
            # Opened from the file rather than from memory: that is what lets a
            # later save append the change instead of rewriting the whole
            # document, which on a large drawing set is seconds against nothing.
            doc = pymupdf.open(path, filetype="pdf")
            page_count = doc.page_count
        except Exception as exc:  # noqa: BLE001 - any failure is the same to us
            _drain_messages()
            raise DocumentError(f"Could not open {path}: {exc}") from exc
        if doc.needs_pass:
            doc.close()
            raise DocumentError(f"{path} is password protected.")
        if not page_count:
            doc.close()
            raise DocumentError(f"{path} has no pages.")
        self._doc.close()
        self._doc = doc
        self.path = path
        self.modified = False
        self.warnings = _drain_messages()
        self.repaired = bool(getattr(doc, "is_repaired", False))

    def save(self, path: Optional[str] = None) -> bool:
        """Write the document out. True if it had to be reloaded to do it.

        Saving back over the file it came from appends the changes, which takes
        no measurable time whatever the document's size. Only a file MuPDF had
        to repair, or a save under a new name, rewrites the whole thing — and
        even then without ``deflate``, which recompresses every stream in the
        document and turns a ten megabyte drawing set into a seventeen second
        wait for a change that took a moment to make.
        """
        target = path or self.path
        if target is None:
            raise DocumentError("The document has no file name yet.")
        if self.path and os.path.abspath(target) == os.path.abspath(self.path):
            if not self.repaired and self._save_appended(target):
                return False
            return self._save_rewritten(target)
        try:
            self._doc.save(target)
        except Exception as exc:  # noqa: BLE001
            _drain_messages()
            raise DocumentError(f"Could not save {target}: {exc}") from exc
        self.path = target
        self.modified = False
        return False

    def _save_appended(self, target: str) -> bool:
        """Append the changes to the file. False if this document cannot."""
        try:
            self._doc.save(target, incremental=True,
                           encryption=pymupdf.PDF_ENCRYPT_KEEP)
        except Exception:  # noqa: BLE001 - a document MuPDF will not append to
            _drain_messages()
            return False
        self.modified = False
        return True

    def _save_rewritten(self, target: str) -> bool:
        """Write a whole new file over the open one, then reopen it.

        The document has to let go of the file before it can be replaced, so
        this is the slow path, and the one that invalidates every xref the
        caller is holding — hence the True it returns.
        """
        temporary = target + ".pdf4py-part"
        try:
            self._doc.save(temporary)
            self._doc.close()
        except Exception as exc:  # noqa: BLE001
            _drain_messages()
            self._remove(temporary)
            raise DocumentError(f"Could not save {target}: {exc}") from exc
        try:
            os.replace(temporary, target)
        except OSError as exc:
            self._remove(temporary)
            self._doc = pymupdf.open(target)     # put the document back
            raise DocumentError(f"Could not save {target}: {exc}") from exc
        self._doc = pymupdf.open(target)
        self.repaired = False
        self.modified = False
        return True

    @staticmethod
    def _remove(path: str) -> None:
        try:
            os.remove(path)
        except OSError:
            pass

    def close(self) -> None:
        self._doc.close()
        self._doc = pymupdf.open()
        self.path = None
        self.modified = False
        self.repaired = False
        self.warnings = ""

    # --------------------------------------------------------------- rendering

    def render_page(self, index: int, zoom: float = 1.0) -> Optional[Raster]:
        """The page *without* its annotations — those are drawn separately so
        they can be picked up and moved.

        ``None`` when the page will not render: a damaged page must leave the
        rest of the document usable, not take the window down with it.
        """
        try:
            page = self._doc[index]
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), annots=False)
        except Exception:  # noqa: BLE001 - a page MuPDF cannot draw
            _drain_messages()
            return None
        return Raster(bytes(pixmap.samples), pixmap.width, pixmap.height,
                      pixmap.stride, bool(pixmap.alpha))

    def render_thumbnail(self, index: int, longest_edge: int = 140) -> Optional[Raster]:
        try:
            width, height = self.page_size(index)
            zoom = longest_edge / max(width, height, 1.0)
            page = self._doc[index]
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), annots=True)
        except Exception:  # noqa: BLE001
            _drain_messages()
            return None
        return Raster(bytes(pixmap.samples), pixmap.width, pixmap.height,
                      pixmap.stride, bool(pixmap.alpha))

    def render_markup(self, index: int, xref: int, zoom: float = 1.0) -> Optional[Raster]:
        """The annotation on its own, transparent everywhere else."""
        try:
            page = self._doc[index]  # the page must outlive the annotation
            annot = self._find(page, xref)
            return None if annot is None else self._raster_for(annot, zoom)
        except Exception:  # noqa: BLE001
            _drain_messages()
            return None

    def markups_with_rasters(self, index: int, zoom: float = 1.0
                             ) -> list[tuple[Markup, Optional[Raster]]]:
        """Every markup on the page, drawn, in a single walk of the page.

        Rendering them one xref at a time means re-walking the annotation list
        for each one, which is quadratic — four seconds for the six hundred
        markups a marked-up drawing sheet can carry. This does one pass.
        """
        try:
            page = self._doc[index]  # the page must outlive the annotations
            rotation = page.rotation_matrix
        except Exception:  # noqa: BLE001
            _drain_messages()
            return []
        drawn: list[tuple[Markup, Optional[Raster]]] = []
        for annot in self._annots(page):
            try:
                if annot.type[0] in HIDDEN_SUBTYPES:
                    continue
                drawn.append((self._describe(page, annot, rotation),
                              self._raster_for(annot, zoom)))
            except Exception:  # noqa: BLE001 - one bad annotation, not the page
                _drain_messages()
        return drawn

    @staticmethod
    def _raster_for(annot: "pymupdf.Annot", zoom: float) -> Optional[Raster]:
        try:
            pixmap = annot.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=True)
        except Exception:  # noqa: BLE001 - annotation without an appearance
            _drain_messages()
            return None
        if not pixmap.width or not pixmap.height:
            return None
        box = pixmap.irect
        return Raster(bytes(pixmap.samples), pixmap.width, pixmap.height,
                      pixmap.stride, True, int(box[0]), int(box[1]))

    # ----------------------------------------------------------------- markups

    def markups(self, index: int) -> list[Markup]:
        try:
            page = self._doc[index]
            rotation = page.rotation_matrix
        except Exception:  # noqa: BLE001
            _drain_messages()
            return []
        found: list[Markup] = []
        for annot in self._annots(page):
            try:
                if annot.type[0] in HIDDEN_SUBTYPES:
                    continue
                found.append(self._describe(page, annot, rotation))
            except Exception:  # noqa: BLE001 - one bad annotation, not the page
                _drain_messages()
        return found

    def _describe(self, page: "pymupdf.Page", annot: "pymupdf.Annot",
                  rotation: "pymupdf.Matrix") -> Markup:
        kind = annot.type[0]
        rect = annot.rect * rotation
        return Markup(annot.xref, annot.type[1],
                      rect.x0, rect.y0, rect.x1, rect.y1,
                      leader=self._leader_of(annot.xref),
                      callout=self._callout_of(page, annot.xref),
                      text=annot.info.get("content", "") if kind in TEXT_SUBTYPES else "",
                      resizable=kind not in FIXED_SIZE_SUBTYPES,
                      editable_text=kind in TEXT_SUBTYPES)

    # ------------------------------------------------------------------ groups

    def _leader_of(self, xref: int) -> int:
        """The markup this one is grouped onto, or 0.

        PDF 32000 §12.5.6.2: an annotation with ``/RT /Group`` is grouped with
        the annotation its ``/IRT`` names, and that one leads the group. A plain
        ``/IRT`` without ``/RT /Group`` is a reply, not a group.
        """
        try:
            kind, reply_type = self._doc.xref_get_key(xref, "RT")
            if kind != "name" or reply_type.lstrip("/") != "Group":
                return 0
            kind, parent = self._doc.xref_get_key(xref, "IRT")
            if kind != "xref":
                return 0
            return int(parent.split()[0])
        except Exception:  # noqa: BLE001
            _drain_messages()
            return 0

    def group_members(self, index: int, xref: int) -> list[int]:
        """Every markup that moves when this one does, itself included."""
        leader = self._leader_of(xref) or xref
        members = [markup.xref for markup in self.markups(index)
                   if markup.xref == leader or markup.leader == leader]
        return members if len(members) > 1 else [xref]

    def group(self, index: int, xrefs: list[int]) -> bool:
        """Tie markups together so they move as one. The first one leads."""
        if len(xrefs) < 2:
            return False
        # Anything already grouped joins under this group's leader instead of
        # keeping a leader that is about to become a member itself.
        leader, *rest = xrefs
        try:
            self._doc.xref_set_key(leader, "IRT", "null")
            self._doc.xref_set_key(leader, "RT", "null")
            for xref in rest:
                self._doc.xref_set_key(xref, "IRT", "%d 0 R" % leader)
                self._doc.xref_set_key(xref, "RT", "/Group")
        except Exception:  # noqa: BLE001
            _drain_messages()
            return False
        self.modified = True
        return True

    def ungroup(self, index: int, xref: int) -> int:
        """Break the group this markup is in. Returns how many were freed."""
        members = self.group_members(index, xref)
        if len(members) < 2:
            return 0
        try:
            for member in members:
                self._doc.xref_set_key(member, "IRT", "null")
                self._doc.xref_set_key(member, "RT", "null")
        except Exception:  # noqa: BLE001
            _drain_messages()
            return 0
        self.modified = True
        return len(members)

    # ---------------------------------------------------------------- callouts

    def _callout_of(self, page: "pymupdf.Page", xref: int
                    ) -> tuple[tuple[float, float], ...]:
        """A callout's leader line in display points, arrow tip first."""
        try:
            kind, raw = self._doc.xref_get_key(xref, "CL")
            if kind != "array":
                return ()
            numbers = [float(value) for value in raw.strip("[]").split()]
        except Exception:  # noqa: BLE001
            _drain_messages()
            return ()
        if len(numbers) not in (4, 6):
            return ()
        to_display = self._to_display(page)
        return tuple((point.x, point.y) for point in
                     (pymupdf.Point(numbers[i], numbers[i + 1]) * to_display
                      for i in range(0, len(numbers), 2)))

    def set_callout(self, index: int, xref: int,
                    points: list[tuple[float, float]]) -> bool:
        """Reshape a callout's leader line, given its points in display points."""
        if len(points) not in (2, 3):
            return False
        try:
            page = self._doc[index]  # the page must outlive the annotation
            annot = self._find(page, xref)
            if annot is None:
                return False
            to_pdf = self._to_pdf(page)
            moved = [pymupdf.Point(x, y) * to_pdf for x, y in points]
            self._doc.xref_set_key(xref, "CL", "[%s]" % " ".join(
                "%g %g" % (point.x, point.y) for point in moved))
            # The rectangle has to hold the line as well as the words, and
            # update() redraws the leader from the numbers just written.
            annot.update()
        except Exception:  # noqa: BLE001
            _drain_messages()
            return False
        self.modified = True
        return True

    # -------------------------------------------------------------------- text

    def set_text(self, index: int, xref: int, text: str) -> bool:
        """Rewrite what a text box or a sticky note says."""
        try:
            page = self._doc[index]  # the page must outlive the annotation
            annot = self._find(page, xref)
            if annot is None or annot.type[0] not in TEXT_SUBTYPES:
                return False
            info = annot.info
            info["content"] = text
            annot.set_info(info)
            annot.update()
        except Exception:  # noqa: BLE001
            _drain_messages()
            return False
        self.modified = True
        return True

    # ------------------------------------------------------------------ resize

    def resize_markup(self, index: int, xref: int,
                      rect: tuple[float, float, float, float]) -> bool:
        """Give a markup a new rectangle, in display points."""
        try:
            page = self._doc[index]  # the page must outlive the annotation
            annot = self._find(page, xref)
            if annot is None or annot.type[0] in FIXED_SIZE_SUBTYPES:
                return False
            target = pymupdf.Rect(*rect).normalize() * page.derotation_matrix
            if target.width < MIN_MARKUP_SIZE or target.height < MIN_MARKUP_SIZE:
                return False
            annot.set_rect(target)
            # set_rect pads the rectangle by the border width, so ask again for
            # the difference it introduced rather than letting it accumulate.
            drift = annot.rect - target
            if max(abs(value) for value in drift) > 0.01:
                annot.set_rect(target - drift)
        except Exception:  # noqa: BLE001 - a markup that will not be resized
            _drain_messages()
            return False
        self.modified = True
        return True

    # ------------------------------------------------------- coordinate frames

    @staticmethod
    def _to_pdf(page: "pymupdf.Page") -> "pymupdf.Matrix":
        """Display points -> PDF user space."""
        return page.derotation_matrix * page.transformation_matrix

    @staticmethod
    def _to_display(page: "pymupdf.Page") -> "pymupdf.Matrix":
        """PDF user space -> display points."""
        return ~pymupdf.Matrix(page.transformation_matrix) * page.rotation_matrix

    def move_markup(self, index: int, xref: int, dx: float, dy: float) -> bool:
        """Shift an existing annotation by ``dx``/``dy`` display points.

        The annotation's ``/Rect`` is rewritten directly rather than through
        ``Annot.set_rect``, which re-applies the border padding on every call and
        so would creep the markup a point further with each drag.
        """
        try:
            page = self._doc[index]  # the page must outlive the annotation
            if self._find(page, xref) is None:
                return False
            kind, raw = self._doc.xref_get_key(xref, "Rect")
            if kind != "array":
                return False
            x0, y0, x1, y1 = (float(value) for value in raw.strip("[]").split())
            # Display points -> unrotated page points -> PDF user space. Only
            # the linear part applies: this is a direction, not a position.
            matrix = page.derotation_matrix * page.transformation_matrix
            pdf_dx = dx * matrix.a + dy * matrix.c
            pdf_dy = dx * matrix.b + dy * matrix.d
            self._doc.xref_set_key(xref, "Rect", "[%g %g %g %g]" % (
                x0 + pdf_dx, y0 + pdf_dy, x1 + pdf_dx, y1 + pdf_dy))
        except Exception:  # noqa: BLE001 - an annotation that will not move
            _drain_messages()
            return False
        # Dropping the page reference is what makes the edit visible: the next
        # ``doc[index]`` then re-reads the page and picks up the new rectangle.
        del page
        self.modified = True
        return True

    def add_rectangle(self, index: int, rect: tuple[float, float, float, float]) -> int:
        """Add a rectangle annotation, given its corners in display points."""
        try:
            page = self._doc[index]
            box = pymupdf.Rect(*rect).normalize() * page.derotation_matrix
            annot = page.add_rect_annot(box)
            annot.set_colors(stroke=RECTANGLE_COLOUR)
            annot.set_border(width=RECTANGLE_WIDTH)
            annot.update()
            xref = annot.xref
        except Exception as exc:  # noqa: BLE001
            _drain_messages()
            raise DocumentError(f"Could not add the rectangle: {exc}") from exc
        self.modified = True
        return xref

    # ------------------------------------------------------------------- pages

    def insert_page(self, index: int) -> None:
        """Insert a blank page at ``index``, matching the size of its neighbour."""
        if self._doc.page_count:
            neighbour = min(max(index - 1, 0), self._doc.page_count - 1)
            width, height = self.page_size(neighbour)
        else:
            width, height = A4_POINTS
        try:
            self._doc.new_page(pno=index, width=width, height=height)
        except Exception as exc:  # noqa: BLE001
            _drain_messages()
            raise DocumentError(f"Could not insert a page: {exc}") from exc
        self.modified = True

    def delete_page(self, index: int) -> None:
        if self._doc.page_count <= 1:
            raise DocumentError("A PDF must keep at least one page.")
        try:
            self._doc.delete_page(index)
        except Exception as exc:  # noqa: BLE001
            _drain_messages()
            raise DocumentError(f"Could not delete the page: {exc}") from exc
        self.modified = True

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _annots(page: "pymupdf.Page") -> Iterator["pymupdf.Annot"]:
        try:
            annot = page.first_annot
        except Exception:  # noqa: BLE001 - a page with a broken /Annots array
            _drain_messages()
            return
        while annot is not None:
            yield annot
            try:
                annot = annot.next
            except Exception:  # noqa: BLE001 - a broken link in the chain
                _drain_messages()
                return

    def _find(self, page: "pymupdf.Page", xref: int) -> Optional["pymupdf.Annot"]:
        """Look an annotation up on a page the caller holds a reference to.

        The page has to outlive the annotation: an ``Annot`` whose page has been
        collected takes MuPDF down with it.
        """
        for annot in self._annots(page):
            if annot.xref == xref:
                return annot
        return None
