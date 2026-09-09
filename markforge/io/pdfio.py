"""Importing PDF pages as page backgrounds, and drawing them with MuPDF.

The renderer is :mod:`markforge.pdf.engine`, which is MuPDF. What this module
adds is the Qt end of it — turning a rendered :class:`~markforge.pdf.engine.Raster`
into a ``QImage`` — and the business of bringing PDF pages into a document as
pages of its own.

Coordinates here are display points: the page as it is drawn, with its own
``/Rotate`` applied. A page that says it is turned ninety degrees measures as
the landscape sheet it is, and a markup put at the top-left corner of what is
on screen is at the top-left corner of the page. Getting that wrong is how an
imported drawing comes in sideways, or comes in the right way up with every
markup on it ninety degrees out.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage

from ..core.document import PT_TO_MM, LANDSCAPE, PORTRAIT, Page, PageSetup
from ..pdf import engine
from ..pdf.engine import PdfError

# An A0 sheet at 300 dpi is 140 megapixels, which is more than can usefully be
# allocated and far more than can be looked at. 48 megapixels is A0 at about
# 100 dpi and A4 at 600, which is more than enough to read a drawing.
MAX_PIXELS = 48_000_000

# What an imported page is rendered at, with nobody asked. There is no
# resolution to choose, and there is no longer a resolution to get wrong: the
# page is drawn from the PDF itself at whatever size it is being looked at, so
# what is stored here is only the first thing shown, before the first proper
# draw.
BEST_DPI = 110.0

# Never hand the live renderer more than this many pixels for one page. A
# page filling a large screen at twice the device ratio is about eight
# megapixels; past that the sharpness is beyond anything a screen can show and
# the wait is not.
MOST_LIVE_PIXELS = 16_000_000

FIT_ORIGINAL = "original"       # page takes the PDF page's own size
FIT_A4 = "a4"                   # scale into A4
FIT_CURRENT = "current"         # scale into the document's current page size


def to_image(raster: Optional[engine.Raster]) -> Optional[QImage]:
    """A rendered raster as a QImage that owns its own bytes.

    A QImage built over a buffer does not copy it, and the buffer here is a
    Python ``bytes`` that goes out of scope as soon as this returns — so the
    copy is not optional, it is the difference between a picture and a crash.
    """
    if raster is None or raster.is_empty:
        return None
    # MuPDF's pixmaps with alpha are premultiplied, and read as though they
    # were not every half-transparent pixel comes out too dark — which over a
    # white page is a grey wash across the whole picture.
    shape = (QImage.Format_RGBA8888_Premultiplied if raster.alpha
             else QImage.Format_RGB888)
    image = QImage(raster.samples, raster.width, raster.height,
                   raster.stride, shape)
    return None if image.isNull() else image.copy()


@dataclass
class PdfPageInfo:
    index: int
    width_pt: float
    height_pt: float


class PdfSource:
    """A loaded PDF, ready to render pages into page backgrounds."""

    def __init__(self, path: str):
        self.path = path
        try:
            self.doc = engine.open_path(path)
        except PdfError as exc:
            raise OSError(str(exc)) from exc
        if self.doc.page_count < 1:
            engine.close(self.doc)
            raise OSError(f"{path} has no pages.")
        # MuPDF repairs what it can rather than refusing, which is what makes a
        # damaged drawing openable at all. Whether it had to is worth knowing:
        # a repaired file has no original bytes left to add to, so saving it
        # has to write the whole file again rather than append to it.
        self.repaired = bool(getattr(self.doc, "is_repaired", False))
        self.warnings = engine.drain_messages()

    @property
    def page_count(self) -> int:
        return self.doc.page_count

    def page_info(self, index: int) -> PdfPageInfo:
        width, height = engine.page_size(self.doc, index)
        return PdfPageInfo(index, width, height)

    def render(self, index: int, dpi: float = 150.0) -> Optional[QImage]:
        """One page as a picture, at *dpi* or the most that will fit."""
        info = self.page_info(index)
        scale = self._scale_for(info, dpi)
        return to_image(engine.render_page(
            self.doc, index,
            max(int(round(info.width_pt * scale)), 1),
            max(int(round(info.height_pt * scale)), 1)))

    def render_png(self, index: int, dpi: float = 150.0) -> tuple[bytes, PdfPageInfo]:
        """Render one page to PNG bytes, at *dpi* or the most that will fit.

        A big drawing sheet at a high dpi runs into limits — the image cannot
        be allocated, or it can be allocated but not encoded — and both used to
        end with an empty asset and a page that simply came out blank. The
        request is scaled down to something that will fit, and anything that
        still fails is raised rather than swallowed.
        """
        info = self.page_info(index)
        image = self.render(index, dpi)
        if image is None:
            raise OSError(f"Could not render page {index + 1} of this PDF")
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        if not image.save(buffer, "PNG") or buffer.data().isEmpty():
            raise OSError(f"Page {index + 1} rendered but could not be stored — "
                          "try a lower dpi")
        return bytes(buffer.data()), info

    @staticmethod
    def _scale_for(info: PdfPageInfo, dpi: float) -> float:
        """Points-to-pixels, held under a size that can actually be allocated."""
        scale = max(dpi, 24.0) / 72.0
        pixels = (info.width_pt * scale) * (info.height_pt * scale)
        if pixels > MAX_PIXELS:
            scale *= (MAX_PIXELS / pixels) ** 0.5
        return max(scale, 24.0 / 72.0)

    def close(self) -> None:
        engine.close(self.doc)


class LivePages:
    """The source PDFs a document has pages from, kept open to draw from.

    A page imported from a PDF is not a picture of a drawing, it is the
    drawing, and the file is still there. So it is drawn from the file at the
    size it is being looked at — which is what makes it sharp at any zoom
    instead of a photograph that goes soft as soon as it is enlarged.

    A MuPDF document belongs to the thread that opened it, and this one is
    opened on the window's thread. Tiles are drawn elsewhere and keep their own
    (see :mod:`markforge.io.pdftiles`); what is left here is the whole-page and
    whole-region work that printing and exporting want, which is allowed to
    wait.
    """

    def __init__(self):
        self._open: dict = {}

    def document_for(self, key: str, data: bytes, without: tuple = ()):
        """The document, ready to draw a page that leaves *without* out.

        A document of its own for each set of left-out annotations: leaving
        one out is done by marking it hidden, and there is no reliable way
        back, so a copy that has hidden some is never asked for a page that
        wants them.
        """
        if not key or not data:
            return None
        found = self._open.get((key, tuple(without)))
        if found is not None:
            return found
        try:
            document = engine.open_bytes(data)
        except PdfError:
            return None
        if document.page_count < 1:
            engine.close(document)
            return None
        self._open[(key, tuple(without))] = document
        return document

    def draw(self, key: str, data: bytes, index: int,
             width: int, height: int, annotations: bool = True,
             without: tuple = ()) -> Optional[QImage]:
        """One page at an exact pixel size, or nothing if it cannot be had."""
        document = self.document_for(key, data, without)
        if document is None or not 0 <= index < document.page_count:
            return None
        if without:
            engine.leave_out(document[index], without)
        width = max(int(width), 1)
        height = max(int(height), 1)
        if width * height > MOST_LIVE_PIXELS:
            shrink = (MOST_LIVE_PIXELS / (width * height)) ** 0.5
            width = max(int(width * shrink), 1)
            height = max(int(height * shrink), 1)
        return to_image(engine.render_page(document, index, width, height,
                                           annotations))

    def draw_region(self, key: str, data: bytes, index: int, whole,
                    region, scale: float, annotations: bool = True,
                    without: tuple = ()):
        """Part of a page, drawn at *scale* pixels to the point.

        *whole* and *region* are QRectF in display points. MuPDF clips before
        it rasterises, so the cost is the piece asked for and not the sheet it
        came off.
        """
        document = self.document_for(key, data, without)
        if document is None or not 0 <= index < document.page_count:
            return None
        if without:
            engine.leave_out(document[index], without)
        across = max(int(round(region.width() * scale)), 1)
        down = max(int(round(region.height() * scale)), 1)
        if across * down > MOST_LIVE_PIXELS:
            return None
        return to_image(engine.render_region(
            document, index,
            (region.left(), region.top(), region.right(), region.bottom()),
            scale, annotations))

    def forget(self, key: str = "") -> None:
        if key:
            for held in [k for k in self._open if k[0] == key]:
                engine.close(self._open.pop(held, None))
            return
        for document in self._open.values():
            engine.close(document)
        self._open.clear()


LIVE = LivePages()


# ---------------------------------------------------------------------------
# a page as a picture, when something really needs one
# ---------------------------------------------------------------------------

def page_raster(document, page, dpi: float = BEST_DPI) -> Optional[QImage]:
    """A picture of *page*, however it has to be got.

    Opening a PDF stores no picture of anything — the page is drawn from the
    file. But rotating, recolouring, cropping and redacting all work on a
    raster and always did, so this is where they get one: the stored sheet if
    the page has one, and otherwise a fresh render straight from the source.
    """
    data = document.asset(page.background_key) if page.background_key else None
    if data:
        image = QImage()
        if image.loadFromData(data) and not image.isNull():
            return image
    if page.pdf_key is None or page.pdf_page_index is None:
        return None
    source = document.asset(page.pdf_key)
    if not source:
        return None
    scale = max(dpi, 24.0) / 72.0
    across = max(page.width_pt, 1.0) * scale
    down = max(page.height_pt, 1.0) * scale
    if across * down > MAX_PIXELS:
        shrink = (MAX_PIXELS / (across * down)) ** 0.5
        across, down = across * shrink, down * shrink
    return LIVE.draw(page.pdf_key, source, int(page.pdf_page_index),
                     int(round(across)), int(round(down)),
                     getattr(page, "pdf_annotations", True))


def store_raster(document, image: Optional[QImage]) -> str:
    """Keep *image* in the document as a PNG asset. The key, or empty."""
    if image is None or image.isNull():
        return ""
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    if not image.save(buffer, "PNG") or buffer.data().isEmpty():
        return ""
    return document.add_asset(bytes(buffer.data()), "png")


def ensure_background(document, page, dpi: float = BEST_DPI) -> str:
    """Give *page* a stored sheet of its own, rendering one if it has none.

    For the operations that destroy what the page came from — a redaction, a
    recolour — where the point is that the source must stop being consulted.
    """
    if page.background_key and document.asset(page.background_key):
        return page.background_key
    key = store_raster(document, page_raster(document, page, dpi))
    if key:
        page.background_key = key
    return key


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


# How many pieces of line work are worth bringing across from one page. A
# big drawing can hold hundreds of thousands; past a few thousand the page is
# slower to draw than it is useful, and the picture underneath still shows
# everything.
MOST_STROKES = 6000


def line_work(path: str, indices: list[int]) -> dict[int, list[dict]]:
    """The vector line work of each page, ready to become markups.

    Nothing when the file cannot be read that way. The pages still come in and
    still draw; they simply do not gain geometry to snap to.
    """
    from . import pdfvector

    try:
        source = pdfvector.PdfFile.open(path)
    except Exception:                                  # noqa: BLE001
        return {}
    found: dict[int, list[dict]] = {}
    try:
        for index in indices:
            if not 0 <= index < source.page_count:
                continue
            try:
                strokes = pdfvector.strokes_of_page(source, index)
            except Exception:                          # noqa: BLE001
                continue
            if strokes:
                found[index] = strokes[:MOST_STROKES]
    finally:
        source.close()
    return found


def outline(path: str, indices: list[int]) -> list[tuple[int, str, float, int]]:
    """The PDF's own bookmarks, for the pages being brought in.

    A drawing set's outline is its sheet index — the only practical way round a
    two-hundred-page file — and it is written in the PDF, so opening one should
    hand it over rather than leaving the panel empty beside a document that
    plainly has one.

    Each entry comes back as ``(page index, title, y, level)``, with *y* in
    display points down the page, so it can be hung off whichever page the
    import made. Entries pointing at pages that were not brought in are left
    out: a bookmark that goes to the wrong sheet is worse than one that is
    missing.
    """
    wanted = {index: order for order, index in enumerate(indices)}
    if not wanted:
        return []
    try:
        source = engine.open_path(path)
    except PdfError:
        return []
    found: list[tuple[int, str, float, int]] = []
    try:
        try:
            table = source.get_toc(simple=False)
        except Exception:                              # noqa: BLE001
            engine.drain_messages()
            return []
        for entry in table:
            level, title, page = entry[0], entry[1], entry[2]
            index = int(page) - 1
            if index not in wanted:
                continue
            found.append((index, str(title),
                          _down_the_page(source, index, entry),
                          max(int(level) - 1, 0)))
    finally:
        engine.close(source)
    return found


def _down_the_page(source, index: int, entry) -> float:
    """How far down the page a bookmark points, in display points.

    A PDF destination is written measuring up from the bottom of the sheet,
    but MuPDF has already turned an outline entry's the right way round by the
    time it hands it over — unlike a link's, which comes back as the file
    wrote it. So this takes it as it is; converting again would put every
    bookmark the same distance from the wrong end of the page.
    """
    where = entry[3] if len(entry) > 3 else None
    point = where.get("to") if isinstance(where, dict) else None
    if point is None:
        return 0.0
    try:
        height = engine.page_size(source, index)[1]
        return max(min(float(point.y), height), 0.0)
    except Exception:                                  # noqa: BLE001
        engine.drain_messages()
        return 0.0


def markups(path: str, indices: list[int], keep_the_look: bool = True,
            document=None) -> dict[int, list[dict]]:
    """Each page's annotations, as the markups they are.

    Somebody else's clouds, dimensions and comments come in as markups that can
    be clicked on, moved, replied to and listed — not as a picture of their
    redlines and not as the thousands of loose segments a cloud is drawn with.

    Each markup remembers which annotation it was read out of and stays that
    annotation's until somebody changes it: the page goes on drawing it, so it
    looks exactly the way its own file draws it, at every zoom and for
    nothing. Editing one takes it over — the page leaves that annotation out
    and this application draws the markup instead.
    """
    from . import pdfmarkups, pdfvector

    try:
        source = pdfvector.PdfFile.open(path)
    except Exception:                                  # noqa: BLE001
        return {}

    def picture_of(png: bytes) -> str:
        return document.add_asset(png, "png") if png else ""

    found: dict[int, list[dict]] = {}
    try:
        for index in indices:
            if not 0 <= index < source.page_count:
                continue
            try:
                made = pdfmarkups.markups_of_page(
                    source, index, keep_the_look=keep_the_look,
                    picture_of=picture_of if document is not None else None)
            except Exception:                          # noqa: BLE001
                continue
            if made:
                found[index] = made
    finally:
        source.close()
    return found


def _scaled_markups(payloads: list[dict], scale: float) -> list[dict]:
    """The same markups on differently sized paper.

    A markup that has been resized is no longer where its own annotation is:
    the page would draw the annotation at the size the file has it, over a
    markup at the size the page is now. So a fitted page's markups are ours
    from the start and this application draws them.
    """
    if scale == 1.0:
        return payloads
    moved = []
    for payload in payloads:
        entry = dict(payload)
        entry.pop("still_theirs", None)
        entry.pop("from_annotation", None)
        for key in ("x", "y"):
            if key in entry:
                entry[key] = entry[key] * scale
        if "rect" in entry:
            entry["rect"] = [value * scale for value in entry["rect"]]
        if "points" in entry:
            entry["points"] = [[x * scale, y * scale] for x, y in entry["points"]]
        style = dict(entry.get("style") or {})
        if "width" in style:
            style["width"] = max(style["width"] * scale, 0.1)
        entry["style"] = style
        moved.append(entry)
    return moved


#: What z the page's own line work is given: below every markup, above the
#: sheet the frame itself draws.
DRAWING_Z = -1.0


def _items_from(strokes: list[dict], scale: float = 1.0) -> list[dict]:
    """Strokes as markup payloads: one polyline for each piece of line work.

    Curves are flattened into short straight runs. What this is for is
    snapping, measuring and pointing at — a curve read as eight segments
    measures and snaps the same as one read as a spline, and the picture
    underneath is what is actually looked at.
    """
    items: list[dict] = []
    for stroke in strokes:
        for points in _runs(stroke.get("path") or []):
            if len(points) < 2:
                continue
            xs = [p[0] * scale for p in points]
            ys = [p[1] * scale for p in points]
            left, top = min(xs), min(ys)
            items.append({
                "type": "poly",
                "kind": "polyline",
                "x": left, "y": top,
                "points": [[x - left, y - top] for x, y in zip(xs, ys)],
                "style": {
                    "stroke": stroke.get("stroke") or "#3d4350",
                    "fill": "",
                    "width": max(float(stroke.get("width", 0.6)) * scale, 0.1),
                },
                "from_drawing": True,
                "locked": True,
                # Below everything drawn on the page. It is the page, so
                # "send to back" has to mean behind the other markups rather
                # than underneath the drawing itself, where nothing would be
                # seen of it again.
                "z": DRAWING_Z,
                "uid": os.urandom(8).hex(),
            })
    return items


def _runs(path: list) -> list[list]:
    """One path as separate runs of points, split where the pen lifts."""
    runs: list[list] = []
    current: list = []
    start = None
    for step in path:
        op = step[0]
        if op == "m":
            if len(current) > 1:
                runs.append(current)
            start = [step[1], step[2]]
            current = [list(start)]
        elif op == "l":
            current.append([step[1], step[2]])
        elif op == "c" and len(step) >= 7:
            if not current:
                continue
            here = current[-1]
            for piece in range(1, 9):
                t = piece / 8.0
                current.append(_bezier(here, step[1:3], step[3:5], step[5:7], t))
        elif op == "z":
            if start is not None and current:
                current.append(list(start))
            if len(current) > 1:
                runs.append(current)
            current = [list(start)] if start is not None else []
    if len(current) > 1:
        runs.append(current)
    return runs


def _bezier(a, b, c, d, t: float) -> list:
    """One point along a cubic curve."""
    u = 1.0 - t
    return [u ** 3 * a[0] + 3 * u * u * t * b[0] + 3 * u * t * t * c[0] + t ** 3 * d[0],
            u ** 3 * a[1] + 3 * u * u * t * b[1] + 3 * u * t * t * c[1] + t ** 3 * d[1]]


def import_pages(document, path: str, indices: list[int], fit: str = FIT_ORIGINAL,
                 dpi: float = 150.0, at: Optional[int] = None,
                 vectors: bool = False, annotations: bool = False,
                 bookmarks: bool = True) -> list[Page]:
    """Load the chosen PDF pages into *document* as new pages.

    **What arrives is the PDF.** Every page is drawn from the file itself, by
    MuPDF, at whatever size it is being looked at — so an opened drawing is the
    drawing, pixel for pixel, and stays that way at any zoom. Nothing is
    converted into anything on the way in, and nothing is stored: no picture of
    the page, and no markups of our own standing in for what is already on it.

    The optional imports make objects, both take time, and neither is what
    opening a file should do — so both are off unless something asks:

    *vectors* brings the page's own line work in as real geometry, so a
    measurement can snap to the end of a beam rather than to a guess.
    *annotations* turns markups already on the page into editable ones.
    """
    source = PdfSource(path)
    with open(path, "rb") as handle:
        pdf_key = document.add_asset(handle.read(), "pdf")
    template = document.pages[at - 1].setup if at else (
        document.pages[-1].setup if document.pages else None)
    drawn = line_work(path, indices) if vectors else {}
    marked = markups(path, indices, document=document) if annotations else {}
    created: list[Page] = []
    source_heights: dict[int, float] = {}
    try:
        for offset, index in enumerate(indices):
            info = source.page_info(index)
            source_heights[index] = info.height_pt
            page = Page(setup_for(info, fit, template))
            if index in drawn:
                # The page's own line work, over the picture of it. The page
                # may have been fitted to different paper, so it is scaled the
                # same way the picture is.
                across = info.width_pt or 1.0
                page._pending_items = _items_from(
                    drawn[index], page.setup.width_pt / across)
            if index in marked:
                across = info.width_pt or 1.0
                onto = page.setup.width_pt / across
                page._pending_items = list(page._pending_items) + _scaled_markups(
                    marked[index], onto)
                # Which of the page's annotations became markups. The page
                # goes on drawing them — that is what makes somebody else's
                # drawing look like theirs — and leaves out the ones that have
                # since been taken over or deleted.
                page.markup_annotations = [
                    int(payload["from_annotation"]) for payload in marked[index]
                    if payload.get("from_annotation")]
            page.pdf_key = pdf_key
            page.pdf_page_index = index
            page.source_note = f"{os.path.basename(path)} page {index + 1}"
            # A drawing has its own lines. A grid ruled over the top of it
            # only gets in the way, so a page that came in from a PDF starts
            # without one whatever the rest of the document does.
            page.grid = False
            page.label = page.source_note
            position = None if at is None else at + offset
            if position is None:
                document.pages.append(page)
            else:
                document.pages.insert(position, page)
            created.append(page)
    finally:
        source.close()
    if bookmarks:
        _bring_the_outline(document, path, indices, created, source_heights)
    document.modified = True
    return created


def _bring_the_outline(document, path: str, indices: list[int],
                       created: list[Page], heights: dict[int, float]) -> None:
    """Hang the source PDF's bookmarks off the pages that were made from it.

    Against each page's own id rather than its number, the way every other
    bookmark here is kept, so inserting pages later does not send the sheet
    index to the wrong sheets. Where the page was fitted onto other paper, how
    far down it a bookmark points is scaled the same way the page was.
    """
    from ..core.document import Bookmark

    made = {index: page for index, page in zip(indices, created)}
    for index, title, y, level in outline(path, indices):
        page = made.get(index)
        if page is None:
            continue
        was = heights.get(index) or 0.0
        scale = (page.height_pt / was) if was > 0 else 1.0
        document.bookmarks.append(
            Bookmark(title.strip() or page.label, page.uid, y * scale, level))


def render_preview(path: str, index: int, box: int = 560):
    """A page rendered small, for showing what an import will bring in."""
    source = PdfSource(path)
    try:
        image = to_image(engine.render_thumbnail(source.doc, index, box))
        return image if image is not None else QImage()
    finally:
        source.close()


def page_count(path: str) -> int:
    source = PdfSource(path)
    try:
        return source.page_count
    finally:
        source.close()


def trouble_with(path: str) -> str:
    """What opening this PDF turned up, in a sentence, or nothing.

    A drawing set is full of files that are not quite right — a cross-reference
    table that points at the wrong offsets, a page tree that loops, a stream
    whose length is a lie. MuPDF repairs them and opens them, which is what
    makes the drawing readable at all, and it is still worth saying so once:
    a repaired file has no original bytes left to append to, so saving it
    writes the whole file again rather than adding to it.
    """
    try:
        source = PdfSource(path)
    except OSError:
        return ""
    try:
        if not source.repaired:
            return ""
        return (f"{os.path.basename(path)} had to be repaired to be read. "
                "It opens, but saving will rewrite the whole file rather "
                "than adding to it.")
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
    page.source_note = os.path.basename(path)
    page.grid = False
    page.label = page.source_note
    if at is None:
        document.pages.append(page)
    else:
        document.pages.insert(at, page)
    document.modified = True
    return page
