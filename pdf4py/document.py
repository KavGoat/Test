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
from typing import Callable, Iterator, Optional

import pymupdf

from . import geometry
from .history import History, Step

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

# Room left round a callout's leader line inside the annotation's rectangle.
CALLOUT_PADDING = 2.0

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

    Opened from its file rather than into memory, so a save can append the
    change instead of rewriting the whole document.
    """

    def __init__(self) -> None:
        self._doc = pymupdf.open()
        self.path: Optional[str] = None
        self.modified = False
        self.repaired = False
        self.warnings = ""
        self.history = History()

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
        self.history.clear()
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
        self.history.clear()        # the xrefs those steps name are gone
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
        self.history.clear()

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
        leader, *rest = xrefs

        def change() -> bool:
            # Anything already grouped joins under this group's leader instead
            # of keeping one that is about to become a member itself.
            self._doc.xref_set_key(leader, "IRT", "null")
            self._doc.xref_set_key(leader, "RT", "null")
            for xref in rest:
                self._doc.xref_set_key(xref, "IRT", "%d 0 R" % leader)
                self._doc.xref_set_key(xref, "RT", "/Group")
            return True

        return self._edit(f"Group {len(xrefs)} markups", xrefs, change)

    def ungroup(self, index: int, xref: int) -> int:
        """Break the group this markup is in. Returns how many were freed."""
        members = self.group_members(index, xref)
        if len(members) < 2:
            return 0

        def change() -> bool:
            for member in members:
                self._doc.xref_set_key(member, "IRT", "null")
                self._doc.xref_set_key(member, "RT", "null")
            return True

        return len(members) if self._edit(f"Ungroup {len(members)} markups",
                                          members, change) else 0

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
        """Reshape a callout's leader line, given its points in display points.

        The rectangle has to hold the leader as well as the words, and the
        ``/RD`` insets say where the words sit inside it. Move the leader
        without moving that pair together and the text box collapses — which
        is a callout that has disappeared.
        """
        if len(points) not in (2, 3):
            return False
        try:
            page = self._doc[index]  # the page must outlive the annotation
            if self._find(page, xref) is None:
                return False
            to_pdf = self._to_pdf(page)
            leader = [pymupdf.Point(x, y) * to_pdf for x, y in points]
            inner = self._text_box_of(xref)
            if inner is None:
                return False
        except Exception:  # noqa: BLE001
            _drain_messages()
            return False

        def change() -> bool:
            box = pymupdf.Rect(inner)
            for point in leader:
                box |= pymupdf.Rect(point.x, point.y, point.x, point.y)
            box = pymupdf.Rect(box.x0 - CALLOUT_PADDING, box.y0 - CALLOUT_PADDING,
                               box.x1 + CALLOUT_PADDING, box.y1 + CALLOUT_PADDING)
            self._doc.xref_set_key(xref, "CL", "[%s]" % " ".join(
                "%g %g" % (point.x, point.y) for point in leader))
            self._set_callout_box(xref, box, inner)
            if not self._regenerate(index, xref):
                return False
            # Redrawing settles the rectangle on what it actually needs, which
            # leaves the insets describing the old one — and an inset measured
            # from the wrong rectangle is a text box that has slid, or closed
            # up altogether. Say where the words go once more, against the
            # rectangle that is now there.
            settled = geometry.rect_of(self._doc, xref)
            if settled is not None and not self._same_box(settled, box):
                self._set_callout_box(xref, settled, inner)
                return self._regenerate(index, xref)
            return True

        return self._edit("Reshape callout", [xref], change)

    def _set_callout_box(self, xref: int, box: "pymupdf.Rect",
                         inner: "pymupdf.Rect") -> None:
        """Set the rectangle and the insets that put the words inside it.

        ``/RD`` is measured inwards from ``/Rect``: left, top, right, bottom.
        """
        self._doc.xref_set_key(xref, "Rect", "[%g %g %g %g]" % tuple(box))
        self._doc.xref_set_key(xref, "RD", "[%g %g %g %g]" % (
            max(inner.x0 - box.x0, 0.0), max(box.y1 - inner.y1, 0.0),
            max(box.x1 - inner.x1, 0.0), max(inner.y0 - box.y0, 0.0)))

    @staticmethod
    def _same_box(one: "pymupdf.Rect", other: "pymupdf.Rect") -> bool:
        return all(abs(a - b) < 0.05 for a, b in zip(tuple(one), tuple(other)))

    def _text_box_of(self, xref: int) -> Optional["pymupdf.Rect"]:
        """Where a free text's words sit: its ``/Rect`` less its ``/RD``."""
        box = geometry.rect_of(self._doc, xref)
        if box is None:
            return None
        try:
            kind, raw = self._doc.xref_get_key(xref, "RD")
            if kind != "array":
                return box
            left, top, right, bottom = (float(v) for v in raw.strip("[]").split())
        except Exception:  # noqa: BLE001
            return box
        inner = pymupdf.Rect(box.x0 + left, box.y0 + bottom,
                             box.x1 - right, box.y1 - top)
        return inner if inner.width > 1 and inner.height > 1 else box

    # -------------------------------------------------------------------- text

    def set_text(self, index: int, xref: int, text: str) -> bool:
        """Rewrite what a text box or a sticky note says."""
        try:
            page = self._doc[index]  # the page must outlive the annotation
            annot = self._find(page, xref)
            if annot is None or annot.type[0] not in TEXT_SUBTYPES:
                return False
        except Exception:  # noqa: BLE001
            _drain_messages()
            return False

        def change() -> bool:
            here = self._doc[index]
            one = self._find(here, xref)
            if one is None:
                return False
            info = one.info
            info["content"] = text
            one.set_info(info)
            return self._regenerate(index, xref)

        return self._edit("Edit text", [xref], change)

    # ------------------------------------------------------------ moving pieces

    def move_markup(self, index: int, xref: int, dx: float, dy: float) -> bool:
        """Shift a markup by ``dx``/``dy`` display points."""
        return self.move_markups(index, {xref: (dx, dy)})

    def move_markups(self, index: int, shifts: dict[int, tuple[float, float]]) -> bool:
        """Move markups, all of it — geometry as well as the box round it.

        Moving only the ``/Rect`` moves what this program draws, because it
        paints the appearance stream, and moves nothing at all in Bluebeam,
        which redraws a cloud from its ``/Vertices``.
        """
        if not shifts:
            return False
        try:
            page = self._doc[index]  # the page must outlive the annotations
            to_pdf = self._to_pdf(page)
        except Exception:  # noqa: BLE001
            _drain_messages()
            return False

        def change() -> bool:
            done = False
            for xref, (dx, dy) in shifts.items():
                # A direction, not a position: only the linear part applies.
                pdf_dx = dx * to_pdf.a + dy * to_pdf.c
                pdf_dy = dx * to_pdf.b + dy * to_pdf.d
                done |= geometry.transform(self._doc, xref,
                                           geometry.move_matrix(pdf_dx, pdf_dy))
            return done

        label = "Move markup" if len(shifts) == 1 else f"Move {len(shifts)} markups"
        return self._edit(label, list(shifts), change)

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
            old = geometry.rect_of(self._doc, xref)
            if old is None or not old.width or not old.height:
                return False
            new = pymupdf.Rect(*(target * page.transformation_matrix)).normalize()
            matrix = geometry.resize_matrix(old, new)
        except Exception:  # noqa: BLE001
            _drain_messages()
            return False

        def change() -> bool:
            if not geometry.transform(self._doc, xref, matrix):
                return False
            # Redrawn from the geometry rather than stretched from the old
            # picture, which is what other editors do too: a cloud resized by
            # stretching its appearance comes out with oval bumps.
            return self._regenerate(index, xref)

        return self._edit("Resize markup", [xref], change)

    def add_rectangle(self, index: int, rect: tuple[float, float, float, float]) -> int:
        """Add a rectangle annotation, given its corners in display points."""
        def draw() -> int:
            page = self._doc[index]
            box = pymupdf.Rect(*rect).normalize() * page.derotation_matrix
            annot = page.add_rect_annot(box)
            annot.set_colors(stroke=RECTANGLE_COLOUR)
            annot.set_border(width=RECTANGLE_WIDTH)
            annot.update()
            return annot.xref

        try:
            xref = draw()
        except Exception as exc:  # noqa: BLE001
            _drain_messages()
            raise DocumentError(f"Could not add the rectangle: {exc}") from exc
        self._record_addition("Draw rectangle", index, xref, draw)
        return xref

    def delete_markups(self, index: int, xrefs: list[int]) -> int:
        """Remove markups from the page."""
        if not xrefs:
            return 0
        # Undo puts the whole page back rather than trying to rebuild an
        # annotation dictionary by hand: a markup is its keys, its appearance
        # stream and whatever else its author put on it, and the page is the
        # one thing that certainly holds all of it.
        before = self._stash_page(index)
        if before is None or not self._remove_annots(index, xrefs):
            return 0
        after = self._stash_page(index)
        if after is None:
            return 0

        # Swapping whole pages both ways, because restoring one gives every
        # markup on it a new xref and there would be nothing left for a redo
        # to name.
        def undo() -> None:
            self._restore_page(index, before)

        def redo() -> None:
            self._restore_page(index, after)

        self.history.record(Step("Delete markup" if len(xrefs) == 1
                                 else f"Delete {len(xrefs)} markups", undo, redo))
        self.modified = True
        return len(xrefs)

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

        def undo() -> None:
            self._doc.delete_page(index)

        def redo() -> None:
            self._doc.new_page(pno=index, width=width, height=height)

        self.history.record(Step("Insert page", undo, redo))

    def delete_page(self, index: int) -> None:
        if self._doc.page_count <= 1:
            raise DocumentError("A PDF must keep at least one page.")
        # The page is set aside in a document of its own so undo can put back
        # what was on it, markups and all, rather than a blank sheet.
        kept = pymupdf.open()
        try:
            kept.insert_pdf(self._doc, from_page=index, to_page=index, annots=True)
            self._doc.delete_page(index)
        except Exception as exc:  # noqa: BLE001
            _drain_messages()
            raise DocumentError(f"Could not delete the page: {exc}") from exc
        self.modified = True

        def undo() -> None:
            self._doc.insert_pdf(kept, start_at=index, annots=True)

        def redo() -> None:
            self._doc.delete_page(index)

        self.history.record(Step("Delete page", undo, redo))

    # ------------------------------------------------------------ undo and redo

    @property
    def can_undo(self) -> bool:
        return self.history.can_undo

    @property
    def can_redo(self) -> bool:
        return self.history.can_redo

    def undo(self) -> Optional[str]:
        label = self.history.undo()
        if label is not None:
            self.modified = True
        return label

    def redo(self) -> Optional[str]:
        label = self.history.redo()
        if label is not None:
            self.modified = True
        return label

    # ---------------------------------------------------------------- internals

    def _edit(self, label: str, xrefs: list[int],
              change: "Callable[[], bool]") -> bool:
        """Run an edit, remembering enough of the markups to take it back."""
        before = {xref: geometry.snapshot(self._doc, xref) for xref in xrefs}
        try:
            done = change()
        except Exception:  # noqa: BLE001
            _drain_messages()
            done = False
        if not done:
            for xref, kept in before.items():
                geometry.restore(self._doc, xref, kept)
            return False
        after = {xref: geometry.snapshot(self._doc, xref) for xref in xrefs}

        def undo() -> None:
            for xref, kept in before.items():
                geometry.restore(self._doc, xref, kept)

        def redo() -> None:
            for xref, kept in after.items():
                geometry.restore(self._doc, xref, kept)

        self.history.record(Step(label, undo, redo))
        self.modified = True
        return True

    def _record_addition(self, label: str, index: int, xref: int,
                         draw: "Callable[[], int]") -> None:
        """Remember a markup that was just drawn.

        Redo draws it again rather than resurrecting the old object, so what
        comes back is a markup this program made from scratch — and the xref it
        gets is the one undo will take away next time.
        """
        made = {"xref": xref}
        self.modified = True

        def undo() -> None:
            self._remove_annots(index, [made["xref"]])

        def redo() -> None:
            try:
                made["xref"] = draw()
            except Exception:  # noqa: BLE001
                _drain_messages()

        self.history.record(Step(label, undo, redo))

    def _stash_page(self, index: int) -> "Optional[pymupdf.Document]":
        """A copy of one page, held aside so undo can put it back."""
        try:
            kept = pymupdf.open()
            kept.insert_pdf(self._doc, from_page=index, to_page=index, annots=True)
            return kept
        except Exception:  # noqa: BLE001
            _drain_messages()
            return None

    def _restore_page(self, index: int, kept: "pymupdf.Document") -> None:
        # Put the copy in first: a PDF cannot be left with no pages at all.
        try:
            self._doc.insert_pdf(kept, start_at=index, annots=True)
            self._doc.delete_page(index + 1)
        except Exception:  # noqa: BLE001
            _drain_messages()

    def _remove_annots(self, index: int, xrefs: list[int]) -> bool:
        try:
            page = self._doc[index]
            wanted = set(xrefs)
            for annot in list(self._annots(page)):
                if annot.xref in wanted:
                    page.delete_annot(annot)
            return True
        except Exception:  # noqa: BLE001
            _drain_messages()
            return False

    def _regenerate(self, index: int, xref: int) -> bool:
        """Redraw a markup from its own numbers, and refuse to lose it.

        MuPDF builds a fresh appearance stream from the annotation's geometry.
        For a markup another program drew that replaces its artwork with
        MuPDF's, which is the price of editing it — but if what comes back is
        blank, the markup has effectively been deleted, and the edit is not
        worth having.
        """
        try:
            page = self._doc[index]  # the page must outlive the annotation
            annot = self._find(page, xref)
            if annot is None:
                return False
            annot.update()
            return self._draws_something(annot)
        except Exception:  # noqa: BLE001
            _drain_messages()
            return False

    @staticmethod
    def _draws_something(annot: "pymupdf.Annot") -> bool:
        try:
            pixmap = annot.get_pixmap(alpha=True)
        except Exception:  # noqa: BLE001
            _drain_messages()
            return False
        if not pixmap.width or not pixmap.height:
            return False
        samples, channels = pixmap.samples, pixmap.n
        return any(samples[i] for i in range(channels - 1, len(samples), channels))

    # ------------------------------------------------------- coordinate frames

    @staticmethod
    def _to_pdf(page: "pymupdf.Page") -> "pymupdf.Matrix":
        """Display points -> PDF user space."""
        return page.derotation_matrix * page.transformation_matrix

    @staticmethod
    def _to_display(page: "pymupdf.Page") -> "pymupdf.Matrix":
        """PDF user space -> display points."""
        return ~pymupdf.Matrix(page.transformation_matrix) * page.rotation_matrix

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
