"""The document model: a PDF held in memory, plus all the edits the editor makes.

Everything that touches the PDF itself lives here, and nothing here imports Qt —
the same split PDF4QT keeps between its rendering library and its applications.
The UI asks this module for images and hands back geometry in *display points*:
PDF user-space units with the page's own ``/Rotate`` already applied, so the
coordinates the user sees on screen are the coordinates used throughout.
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from typing import Callable, Iterator, Optional

import pymupdf

from . import geometry
from .history import History, Step

pymupdf.TOOLS.mupdf_display_errors(False)
pymupdf.TOOLS.mupdf_display_warnings(False)


def _drain_messages() -> str:
    try:
        return pymupdf.TOOLS.mupdf_warnings(reset=True) or ""
    except Exception:
        return ""


HIDDEN_SUBTYPES = frozenset({pymupdf.PDF_ANNOT_POPUP, pymupdf.PDF_ANNOT_LINK})

FIXED_SIZE_SUBTYPES = frozenset({pymupdf.PDF_ANNOT_TEXT,
                                 pymupdf.PDF_ANNOT_FILE_ATTACHMENT,
                                 pymupdf.PDF_ANNOT_SOUND})

TEXT_SUBTYPES = frozenset({pymupdf.PDF_ANNOT_FREE_TEXT, pymupdf.PDF_ANNOT_TEXT})

A4_POINTS = (595.0, 842.0)

MIN_MARKUP_SIZE = 3.0
CALLOUT_PADDING = 2.0

# Default colours for new annotations
RECTANGLE_COLOUR = (0.85, 0.16, 0.16)
LINE_COLOUR = (0.13, 0.45, 0.85)
ELLIPSE_COLOUR = (0.1, 0.6, 0.3)
POLYGON_COLOUR = (0.55, 0.27, 0.07)
CLOUD_COLOUR = (0.85, 0.16, 0.16)
INK_COLOUR = (0.13, 0.13, 0.75)
HIGHLIGHT_COLOUR = (1.0, 0.92, 0.23)
FREETEXT_COLOUR = (0.0, 0.0, 0.0)

DEFAULT_BORDER_WIDTH = 1.5
DEFAULT_OPACITY = 1.0


@dataclass(frozen=True)
class Markup:
    """One annotation on a page, in display points."""

    xref: int
    subtype: str
    subtype_id: int = 0
    x0: float = 0.0
    y0: float = 0.0
    x1: float = 0.0
    y1: float = 0.0
    leader: int = 0
    callout: tuple[tuple[float, float], ...] = ()
    text: str = ""
    resizable: bool = True
    editable_text: bool = False
    colour: tuple[float, ...] = ()
    fill_colour: tuple[float, ...] = ()
    border_width: float = 1.0
    opacity: float = 1.0
    author: str = ""
    created: str = ""
    subject: str = ""
    page_index: int = 0

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
    """A rendered image, ready to be wrapped in a QImage."""

    samples: bytes
    width: int
    height: int
    stride: int
    alpha: bool
    x: int = 0
    y: int = 0


@dataclass
class Bookmark:
    """A PDF outline entry."""
    title: str
    page: int
    level: int = 0


class DocumentError(RuntimeError):
    """A PDF could not be opened or saved."""


class PdfDocument:
    """A PDF opened for editing."""

    def __init__(self) -> None:
        self._doc = pymupdf.open()
        self.path: Optional[str] = None
        self.modified = False
        self.repaired = False
        self.warnings = ""
        self.history = History()

    @property
    def page_count(self) -> int:
        return self._doc.page_count

    @property
    def is_empty(self) -> bool:
        return self._doc.page_count == 0

    def page_size(self, index: int) -> tuple[float, float]:
        try:
            rect = self._doc[index].rect
        except Exception:
            _drain_messages()
            return A4_POINTS
        return rect.width, rect.height

    # ------------------------------------------------------------- open, save

    def open(self, path: str) -> None:
        _drain_messages()
        try:
            doc = pymupdf.open(path, filetype="pdf")
            page_count = doc.page_count
        except Exception as exc:
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
        target = path or self.path
        if target is None:
            raise DocumentError("The document has no file name yet.")
        if self.path and os.path.abspath(target) == os.path.abspath(self.path):
            if not self.repaired and self._save_appended(target):
                return False
            return self._save_rewritten(target)
        try:
            self._doc.save(target)
        except Exception as exc:
            _drain_messages()
            raise DocumentError(f"Could not save {target}: {exc}") from exc
        self.path = target
        self.modified = False
        return False

    def _save_appended(self, target: str) -> bool:
        try:
            self._doc.save(target, incremental=True,
                           encryption=pymupdf.PDF_ENCRYPT_KEEP)
        except Exception:
            _drain_messages()
            return False
        self.modified = False
        return True

    def _save_rewritten(self, target: str) -> bool:
        temporary = target + ".pdf4py-part"
        try:
            self._doc.save(temporary)
            self._doc.close()
        except Exception as exc:
            _drain_messages()
            self._remove(temporary)
            raise DocumentError(f"Could not save {target}: {exc}") from exc
        try:
            os.replace(temporary, target)
        except OSError as exc:
            self._remove(temporary)
            self._doc = pymupdf.open(target)
            raise DocumentError(f"Could not save {target}: {exc}") from exc
        self._doc = pymupdf.open(target)
        self.repaired = False
        self.modified = False
        self.history.clear()
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
        try:
            page = self._doc[index]
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), annots=False)
        except Exception:
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
        except Exception:
            _drain_messages()
            return None
        return Raster(bytes(pixmap.samples), pixmap.width, pixmap.height,
                      pixmap.stride, bool(pixmap.alpha))

    def render_markup(self, index: int, xref: int, zoom: float = 1.0) -> Optional[Raster]:
        try:
            page = self._doc[index]
            annot = self._find(page, xref)
            return None if annot is None else self._raster_for(annot, zoom)
        except Exception:
            _drain_messages()
            return None

    def markups_with_rasters(self, index: int, zoom: float = 1.0
                             ) -> list[tuple[Markup, Optional[Raster]]]:
        try:
            page = self._doc[index]
            rotation = page.rotation_matrix
        except Exception:
            _drain_messages()
            return []
        annot_map: dict[int, tuple[Markup, Optional[Raster]]] = {}
        for annot in self._annots(page):
            try:
                if annot.type[0] in HIDDEN_SUBTYPES:
                    continue
                annot_map[annot.xref] = (self._describe(page, annot, rotation, index),
                                         self._raster_for(annot, zoom))
            except Exception:
                _drain_messages()
        xref_order = self._annot_xref_order(page)
        result = [annot_map[x] for x in xref_order if x in annot_map]
        seen = {m.xref for m, _ in result}
        result.extend(v for x, v in annot_map.items() if x not in seen)
        return result

    @staticmethod
    def _raster_for(annot: "pymupdf.Annot", zoom: float) -> Optional[Raster]:
        try:
            pixmap = annot.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=True)
        except Exception:
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
        except Exception:
            _drain_messages()
            return []
        annot_map: dict[int, Markup] = {}
        for annot in self._annots(page):
            try:
                if annot.type[0] in HIDDEN_SUBTYPES:
                    continue
                annot_map[annot.xref] = self._describe(page, annot, rotation, index)
            except Exception:
                _drain_messages()
        xref_order = self._annot_xref_order(page)
        result = [annot_map[x] for x in xref_order if x in annot_map]
        seen = {m.xref for m in result}
        result.extend(m for x, m in annot_map.items() if x not in seen)
        return result

    def all_markups(self) -> list[Markup]:
        """Every markup in the document, across all pages."""
        result: list[Markup] = []
        for idx in range(self._doc.page_count):
            result.extend(self.markups(idx))
        return result

    def _describe(self, page: "pymupdf.Page", annot: "pymupdf.Annot",
                  rotation: "pymupdf.Matrix", page_index: int = 0) -> Markup:
        kind = annot.type[0]
        rect = annot.rect * rotation
        colours = annot.colors
        stroke = colours.get("stroke", ()) or ()
        fill = colours.get("fill", ()) or ()
        info = annot.info
        border = annot.border
        border_width = border.get("width", 1.0) if border else 1.0
        return Markup(
            xref=annot.xref,
            subtype=annot.type[1],
            subtype_id=kind,
            x0=rect.x0, y0=rect.y0, x1=rect.x1, y1=rect.y1,
            leader=self._leader_of(annot.xref),
            callout=self._callout_of(page, annot.xref),
            text=info.get("content", "") if kind in TEXT_SUBTYPES else "",
            resizable=kind not in FIXED_SIZE_SUBTYPES,
            editable_text=kind in TEXT_SUBTYPES,
            colour=tuple(stroke) if stroke else (),
            fill_colour=tuple(fill) if fill else (),
            border_width=border_width,
            opacity=annot.opacity if annot.opacity >= 0 else 1.0,
            author=info.get("title", ""),
            created=info.get("creationDate", ""),
            subject=info.get("subject", ""),
            page_index=page_index,
        )

    # ------------------------------------------------------------------ groups

    def _leader_of(self, xref: int) -> int:
        try:
            kind, reply_type = self._doc.xref_get_key(xref, "RT")
            if kind != "name" or reply_type.lstrip("/") != "Group":
                return 0
            kind, parent = self._doc.xref_get_key(xref, "IRT")
            if kind != "xref":
                return 0
            return int(parent.split()[0])
        except Exception:
            _drain_messages()
            return 0

    def group_members(self, index: int, xref: int) -> list[int]:
        leader = self._leader_of(xref) or xref
        members = [markup.xref for markup in self.markups(index)
                   if markup.xref == leader or markup.leader == leader]
        return members if len(members) > 1 else [xref]

    def group(self, index: int, xrefs: list[int]) -> bool:
        if len(xrefs) < 2:
            return False
        leader, *rest = xrefs

        def change() -> bool:
            self._doc.xref_set_key(leader, "IRT", "null")
            self._doc.xref_set_key(leader, "RT", "null")
            for xref in rest:
                self._doc.xref_set_key(xref, "IRT", "%d 0 R" % leader)
                self._doc.xref_set_key(xref, "RT", "/Group")
            return True

        return self._edit(f"Group {len(xrefs)} markups", xrefs, change)

    def ungroup(self, index: int, xref: int) -> int:
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
        try:
            kind, raw = self._doc.xref_get_key(xref, "CL")
            if kind != "array":
                return ()
            numbers = [float(value) for value in raw.strip("[]").split()]
        except Exception:
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
        if len(points) not in (2, 3):
            return False
        try:
            page = self._doc[index]
            if self._find(page, xref) is None:
                return False
            to_pdf = self._to_pdf(page)
            leader = [pymupdf.Point(x, y) * to_pdf for x, y in points]
            inner = self._text_box_of(xref)
            if inner is None:
                return False
        except Exception:
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
            settled = geometry.rect_of(self._doc, xref)
            if settled is not None and not self._same_box(settled, box):
                self._set_callout_box(xref, settled, inner)
                return self._regenerate(index, xref)
            return True

        return self._edit("Reshape callout", [xref], change)

    def _set_callout_box(self, xref: int, box: "pymupdf.Rect",
                         inner: "pymupdf.Rect") -> None:
        self._doc.xref_set_key(xref, "Rect", "[%g %g %g %g]" % tuple(box))
        self._doc.xref_set_key(xref, "RD", "[%g %g %g %g]" % (
            max(inner.x0 - box.x0, 0.0), max(box.y1 - inner.y1, 0.0),
            max(box.x1 - inner.x1, 0.0), max(inner.y0 - box.y0, 0.0)))

    @staticmethod
    def _same_box(one: "pymupdf.Rect", other: "pymupdf.Rect") -> bool:
        return all(abs(a - b) < 0.05 for a, b in zip(tuple(one), tuple(other)))

    def _text_box_of(self, xref: int) -> Optional["pymupdf.Rect"]:
        box = geometry.rect_of(self._doc, xref)
        if box is None:
            return None
        try:
            kind, raw = self._doc.xref_get_key(xref, "RD")
            if kind != "array":
                return box
            left, top, right, bottom = (float(v) for v in raw.strip("[]").split())
        except Exception:
            return box
        inner = pymupdf.Rect(box.x0 + left, box.y0 + bottom,
                             box.x1 - right, box.y1 - top)
        return inner if inner.width > 1 and inner.height > 1 else box

    # -------------------------------------------------------------------- text

    def set_text(self, index: int, xref: int, text: str) -> bool:
        try:
            page = self._doc[index]
            annot = self._find(page, xref)
            if annot is None or annot.type[0] not in TEXT_SUBTYPES:
                return False
        except Exception:
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

    # --------------------------------------------------------- markup properties

    def set_markup_colour(self, index: int, xref: int,
                          stroke: Optional[tuple[float, ...]] = None,
                          fill: Optional[tuple[float, ...]] = None) -> bool:
        """Change a markup's stroke and/or fill colour."""
        try:
            page = self._doc[index]
            annot = self._find(page, xref)
            if annot is None:
                return False
        except Exception:
            _drain_messages()
            return False

        def change() -> bool:
            here = self._doc[index]
            one = self._find(here, xref)
            if one is None:
                return False
            colours = {}
            if stroke is not None:
                colours["stroke"] = stroke
            if fill is not None:
                colours["fill"] = fill
            one.set_colors(**colours)
            return self._regenerate(index, xref)

        return self._edit("Change colour", [xref], change)

    def set_markup_border_width(self, index: int, xref: int, width: float) -> bool:
        try:
            page = self._doc[index]
            annot = self._find(page, xref)
            if annot is None:
                return False
        except Exception:
            _drain_messages()
            return False

        def change() -> bool:
            here = self._doc[index]
            one = self._find(here, xref)
            if one is None:
                return False
            one.set_border(width=width)
            return self._regenerate(index, xref)

        return self._edit("Change border width", [xref], change)

    def set_markup_opacity(self, index: int, xref: int, opacity: float) -> bool:
        try:
            page = self._doc[index]
            annot = self._find(page, xref)
            if annot is None:
                return False
        except Exception:
            _drain_messages()
            return False

        def change() -> bool:
            here = self._doc[index]
            one = self._find(here, xref)
            if one is None:
                return False
            one.set_opacity(max(0.0, min(1.0, opacity)))
            return self._regenerate(index, xref)

        return self._edit("Change opacity", [xref], change)

    # ------------------------------------------------------------ moving pieces

    def move_markup(self, index: int, xref: int, dx: float, dy: float) -> bool:
        return self.move_markups(index, {xref: (dx, dy)})

    def move_markups(self, index: int, shifts: dict[int, tuple[float, float]]) -> bool:
        if not shifts:
            return False
        try:
            page = self._doc[index]
            to_pdf = self._to_pdf(page)
        except Exception:
            _drain_messages()
            return False

        def change() -> bool:
            done = False
            for xref, (dx, dy) in shifts.items():
                pdf_dx = dx * to_pdf.a + dy * to_pdf.c
                pdf_dy = dx * to_pdf.b + dy * to_pdf.d
                done |= geometry.transform(self._doc, xref,
                                           geometry.move_matrix(pdf_dx, pdf_dy))
            return done

        label = "Move markup" if len(shifts) == 1 else f"Move {len(shifts)} markups"
        return self._edit(label, list(shifts), change)

    def resize_markup(self, index: int, xref: int,
                      rect: tuple[float, float, float, float]) -> bool:
        try:
            page = self._doc[index]
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
        except Exception:
            _drain_messages()
            return False

        def change() -> bool:
            if not geometry.transform(self._doc, xref, matrix):
                return False
            return self._regenerate(index, xref)

        return self._edit("Resize markup", [xref], change)

    # ---------------------------------------------------------- annotation ordering

    def bring_to_front(self, index: int, xref: int) -> bool:
        """Move an annotation to the end of the page's annotation list (top)."""
        before = self._stash_page(index)
        if before is None:
            return False
        try:
            page = self._doc[index]
            annot_xrefs = self._annot_xref_order(page)
            if xref not in annot_xrefs or annot_xrefs[-1] == xref:
                return False
            annot_xrefs.remove(xref)
            annot_xrefs.append(xref)
            self._reorder_annots(page, annot_xrefs)
        except Exception:
            _drain_messages()
            return False
        after = self._stash_page(index)
        if after is None:
            return False
        self._record_page_swap("Bring to front", index, before, after)
        return True

    def send_to_back(self, index: int, xref: int) -> bool:
        """Move an annotation to the start of the page's annotation list (bottom)."""
        before = self._stash_page(index)
        if before is None:
            return False
        try:
            page = self._doc[index]
            annot_xrefs = self._annot_xref_order(page)
            if xref not in annot_xrefs or annot_xrefs[0] == xref:
                return False
            annot_xrefs.remove(xref)
            annot_xrefs.insert(0, xref)
            self._reorder_annots(page, annot_xrefs)
        except Exception:
            _drain_messages()
            return False
        after = self._stash_page(index)
        if after is None:
            return False
        self._record_page_swap("Send to back", index, before, after)
        return True

    def _reorder_annots(self, page: "pymupdf.Page", xref_order: list[int]) -> None:
        """Rewrite the page's /Annots array in the given order."""
        refs = " ".join(f"{x} 0 R" for x in xref_order)
        page_xref = page.xref
        self._doc.xref_set_key(page_xref, "Annots", f"[{refs}]")

    def _annot_xref_order(self, page: "pymupdf.Page") -> list[int]:
        """Read the raw /Annots array and return xrefs in order."""
        try:
            kind, val = self._doc.xref_get_key(page.xref, "Annots")
            if kind != "array":
                return []
            return [int(m) for m in re.findall(r'(\d+)\s+0\s+R', val)]
        except Exception:
            return []

    # --------------------------------------------------------- drawing new annotations

    def add_rectangle(self, index: int, rect: tuple[float, float, float, float],
                      colour: tuple[float, ...] = RECTANGLE_COLOUR,
                      width: float = DEFAULT_BORDER_WIDTH) -> int:
        def draw() -> int:
            page = self._doc[index]
            box = pymupdf.Rect(*rect).normalize() * page.derotation_matrix
            annot = page.add_rect_annot(box)
            annot.set_colors(stroke=colour)
            annot.set_border(width=width)
            annot.update()
            return annot.xref

        try:
            xref = draw()
        except Exception as exc:
            _drain_messages()
            raise DocumentError(f"Could not add the rectangle: {exc}") from exc
        self._record_addition("Draw rectangle", index, xref, draw)
        return xref

    def add_line(self, index: int, p1: tuple[float, float],
                 p2: tuple[float, float],
                 colour: tuple[float, ...] = LINE_COLOUR,
                 width: float = DEFAULT_BORDER_WIDTH,
                 end_style: str = "none") -> int:
        def draw() -> int:
            page = self._doc[index]
            a = pymupdf.Point(*p1) * page.derotation_matrix
            b = pymupdf.Point(*p2) * page.derotation_matrix
            annot = page.add_line_annot(a, b)
            annot.set_colors(stroke=colour)
            annot.set_border(width=width)
            if end_style == "arrow":
                annot.set_line_ends(pymupdf.PDF_ANNOT_LE_NONE,
                                    pymupdf.PDF_ANNOT_LE_OPEN_ARROW)
            annot.update()
            return annot.xref

        try:
            xref = draw()
        except Exception as exc:
            _drain_messages()
            raise DocumentError(f"Could not add the line: {exc}") from exc
        label = "Draw arrow" if end_style == "arrow" else "Draw line"
        self._record_addition(label, index, xref, draw)
        return xref

    def add_ellipse(self, index: int, rect: tuple[float, float, float, float],
                    colour: tuple[float, ...] = ELLIPSE_COLOUR,
                    width: float = DEFAULT_BORDER_WIDTH) -> int:
        def draw() -> int:
            page = self._doc[index]
            box = pymupdf.Rect(*rect).normalize() * page.derotation_matrix
            annot = page.add_circle_annot(box)
            annot.set_colors(stroke=colour)
            annot.set_border(width=width)
            annot.update()
            return annot.xref

        try:
            xref = draw()
        except Exception as exc:
            _drain_messages()
            raise DocumentError(f"Could not add the ellipse: {exc}") from exc
        self._record_addition("Draw ellipse", index, xref, draw)
        return xref

    def add_polygon(self, index: int, points: list[tuple[float, float]],
                    colour: tuple[float, ...] = POLYGON_COLOUR,
                    width: float = DEFAULT_BORDER_WIDTH,
                    cloud: bool = False) -> int:
        if len(points) < 3:
            raise DocumentError("A polygon needs at least three points.")

        def draw() -> int:
            page = self._doc[index]
            pdf_points = [pymupdf.Point(*p) * page.derotation_matrix for p in points]
            annot = page.add_polygon_annot(pdf_points)
            annot.set_colors(stroke=colour)
            annot.set_border(width=width)
            if cloud:
                annot.set_border(width=width)
                try:
                    self._doc.xref_set_key(annot.xref, "BE", "<</S /C /I 1>>")
                except Exception:
                    pass
            annot.update()
            return annot.xref

        try:
            xref = draw()
        except Exception as exc:
            _drain_messages()
            raise DocumentError(f"Could not add the polygon: {exc}") from exc
        label = "Draw cloud" if cloud else "Draw polygon"
        self._record_addition(label, index, xref, draw)
        return xref

    def add_cloud(self, index: int, rect: tuple[float, float, float, float],
                  colour: tuple[float, ...] = CLOUD_COLOUR,
                  width: float = DEFAULT_BORDER_WIDTH) -> int:
        """Add a revision cloud (rectangle with cloudy border)."""
        def draw() -> int:
            page = self._doc[index]
            box = pymupdf.Rect(*rect).normalize() * page.derotation_matrix
            annot = page.add_rect_annot(box)
            annot.set_colors(stroke=colour)
            annot.set_border(width=width)
            try:
                self._doc.xref_set_key(annot.xref, "BE", "<</S /C /I 2>>")
            except Exception:
                pass
            annot.update()
            return annot.xref

        try:
            xref = draw()
        except Exception as exc:
            _drain_messages()
            raise DocumentError(f"Could not add the cloud: {exc}") from exc
        self._record_addition("Draw cloud", index, xref, draw)
        return xref

    def add_ink(self, index: int, strokes: list[list[tuple[float, float]]],
                colour: tuple[float, ...] = INK_COLOUR,
                width: float = 2.0) -> int:
        if not strokes:
            raise DocumentError("No ink strokes to add.")

        def draw() -> int:
            page = self._doc[index]
            pdf_strokes = []
            for stroke in strokes:
                pdf_strokes.append(
                    [list(pymupdf.Point(*p) * page.derotation_matrix) for p in stroke])
            annot = page.add_ink_annot(pdf_strokes)
            annot.set_colors(stroke=colour)
            annot.set_border(width=width)
            annot.update()
            return annot.xref

        try:
            xref = draw()
        except Exception as exc:
            _drain_messages()
            raise DocumentError(f"Could not add the ink: {exc}") from exc
        self._record_addition("Draw ink", index, xref, draw)
        return xref

    def add_highlight(self, index: int, rect: tuple[float, float, float, float],
                      colour: tuple[float, ...] = HIGHLIGHT_COLOUR) -> int:
        def draw() -> int:
            page = self._doc[index]
            box = pymupdf.Rect(*rect).normalize() * page.derotation_matrix
            quads = [box.quad]
            annot = page.add_highlight_annot(quads=quads)
            annot.set_colors(stroke=colour)
            annot.set_opacity(0.4)
            annot.update()
            return annot.xref

        try:
            xref = draw()
        except Exception as exc:
            _drain_messages()
            raise DocumentError(f"Could not add the highlight: {exc}") from exc
        self._record_addition("Highlight", index, xref, draw)
        return xref

    def add_freetext(self, index: int, rect: tuple[float, float, float, float],
                     text: str = "Text",
                     fontsize: float = 12.0,
                     colour: tuple[float, ...] = FREETEXT_COLOUR) -> int:
        def draw() -> int:
            page = self._doc[index]
            box = pymupdf.Rect(*rect).normalize() * page.derotation_matrix
            annot = page.add_freetext_annot(box, text, fontsize=fontsize,
                                            text_color=colour)
            annot.update()
            return annot.xref

        try:
            xref = draw()
        except Exception as exc:
            _drain_messages()
            raise DocumentError(f"Could not add the text: {exc}") from exc
        self._record_addition("Add text", index, xref, draw)
        return xref

    def add_note(self, index: int, point: tuple[float, float],
                 text: str = "Note") -> int:
        def draw() -> int:
            page = self._doc[index]
            pt = pymupdf.Point(*point) * page.derotation_matrix
            annot = page.add_text_annot(pt, text)
            annot.update()
            return annot.xref

        try:
            xref = draw()
        except Exception as exc:
            _drain_messages()
            raise DocumentError(f"Could not add the note: {exc}") from exc
        self._record_addition("Add note", index, xref, draw)
        return xref

    def delete_markups(self, index: int, xrefs: list[int]) -> int:
        if not xrefs:
            return 0
        before = self._stash_page(index)
        if before is None or not self._remove_annots(index, xrefs):
            return 0
        after = self._stash_page(index)
        if after is None:
            return 0

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
        if self._doc.page_count:
            neighbour = min(max(index - 1, 0), self._doc.page_count - 1)
            width, height = self.page_size(neighbour)
        else:
            width, height = A4_POINTS
        try:
            self._doc.new_page(pno=index, width=width, height=height)
        except Exception as exc:
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
        kept = pymupdf.open()
        try:
            kept.insert_pdf(self._doc, from_page=index, to_page=index, annots=True)
            self._doc.delete_page(index)
        except Exception as exc:
            _drain_messages()
            raise DocumentError(f"Could not delete the page: {exc}") from exc
        self.modified = True

        def undo() -> None:
            self._doc.insert_pdf(kept, start_at=index, annots=True)

        def redo() -> None:
            self._doc.delete_page(index)

        self.history.record(Step("Delete page", undo, redo))

    def rotate_page(self, index: int, angle: int = 90) -> None:
        """Rotate a page by 90, 180, or 270 degrees clockwise."""
        if angle not in (90, 180, 270):
            raise DocumentError("Rotation must be 90, 180, or 270 degrees.")
        try:
            page = self._doc[index]
            old_rotation = page.rotation
            new_rotation = (old_rotation + angle) % 360
            page.set_rotation(new_rotation)
        except Exception as exc:
            _drain_messages()
            raise DocumentError(f"Could not rotate the page: {exc}") from exc
        self.modified = True

        def undo() -> None:
            self._doc[index].set_rotation(old_rotation)

        def redo() -> None:
            self._doc[index].set_rotation(new_rotation)

        self.history.record(Step(f"Rotate page {angle}°", undo, redo))

    # ---------------------------------------------------------------- bookmarks

    def bookmarks(self) -> list[Bookmark]:
        """Read the PDF's outline tree as a flat list."""
        result: list[Bookmark] = []
        try:
            toc = self._doc.get_toc(simple=True)
            for level, title, page in toc:
                result.append(Bookmark(title=title, page=max(page - 1, 0), level=level))
        except Exception:
            _drain_messages()
        return result

    def set_bookmarks(self, bookmarks: list[Bookmark]) -> None:
        """Rewrite the PDF outline."""
        toc = [[bm.level, bm.title, bm.page + 1] for bm in bookmarks]
        try:
            self._doc.set_toc(toc)
        except Exception as exc:
            _drain_messages()
            raise DocumentError(f"Could not set bookmarks: {exc}") from exc
        self.modified = True

    def add_bookmark(self, title: str, page: int) -> None:
        bmarks = self.bookmarks()
        bmarks.append(Bookmark(title=title, page=page, level=1))
        self.set_bookmarks(bmarks)

    def remove_bookmark(self, index: int) -> None:
        bmarks = self.bookmarks()
        if 0 <= index < len(bmarks):
            bmarks.pop(index)
            self.set_bookmarks(bmarks)

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
        before = {xref: geometry.snapshot(self._doc, xref) for xref in xrefs}
        try:
            done = change()
        except Exception:
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
        made = {"xref": xref}
        self.modified = True

        def undo() -> None:
            self._remove_annots(index, [made["xref"]])

        def redo() -> None:
            try:
                made["xref"] = draw()
            except Exception:
                _drain_messages()

        self.history.record(Step(label, undo, redo))

    def _record_page_swap(self, label: str, index: int,
                          before: "pymupdf.Document",
                          after: "pymupdf.Document") -> None:
        def undo() -> None:
            self._restore_page(index, before)

        def redo() -> None:
            self._restore_page(index, after)

        self.history.record(Step(label, undo, redo))
        self.modified = True

    def _stash_page(self, index: int) -> "Optional[pymupdf.Document]":
        try:
            kept = pymupdf.open()
            kept.insert_pdf(self._doc, from_page=index, to_page=index, annots=True)
            return kept
        except Exception:
            _drain_messages()
            return None

    def _restore_page(self, index: int, kept: "pymupdf.Document") -> None:
        try:
            self._doc.insert_pdf(kept, start_at=index, annots=True)
            self._doc.delete_page(index + 1)
        except Exception:
            _drain_messages()

    def _remove_annots(self, index: int, xrefs: list[int]) -> bool:
        try:
            page = self._doc[index]
            wanted = set(xrefs)
            for annot in list(self._annots(page)):
                if annot.xref in wanted:
                    page.delete_annot(annot)
            return True
        except Exception:
            _drain_messages()
            return False

    def _regenerate(self, index: int, xref: int) -> bool:
        try:
            page = self._doc[index]
            annot = self._find(page, xref)
            if annot is None:
                return False
            annot.update()
            return self._draws_something(annot)
        except Exception:
            _drain_messages()
            return False

    @staticmethod
    def _draws_something(annot: "pymupdf.Annot") -> bool:
        try:
            pixmap = annot.get_pixmap(alpha=True)
        except Exception:
            _drain_messages()
            return False
        if not pixmap.width or not pixmap.height:
            return False
        samples, channels = pixmap.samples, pixmap.n
        return any(samples[i] for i in range(channels - 1, len(samples), channels))

    @staticmethod
    def _to_pdf(page: "pymupdf.Page") -> "pymupdf.Matrix":
        return page.derotation_matrix * page.transformation_matrix

    @staticmethod
    def _to_display(page: "pymupdf.Page") -> "pymupdf.Matrix":
        return ~pymupdf.Matrix(page.transformation_matrix) * page.rotation_matrix

    @staticmethod
    def _annots(page: "pymupdf.Page") -> Iterator["pymupdf.Annot"]:
        try:
            annot = page.first_annot
        except Exception:
            _drain_messages()
            return
        while annot is not None:
            yield annot
            try:
                annot = annot.next
            except Exception:
                _drain_messages()
                return

    def _find(self, page: "pymupdf.Page", xref: int) -> Optional["pymupdf.Annot"]:
        for annot in self._annots(page):
            if annot.xref == xref:
                return annot
        return None
