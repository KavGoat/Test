"""Drawing PDF pages the way a PDF reader does: in tiles, off the main thread.

The problem this solves is the one every PDF viewer has. A drawing sheet is
enormous — an A1 page at the zoom somebody actually reads a detail at is
hundreds of megapixels — so the page cannot be rendered as one picture, and it
certainly cannot be rendered while the window is trying to repaint. Do it that
way and the sheet is either blurred, because the render had to be shrunk to
something that would fit, or the window stops dead every time it scrolls.

So, the same arrangement PDF4QT uses, and Chrome's viewer, and every other
reader worth using:

* **Tiles.** The page is cut into squares of a fixed size in *screen* pixels.
  Only the squares on screen are ever drawn, so the cost of a repaint depends
  on the size of the window and not on the size of the sheet.

* **A zoom ladder.** Tiles are rendered at powers of two, not at whatever the
  zoom happens to be, so a wheel notch reuses what is already drawn and a real
  zoom change costs one round of rendering rather than fifty.

* **A background thread.** Nothing is rendered on the thread that paints. A
  repaint draws the tiles that are ready and asks for the ones that are not;
  when one arrives it says so and that part of the page is repainted. The
  window never waits.

* **A thumbnail underneath.** One small picture of each whole page, kept, and
  drawn stretched under the tiles. It is what fills the gap while tiles are
  still coming, so a page is never blank and never shows a hole — it starts
  soft and sharpens, rather than starting empty. It is only ever the gap
  filler: tiles are rendered at every zoom, including zoomed right out, so
  what settles is always drawn at the resolution the screen is showing and
  never a small picture stretched over a big sheet.

* **A cache with a ceiling.** Tiles are kept for as long as there is room and
  the least recently wanted are dropped first, so zooming back out and
  scrolling back up are instant, and the memory does not grow without end.

Printing and exporting do not come through here. They want the whole page at
one resolution, right now, and they are allowed to wait — that is
:func:`markforge.io.pdfio.LivePages.draw_region`.

The renderer is MuPDF, through :mod:`markforge.pdf.engine`. A MuPDF document
belongs to the thread that opened it, so the worker below opens its own from
the same bytes rather than sharing the one the window draws with — which is
the same arrangement the Qt renderer needed, for the same reason.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import atexit
import threading

from PySide6.QtCore import (QCoreApplication, QObject, QRectF, Qt, QThread,
                            Signal)
from PySide6.QtGui import QImage, QPixmap

from ..pdf import engine
from ..pdf.engine import PdfError

#: How big a tile is, in screen pixels.
#:
#: Bigger than it looks like it should be, and measured rather than guessed.
#: What a tile costs is mostly walking the page's drawing — forty thousand
#: paths on a dense A1 sheet — and that is paid once per tile whatever size it
#: is, because clipping decides what to rasterise and not what to walk. So
#: cutting the screen into more, smaller squares pays the expensive part more
#: often. Covering a window at 1024 is roughly forty per cent quicker than at
#: 512 across every zoom; 2048 gives it back again in rasterising.
TILE = 1024

#: The longest edge of the small picture kept of a whole page.
THUMBNAIL_EDGE = 1100

#: How much of the tile cache to keep, in bytes of image. Roughly forty
#: A1-sized screenfuls, and a hard ceiling rather than a hope.
CACHE_BYTES = 192 * 1024 * 1024

#: The most tiles one repaint will ask for. A screenful is about a dozen, so
#: this is several screenfuls of margin and still a bound: past it the answers
#: arrive long after the zoom that wanted them has moved on.
MOST_TILES_AT_ONCE = 48

#: How many whole-page pictures to have in hand at once. Enough for the sheet
#: being read and its neighbours; the rest follow as each one arriving repaints
#: the canvas and asks for the next.
MOST_SHEETS_AT_ONCE = 4

#: How many pages to keep parsed on the render thread. A display list of a
#: dense A1 sheet is a few megabytes; a handful covers the page being read and
#: its neighbours, which is what scrolling touches.
MOST_HELD_PAGES = 8


def zoom_step(scale: float) -> float:
    """The rung of the ladder at or above *scale*.

    Rendering at exactly the zoom on screen would mean re-rendering on every
    notch of the wheel. Rendering at the next power of two up means a zoom is
    one round of work, and never gives back less resolution than the screen is
    showing.
    """
    step = 0.25
    while step < scale and step < 64.0:
        step *= 2.0
    return step


@dataclass(frozen=True)
class TileKey:
    """One square of one page at one rung of the zoom ladder."""
    source: str
    index: int
    scale: float
    col: int
    row: int
    annotations: bool
    #: The page's own annotations to leave out, because this application has
    #: taken them over and is drawing them itself.
    without: tuple = ()

    def page_rect(self, pixels=None) -> QRectF:
        """Where this tile belongs on the page, in points.

        The tiles at the right-hand edge and along the bottom are the part of
        a tile that fits, and are that much narrower or shorter than the rest.
        Given the picture, this says the size it really is — without which an
        edge tile gets stretched across a whole tile's worth of page, which
        looks exactly like the right-hand strip of the sheet being smeared.
        """
        size = TILE / self.scale
        left, top = self.col * size, self.row * size
        if pixels is None:
            return QRectF(left, top, size, size)
        return QRectF(left, top, pixels.width() / self.scale,
                      pixels.height() / self.scale)


@dataclass(frozen=True)
class SheetKey:
    """The small picture of a whole page."""
    source: str
    index: int
    annotations: bool
    #: The page's own annotations to leave out — see :class:`TileKey`.
    without: tuple = ()


class _Worker(QThread):
    """Renders on its own thread, taking work off a stack.

    Deliberately a stack and not queued slot calls: handing Python objects
    across threads through Qt's meta-object system is a way to crash, and
    there is nothing here that needs it. What crosses back is a signal, which
    Qt delivers on the window's thread by itself.

    **A stack, not a queue.** What was asked for most recently is what is on
    screen now, and what was asked for a second ago may be the same page at a
    zoom nobody is looking at any more. Rendering in the order the requests
    arrived means every zoom is served only after the whole of the previous
    zoom has been drawn — which is what made zooming into a dense sheet take
    ten seconds and then fifteen. Newest first, and anything nobody still
    wants is dropped rather than drawn.

    The thread keeps its own MuPDF document for each source, because a document
    belongs to the thread that opened it, and a display list for each page it
    has drawn: a page is parsed once and its tiles are rasterised from that
    rather than running the content stream again for every square.
    """

    tileDone = Signal(object, QImage)
    sheetDone = Signal(object, QImage)

    def __init__(self, wanted: "Optional[set]" = None) -> None:
        super().__init__()
        self._work: list = []                # a stack; the newest is on top
        self._lock = threading.Lock()
        self._ready = threading.Semaphore(0)
        self._open: dict[str, object] = {}
        self._lists: "dict[tuple, object]" = {}
        self._wanted = wanted if wanted is not None else set()
        self._stopping = False

    def submit(self, key, data: bytes, width: float, height: float) -> None:
        with self._lock:
            self._work.append((key, data, width, height))
        self._ready.release()

    def stop(self) -> None:
        self._stopping = True
        with self._lock:
            self._work.append(None)
        self._ready.release()

    def drop(self, source: str) -> None:
        self.submit("forget", source, 0.0, 0.0)

    def _next(self):
        """The most recent piece of work still worth doing."""
        while True:
            self._ready.acquire()
            with self._lock:
                if not self._work:
                    continue
                job = self._work.pop()
            if job is None or job[0] == "forget":
                return job
            # Asked for, then superseded before the thread got to it. Skipping
            # here is the whole point of the stack: the answer would be thrown
            # away the moment it arrived.
            if job[0] in self._wanted:
                return job

    def run(self) -> None:
        while True:
            job = self._next()
            if job is None:
                break
            key, data, width, height = job
            if key == "forget":
                for held in [k for k in self._open if k[0] == data]:
                    engine.close(self._open.pop(held, None))
                for held in [k for k in self._lists if k[0] == data]:
                    self._lists.pop(held, None)
                continue
            try:
                if isinstance(key, SheetKey):
                    self._sheet(key, data, width, height)
                else:
                    self._tile(key, data, width, height)
            except Exception:                              # noqa: BLE001
                # A source that cannot be drawn must not take the thread down
                # with it, or every page after it stops appearing.
                signal = (self.sheetDone if isinstance(key, SheetKey)
                          else self.tileDone)
                signal.emit(key, QImage())
        self._lists.clear()
        for document in self._open.values():
            engine.close(document)
        self._open.clear()

    def _document(self, source, data: bytes):
        found = self._open.get(source)
        if found is not None:
            return found
        try:
            document = engine.open_bytes(data)
        except PdfError:
            return None
        if document.page_count < 1:
            engine.close(document)
            return None
        if len(self._open) >= MOST_HELD_PAGES:
            engine.close(self._open.pop(next(iter(self._open))))
        self._open[source] = document
        return document

    def _display_list(self, source: str, data: bytes, index: int,
                      annotations: bool, without: tuple = ()):
        """The page, parsed once, ready to be rasterised any number of times.

        A dense drawing sheet is tens of thousands of path operations, and
        asking the page for a square of itself runs all of them again. Held as
        a display list they are run once and every tile after that is only
        rasterising.
        """
        key = (source, index, annotations, without)
        found = self._lists.get(key)
        if found is not None:
            return found
        # A document of its own for each set of left-out annotations. Leaving
        # one out is done by setting its hidden flag, and a flag put back
        # again does not always give back what was there before — so the
        # answer is never to put one back: each set gets a clean copy.
        document = self._document((source, without), data)
        if document is None or not 0 <= index < document.page_count:
            return None
        made = engine.display_list(document, index, annotations, without)
        if made is None:
            return None
        if len(self._lists) >= MOST_HELD_PAGES:
            self._lists.pop(next(iter(self._lists)), None)
        self._lists[key] = made
        return made

    def _tile(self, key: "TileKey", data: bytes,
              page_width: float, page_height: float) -> None:
        from .pdfio import to_image

        drawing = self._display_list(key.source, data, key.index,
                                     key.annotations, key.without)
        if drawing is None:
            self.tileDone.emit(key, QImage())
            return
        # Where this tile is on the page, in points. The last tile in a row or
        # column is the part of one that fits, and asking for more than the
        # page has would stretch its edge across the difference.
        size = TILE / key.scale
        left, top = key.col * size, key.row * size
        right = min(left + size, page_width)
        bottom = min(top + size, page_height)
        if right - left <= 0 or bottom - top <= 0:
            self.tileDone.emit(key, QImage())
            return
        image = to_image(engine.raster_from(
            drawing, (left, top, right, bottom), key.scale))
        self.tileDone.emit(key, image if image is not None else QImage())

    def _sheet(self, key: "SheetKey", data: bytes,
               page_width: float, page_height: float) -> None:
        from .pdfio import to_image

        drawing = self._display_list(key.source, data, key.index,
                                     key.annotations, key.without)
        if drawing is None:
            self.sheetDone.emit(key, QImage())
            return
        longest = max(page_width, page_height, 1.0)
        shrink = min(THUMBNAIL_EDGE / longest, 4.0)
        image = to_image(engine.raster_from(
            drawing, (0.0, 0.0, page_width, page_height), shrink))
        self.sheetDone.emit(key, image if image is not None else QImage())


class TileCache(QObject):
    """What has been drawn, and what has been asked for.

    Lives on the window's thread. Hands out pixmaps, and says — by signal —
    when something that was not ready is.
    """

    tileReady = Signal(object)      # TileKey
    sheetReady = Signal(object)     # SheetKey

    def __init__(self) -> None:
        super().__init__()
        self._tiles: dict[TileKey, QPixmap] = {}
        self._sheets: dict[SheetKey, QPixmap] = {}
        # Shared with the worker, which reads it to decide whether a job it is
        # about to start is still worth doing. A set of immutable keys, added
        # to and discarded from on this thread only, so the worker never sees
        # half a change.
        self._waiting: set = set()
        self._held = 0
        self._worker: Optional[_Worker] = None
        self._farewell = False

    # -- the thread --------------------------------------------------------
    def _started(self) -> _Worker:
        if self._worker is not None:
            return self._worker
        worker = _Worker(self._waiting)
        worker.setObjectName("markforge-pdf")
        worker.tileDone.connect(self._tile_arrived, Qt.QueuedConnection)
        worker.sheetDone.connect(self._sheet_arrived, Qt.QueuedConnection)
        worker.start()
        self._worker = worker
        # A running thread outliving the application it belongs to is an
        # abort on the way out, so the way out is arranged for here rather
        # than being left to whoever happens to be closing the window.
        application = QCoreApplication.instance()
        if application is not None and not self._farewell:
            application.aboutToQuit.connect(self.shut_down)
            self._farewell = True
        atexit.register(self.shut_down)
        return worker

    def shut_down(self) -> None:
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.stop()
            worker.wait(3000)
        self.forget()

    # -- what is ready -----------------------------------------------------
    def sheet(self, source: str, data: bytes, index: int,
              page: QRectF, annotations: bool = True,
              ask: bool = True, without: tuple = ()) -> Optional[QPixmap]:
        """The small picture of the whole page, asking for it if need be.

        Without *ask*, only what is already drawn: for a caller that would
        like a picture but must not start forty of them. Opening a drawing set
        should draw the sheets somebody is looking at, not every sheet in the
        file before the window will move.
        """
        key = SheetKey(source, index, annotations, tuple(without))
        found = self._sheets.get(key)
        if found is not None:
            return found if not found.isNull() else None
        if ask and self._sheets_wanted() < MOST_SHEETS_AT_ONCE:
            # A few at a time. Zoomed out far enough to see a whole set, every
            # sheet in it is on screen at once and every one of them wants
            # drawing — which is a drawing set taking five seconds to appear
            # rather than the two or three sheets anybody is reading. Each one
            # that arrives repaints the canvas, which asks for the next few, so
            # they fill in from the top instead of all being waited for.
            self._ask(key, data, page, sheet=True)
        return None

    def _sheets_wanted(self) -> int:
        return sum(1 for key in self._waiting if isinstance(key, SheetKey))

    def tiles(self, source: str, data: bytes, index: int, page: QRectF,
              scale: float, region: QRectF, annotations: bool = True,
              without: tuple = ()
              ) -> tuple[list[tuple[QRectF, QPixmap]], bool]:
        """Every tile of *region* that is ready, and whether any is missing.

        The missing ones are asked for on the way past. Whether anything is
        missing is what decides if the small picture of the page needs drawing
        underneath: once the tiles cover what is on screen, it does not, and
        skipping it saves a full-page scaled blit on every repaint.
        """
        step = zoom_step(scale)
        without = tuple(without)
        size = TILE / step
        if size <= 0:
            return [], True
        wanted = QRectF(region).intersected(page)
        if wanted.isEmpty():
            return [], False
        first_col = max(int(wanted.left() // size), 0)
        last_col = int((wanted.right() - 1e-6) // size)
        first_row = max(int(wanted.top() // size), 0)
        last_row = int((wanted.bottom() - 1e-6) // size)
        self._stop_wanting(source, index, step, without)
        ready: list[tuple[QRectF, QPixmap]] = []
        wanting: list = []
        missing = False
        for row in range(first_row, last_row + 1):
            for col in range(first_col, last_col + 1):
                key = TileKey(source, index, step, col, row, annotations,
                              without)
                found = self._tiles.get(key)
                if found is not None:
                    if not found.isNull():
                        ready.append((key.page_rect(found), found))
                    continue
                missing = True
                wanting.append(key)
        if missing:
            # Something better than the small picture of the whole page while
            # the squares for this zoom are still coming: whatever is already
            # drawn of this page at another zoom. Zooming in on a sheet that
            # was sharp should not go soft on the way — the rung below is half
            # the resolution, not a thumbnail of the entire drawing — and
            # these are drawn under the tiles that are ready, coarsest first.
            ready = self._standing_in(source, index, step, wanted,
                                      annotations, without) + ready
        # Nearest the middle of what is being looked at first, and never more
        # than a few screenfuls at once. A repaint that asks for a thousand
        # tiles is a repaint whose answers arrive minutes later, by which time
        # the zoom has moved on; the rest are asked for on the repaints that
        # follow, by which time it is known whether they are still wanted.
        if len(wanting) > MOST_TILES_AT_ONCE:
            middle = wanted.center()
            wanting.sort(key=lambda key: _distance_from(key, middle))
            wanting = wanting[:MOST_TILES_AT_ONCE]
        for key in wanting:
            self._ask(key, data, page, sheet=False)
        return ready, missing

    def _standing_in(self, source: str, index: int, step: float,
                     region: QRectF, annotations: bool, without: tuple = ()
                     ) -> list[tuple[QRectF, QPixmap]]:
        """What is already drawn of this page at other zooms, coarsest first.

        A page that was sharp a moment ago has squares of itself in the cache,
        and half the resolution wanted is far better than a picture of the
        whole sheet stretched over it. Drawn coarsest first so anything finer
        lands on top, and the tiles for the zoom actually wanted go on last.
        """
        found: list[tuple[float, QRectF, QPixmap]] = []
        for key, pixmap in self._tiles.items():
            if (key.source != source or key.index != index
                    or key.scale == step or key.annotations != annotations
                    or key.without != without
                    or pixmap is None or pixmap.isNull()):
                continue
            where = key.page_rect(pixmap)
            if where.intersects(region):
                found.append((key.scale, where, pixmap))
        found.sort(key=lambda entry: entry[0])
        return [(where, pixmap) for _scale, where, pixmap in found]

    def _stop_wanting(self, source: str, index: int, step: float,
                      without: tuple = ()) -> None:
        """Give up on tiles of this page at a zoom nobody is looking at now.

        A zoom asks for a fresh rung of the ladder, and everything still
        outstanding from the rung before it is about to be thrown away — it
        would arrive, be cached, and never be drawn. Left in the queue it is
        worse than useless: the worker draws all of it before it reaches the
        tiles that are actually on screen, which is what made zooming into a
        dense sheet take ten seconds and then fifteen.

        Only the same page's other zooms go. Tiles of *other* pages are still
        wanted — that is the next page in the scroll, coming.
        """
        stale = [key for key in self._waiting
                 if isinstance(key, TileKey) and key.source == source
                 and key.index == index
                 and (key.scale != step or key.without != without)]
        self._waiting.difference_update(stale)

    def _ask(self, key, data: bytes, page: QRectF, sheet: bool) -> None:
        if key in self._waiting or not data:
            return
        worker = self._started()
        self._waiting.add(key)
        # Onto the queue and straight back: a repaint must never wait for a
        # page to be drawn.
        worker.submit(key, data, page.width(), page.height())

    # -- what comes back ---------------------------------------------------
    def _tile_arrived(self, key: TileKey, image: QImage) -> None:
        self._waiting.discard(key)
        pixmap = QPixmap.fromImage(image) if not image.isNull() else QPixmap()
        self._tiles[key] = pixmap
        self._held += _weight(pixmap)
        self._make_room()
        self.tileReady.emit(key)

    def _sheet_arrived(self, key: SheetKey, image: QImage) -> None:
        self._waiting.discard(key)
        pixmap = QPixmap.fromImage(image) if not image.isNull() else QPixmap()
        self._sheets[key] = pixmap
        self.sheetReady.emit(key)

    def _make_room(self) -> None:
        """Drop the oldest tiles until the cache is inside its ceiling.

        Python keeps a dict in the order things went into it, so the oldest
        is simply the first — and a tile that is still wanted is asked for
        again and drawn again, which costs one tile.
        """
        while self._held > CACHE_BYTES and self._tiles:
            oldest = next(iter(self._tiles))
            self._held -= _weight(self._tiles.pop(oldest))

    def forget(self, source: str = "") -> None:
        if not source:
            self._tiles.clear()
            self._sheets.clear()
            self._held = 0
            return
        for key in [k for k in self._tiles if k.source == source]:
            self._held -= _weight(self._tiles.pop(key))
        for key in [k for k in self._sheets if k.source == source]:
            self._sheets.pop(key, None)
        if self._worker is not None:
            self._worker.drop(source)


def _sheet_scale(page: QRectF) -> float:
    """How sharp the small picture of a whole page is, in pixels to the point.

    What the gap filler is worth while the tiles of a page are still coming.
    Not a reason to skip those tiles: a page left showing this is a page that
    stays soft until something else makes it redraw.
    """
    longest = max(page.width(), page.height(), 1.0)
    return min(THUMBNAIL_EDGE / longest, 4.0)


def _distance_from(key: "TileKey", middle) -> float:
    """How far a tile's own middle is from the middle of what is on screen."""
    box = key.page_rect()
    return ((box.center().x() - middle.x()) ** 2
            + (box.center().y() - middle.y()) ** 2)


def _weight(pixmap: QPixmap) -> int:
    if pixmap is None or pixmap.isNull():
        return 0
    return pixmap.width() * pixmap.height() * 4


#: One cache for the application. Pages are keyed by the asset they came from,
#: so two windows showing the same drawing share the work of drawing it.
TILES = TileCache()
