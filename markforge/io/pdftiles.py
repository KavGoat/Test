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
  on the size of the window and not on the size of the sheet. A tile of an A1
  sheet at four times life size takes about twenty milliseconds.

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
  soft and sharpens, rather than starting empty.

* **A cache with a ceiling.** Tiles are kept for as long as there is room and
  the least recently wanted are dropped first, so zooming back out and
  scrolling back up are instant, and the memory does not grow without end.

Printing and exporting do not come through here. They want the whole page at
one resolution, right now, and they are allowed to wait — that is
:func:`markforge.io.pdfio.LivePages.draw_region`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import atexit
import queue

from PySide6.QtCore import (QBuffer, QByteArray, QCoreApplication, QIODevice,
                            QObject, QRect, QRectF, QSize, Qt, QThread, Signal)
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtPdf import QPdfDocument, QPdfDocumentRenderOptions

#: How big a tile is, in screen pixels. Big enough that a screenful is a
#: handful of them rather than hundreds; small enough that one is quick.
TILE = 512

#: The longest edge of the small picture kept of a whole page.
THUMBNAIL_EDGE = 1100

#: How much of the tile cache to keep, in bytes of image. Roughly forty
#: A1-sized screenfuls, and a hard ceiling rather than a hope.
CACHE_BYTES = 192 * 1024 * 1024


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


def _options(annotations: bool) -> QPdfDocumentRenderOptions:
    options = QPdfDocumentRenderOptions()
    if annotations:
        options.setRenderFlags(QPdfDocumentRenderOptions.RenderFlag.Annotations)
    return options


class _Worker(QThread):
    """Renders on its own thread, taking work off a queue.

    Deliberately a queue and not queued slot calls: handing Python objects
    across threads through Qt's meta-object system is a way to crash, and
    there is nothing here that needs it. What crosses back is a signal, which
    Qt delivers on the window's thread by itself.

    The thread keeps its own QPdfDocument for each source, because a document
    belongs to the thread that opened it.
    """

    tileDone = Signal(object, QImage)
    sheetDone = Signal(object, QImage)

    def __init__(self) -> None:
        super().__init__()
        self._work: "queue.Queue" = queue.Queue()
        self._open: dict[str, QPdfDocument] = {}
        self._stopping = False

    def submit(self, key, data: bytes, width: float, height: float) -> None:
        self._work.put((key, data, width, height))

    def stop(self) -> None:
        self._stopping = True
        self._work.put(None)

    def drop(self, source: str) -> None:
        self._work.put(("forget", source, 0.0, 0.0))

    def run(self) -> None:
        while True:
            job = self._work.get()
            if job is None:
                break
            key, data, width, height = job
            if key == "forget":
                self._open.pop(data, None)
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
        self._open.clear()

    def _document(self, source: str, data: bytes) -> Optional[QPdfDocument]:
        found = self._open.get(source)
        if found is not None:
            return found
        holder = QBuffer()
        holder.setData(QByteArray(data))
        holder.open(QIODevice.ReadOnly)
        document = QPdfDocument()
        document.load(holder)
        if document.pageCount() < 1:
            return None
        # The buffer has to outlive the document reading from it.
        document._markforge_buffer = holder
        self._open[source] = document
        return document

    def _tile(self, key: "TileKey", data: bytes,
              page_width: float, page_height: float) -> None:
        document = self._document(key.source, data)
        if document is None or not 0 <= key.index < document.pageCount():
            self.tileDone.emit(key, QImage())
            return
        across = max(int(round(page_width * key.scale)), 1)
        down = max(int(round(page_height * key.scale)), 1)
        # The last tile in a row or column is the part of one that fits.
        left, top = key.col * TILE, key.row * TILE
        width = max(min(TILE, across - left), 0)
        height = max(min(TILE, down - top), 0)
        if width <= 0 or height <= 0:
            self.tileDone.emit(key, QImage())
            return
        options = _options(key.annotations)
        options.setScaledSize(QSize(across, down))
        options.setScaledClipRect(QRect(left, top, width, height))
        image = document.render(key.index, QSize(width, height), options)
        self.tileDone.emit(key, image)

    def _sheet(self, key: "SheetKey", data: bytes,
               page_width: float, page_height: float) -> None:
        document = self._document(key.source, data)
        if document is None or not 0 <= key.index < document.pageCount():
            self.sheetDone.emit(key, QImage())
            return
        longest = max(page_width, page_height, 1.0)
        shrink = min(THUMBNAIL_EDGE / longest, 4.0)
        across = max(int(page_width * shrink), 1)
        down = max(int(page_height * shrink), 1)
        image = document.render(key.index, QSize(across, down),
                                _options(key.annotations))
        self.sheetDone.emit(key, image)


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
        self._waiting: set = set()
        self._held = 0
        self._worker: Optional[_Worker] = None
        self._farewell = False

    # -- the thread --------------------------------------------------------
    def _started(self) -> _Worker:
        if self._worker is not None:
            return self._worker
        worker = _Worker()
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
              page: QRectF, annotations: bool = True) -> Optional[QPixmap]:
        """The small picture of the whole page, asking for it if need be."""
        key = SheetKey(source, index, annotations)
        found = self._sheets.get(key)
        if found is not None:
            return found if not found.isNull() else None
        self._ask(key, data, page, sheet=True)
        return None

    def tiles(self, source: str, data: bytes, index: int, page: QRectF,
              scale: float, region: QRectF, annotations: bool = True
              ) -> tuple[list[tuple[QRectF, QPixmap]], bool]:
        """Every tile of *region* that is ready, and whether any is missing.

        The missing ones are asked for on the way past. Whether anything is
        missing is what decides if the small picture of the page needs drawing
        underneath: once the tiles cover what is on screen, it does not, and
        skipping it saves a full-page scaled blit on every repaint.
        """
        step = zoom_step(scale)
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
        ready: list[tuple[QRectF, QPixmap]] = []
        missing = False
        for row in range(first_row, last_row + 1):
            for col in range(first_col, last_col + 1):
                key = TileKey(source, index, step, col, row, annotations)
                found = self._tiles.get(key)
                if found is not None:
                    if not found.isNull():
                        ready.append((key.page_rect(found), found))
                    continue
                missing = True
                self._ask(key, data, page, sheet=False)
        return ready, missing

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


def _weight(pixmap: QPixmap) -> int:
    if pixmap is None or pixmap.isNull():
        return 0
    return pixmap.width() * pixmap.height() * 4


#: One cache for the application. Pages are keyed by the asset they came from,
#: so two windows showing the same drawing share the work of drawing it.
TILES = TileCache()
