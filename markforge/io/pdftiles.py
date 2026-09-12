"""Viewport PDF tiles rendered by a bounded pool of independent processes.

Only visible tiles and a small scroll margin are requested. A zoom ladder and
LRU pixmap caches reuse finished work. Each render process keeps its own parsed
pages; private source files and fixed shared pixel buffers avoid copying large
PDFs and images through the job queue. The Qt coordinator only schedules work
and transfers owned QImages back to the window.

Separate processes matter: PyMuPDF does not support multithreaded use, and a
native render in a Python thread can hold the interpreter lock and stall Qt.
Printing/export retain the synchronous renderer in pdfio.LivePages.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import atexit
import time
import threading
import weakref

from PySide6.QtCore import (QCoreApplication, QObject, QRectF, Qt, QThread,
                            Signal, QTimer)
from PySide6.QtGui import QImage, QPixmap


#: How big a tile is, in screen pixels.
#:
#: The process-pool benchmark compares 512, 1024 and 2048 pixels over the
#: same area. 1024 gives the best balance of complete-view latency, first-tile
#: latency and shared-buffer memory. See docs/PDF_PERFORMANCE.md.
TILE = 1024

#: The longest edge of the small picture kept of a whole page.
THUMBNAIL_EDGE = 1100

#: How much of the tile cache to keep, in bytes of image. Roughly forty
#: A1-sized screenfuls, and a hard ceiling rather than a hope.
CACHE_BYTES = 192 * 1024 * 1024
SHEET_CACHE_BYTES = 32 * 1024 * 1024

#: The most tiles one repaint will ask for. A screenful is about a dozen, so
#: this is several screenfuls of margin and still a bound: past it the answers
#: arrive long after the zoom that wanted them has moved on.
MOST_TILES_AT_ONCE = 48

#: How many whole-page pictures to have in hand at once. Enough for the sheet
#: being read and its neighbours; the rest follow as each one arriving repaints
#: the canvas and asks for the next.
MOST_SHEETS_AT_ONCE = 4

# Source files are private, shared by the renderers, and bounded separately
# from the GUI pixmaps. A single PDF larger than this can still be opened.
SOURCE_CACHE_BYTES = 256 * 1024 * 1024
MOST_HELD_SOURCES = 8


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
    """Schedule a bounded pool of render processes without blocking Qt.

    This thread only transfers jobs and pixels. MuPDF runs exclusively in the
    child processes, outside the UI process and its Python interpreter lock.
    Jobs stay here until a renderer is idle so obsolete zooms can be dropped.
    """

    tileDone = Signal(object, QImage)
    sheetDone = Signal(object, QImage)

    def __init__(self, wanted=None, processes=None):
        super().__init__()
        from .pdfrender import worker_count
        self.process_count = max(1, min(8, int(processes))) if processes is not None else worker_count()
        self._work = {}
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._wanted = wanted if wanted is not None else set()
        self._stopping = False
        self._forgotten = set()
        self.stats = {}

    def submit(self, key, data, width, height):
        with self._lock:
            self._work.pop(key, None)
            self._work[key] = (key, data, width, height)
        self._ready.set()

    def stop(self):
        self._stopping = True
        self._ready.set()

    def drop(self, source):
        with self._lock:
            self._forgotten.add(source)
            for key in list(self._work):
                if not source or key.source == source:
                    self._work.pop(key, None)
        self._ready.set()

    def _next(self):
        with self._lock:
            while self._work:
                _, job = self._work.popitem()
                if job[0] in self._wanted:
                    return job
        return None

    def _emit(self, key, image):
        signal = self.sheetDone if isinstance(key, SheetKey) else self.tileDone
        signal.emit(key, image if image is not None else QImage())

    def run(self):
        import multiprocessing
        from multiprocessing.connection import wait
        from multiprocessing.shared_memory import SharedMemory
        import os
        import tempfile
        from .pdfrender import serve

        context = multiprocessing.get_context('spawn')
        slots, paths, sizes, retries = [], {}, {}, {}
        deferred_deletes = set()

        def start_slot():
            parent, child = context.Pipe()
            memory = SharedMemory(create=True, size=(max(TILE, THUMBNAIL_EDGE) + 2) ** 2 * 4)
            process = context.Process(target=serve, args=(child, memory.name, memory.size), daemon=True,
                                      name='MarkForge PDF renderer')
            try:
                process.start()
            except Exception:
                parent.close()
                child.close()
                memory.close()
                memory.unlink()
                raise
            child.close()
            return {'process': process, 'pipe': parent, 'memory': memory,
                    'job': None, 'forgotten': set()}

        def finish_slot(slot):
            process = slot['process']
            if process.is_alive():
                process.terminate()
            process.join(.2)
            if process.is_alive():
                process.kill()
                process.join(.2)
            slot['pipe'].close()
            slot['memory'].close()
            slot['memory'].unlink()
            process.close()

        with tempfile.TemporaryDirectory(prefix='markforge-render-') as folder:
            try:
                while not self._stopping:
                    with self._lock:
                        forgotten, self._forgotten = self._forgotten, set()
                    for path in list(deferred_deletes):
                        try:
                            os.unlink(path)
                            deferred_deletes.discard(path)
                        except OSError:
                            pass
                    for source in list(paths):
                        if '' in forgotten or source in forgotten:
                            path = paths.pop(source)
                            sizes.pop(source, None)
                            for slot in slots:
                                slot['forgotten'].add(path)
                            # Open handles remain valid until their job completes.
                            # On Windows defer deletion to TemporaryDirectory.
                            try:
                                os.unlink(path)
                            except OSError:
                                deferred_deletes.add(path)
                    for slot in list(slots):
                        process = slot['process']
                        if not process.is_alive():
                            job = slot['job']
                            finish_slot(slot)
                            slots.remove(slot)
                            if job and job[0] in self._wanted:
                                key = job[0]
                                attempts = retries.get(key, 0)
                                if attempts < 1:
                                    retries[key] = attempts + 1
                                    self.submit(*job)
                                else:
                                    self._emit(key, None)
                    # Nothing is submitted into an unbounded child-side queue.
                    idle = [slot for slot in slots if slot['job'] is None]
                    while not self._stopping:
                        if not idle and len(slots) >= self.process_count:
                            break
                        job = self._next()
                        if job is None:
                            break
                        key, data, width, height = job
                        slot = None
                        try:
                            if idle:
                                slot = idle.pop(0)
                            else:
                                slot = start_slot()
                                slots.append(slot)
                            for path in slot['forgotten']:
                                slot['pipe'].send(('forget', path))
                            slot['forgotten'].clear()
                            path = paths.pop(key.source, None)
                            if path is not None:
                                paths[key.source] = path
                            if path is None:
                                busy_sources = {held['job'][0].source for held in slots if held['job']}
                                for source in list(paths):
                                    if len(paths) < MOST_HELD_SOURCES and sum(sizes.values()) + len(data) <= SOURCE_CACHE_BYTES:
                                        break
                                    if source in busy_sources:
                                        continue
                                    old_path = paths.pop(source)
                                    sizes.pop(source, None)
                                    for held in slots:
                                        held['forgotten'].add(old_path)
                                    try:
                                        os.unlink(old_path)
                                    except OSError:
                                        deferred_deletes.add(old_path)
                                # Write the source once, off the UI thread. Children
                                # open the same private file rather than receiving a
                                # fresh copy of a large PDF for every tile.
                                descriptor, path = tempfile.mkstemp(suffix='.pdf', dir=folder)
                                with os.fdopen(descriptor, 'wb') as output:
                                    output.write(data)
                                paths[key.source] = path
                                sizes[key.source] = len(data)
                            if isinstance(key, SheetKey):
                                region = (0., 0., width, height)
                                scale = min(THUMBNAIL_EDGE / max(width, height, 1.), 4.)
                            else:
                                scale = key.scale
                                size = TILE / scale
                                left, top = key.col * size, key.row * size
                                region = (left, top, min(left + size, width), min(top + size, height))
                            slot['job'] = job
                            slot['pipe'].send(('render', path, key.index,
                                               key.annotations, key.without, region, scale))
                        except Exception:
                            self._emit(key, None)
                            if slot in slots:
                                finish_slot(slot)
                                slots.remove(slot)
                    busy = [slot for slot in slots if slot['job'] is not None]
                    if not busy:
                        self._ready.wait(.05)
                        self._ready.clear()
                        continue
                    ready = wait([slot['pipe'] for slot in busy], timeout=.02)
                    for slot in busy:
                        if slot['pipe'] not in ready:
                            continue
                        try:
                            description, stats = slot['pipe'].recv()
                        except (EOFError, OSError):
                            # The death/retry path above owns this job.
                            continue
                        key = slot['job'][0]
                        slot['job'] = None
                        self.stats[stats['pid']] = stats
                        while len(self.stats) > 32:
                            self.stats.pop(next(iter(self.stats)))
                        retries.pop(key, None)
                        if key in self._wanted:
                            image = None
                            if description is not None:
                                width, height, stride, alpha = description
                                shape = QImage.Format_RGBA8888_Premultiplied if alpha else QImage.Format_RGB888
                                # Own the pixels before this worker gets another
                                # job and overwrites its fixed shared buffer.
                                image = QImage(slot['memory'].buf, width, height, stride, shape).copy()
                            self._emit(key, image)
            finally:
                for slot in slots:
                    finish_slot(slot)
                with self._lock:
                    self._work.clear()


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
        self._failures = {}
        self._sheet_bytes = 0
        self._consumers = weakref.WeakKeyDictionary()
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
            worker.wait()
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
            self._sheets.pop(key)
            self._sheets[key] = found
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
              without: tuple = (), consumer=None
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
        self._stop_wanting(source, index, step, without, consumer, wanted)
        ready: list[tuple[QRectF, QPixmap]] = []
        wanting: list = []
        missing = False
        for row in range(first_row, last_row + 1):
            for col in range(first_col, last_col + 1):
                key = TileKey(source, index, step, col, row, annotations,
                              without)
                found = self._tiles.get(key)
                if found is not None:
                    self._tiles.pop(key)
                    self._tiles[key] = found
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
        middle = wanted.center()
        wanting.sort(key=lambda key: _distance_from(key, middle))
        wanting = wanting[:MOST_TILES_AT_ONCE]
        # The worker uses a stack: enqueue the centre last so it renders first.
        wanting.reverse()
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
                      without: tuple = (), consumer=None, region=None) -> None:
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
        request = (step, without, QRectF(region) if region is not None else None)
        retained = [request]
        if consumer is not None:
            self._consumers.setdefault(consumer, {})[(source, index)] = request
            retained.extend(requests[(source, index)] for requests in self._consumers.values()
                            if (source, index) in requests)
        stale = [key for key in self._waiting
                 if isinstance(key, TileKey) and key.source == source
                 and key.index == index
                 and not any(key.scale == scale and key.without == omitted
                             and (area is None or key.page_rect().intersects(area))
                             for scale, omitted, area in retained)]
        self._waiting.difference_update(stale)

    def _ask(self, key, data: bytes, page: QRectF, sheet: bool) -> None:
        if key in self._waiting or not data:
            return
        failed = self._failures.get(key)
        if failed is not None and (failed[0] >= 3 or time.monotonic() < failed[1]):
            return
        worker = self._started()
        self._waiting.add(key)
        # Onto the queue and straight back: a repaint must never wait for a
        # page to be drawn.
        worker.submit(key, data, page.width(), page.height())

    # -- what comes back ---------------------------------------------------
    def _tile_arrived(self, key: TileKey, image: QImage) -> None:
        if key not in self._waiting:
            return
        self._waiting.discard(key)
        if image.isNull():
            self._render_failed(key)
            return
        self._failures.pop(key, None)
        pixmap = QPixmap.fromImage(image)
        self._held -= _weight(self._tiles.pop(key, None))
        self._tiles[key] = pixmap
        self._held += _weight(pixmap)
        self._make_room()
        self.tileReady.emit(key)

    def _sheet_arrived(self, key: SheetKey, image: QImage) -> None:
        if key not in self._waiting:
            return
        self._waiting.discard(key)
        if image.isNull():
            self._render_failed(key)
            return
        self._failures.pop(key, None)
        pixmap = QPixmap.fromImage(image)
        self._sheet_bytes -= _weight(self._sheets.pop(key, None))
        self._sheets[key] = pixmap
        self._sheet_bytes += _weight(pixmap)
        while self._sheet_bytes > SHEET_CACHE_BYTES and self._sheets:
            self._sheet_bytes -= _weight(self._sheets.pop(next(iter(self._sheets))))
        self.sheetReady.emit(key)

    def _render_failed(self, key):
        attempts = self._failures.get(key, (0, 0))[0] + 1
        delay = .1 if attempts == 1 else .5
        self._failures[key] = (attempts, time.monotonic() + delay)
        while len(self._failures) > 256:
            self._failures.pop(next(iter(self._failures)))
        signal = self.sheetReady if isinstance(key, SheetKey) else self.tileReady
        # Keep drawing the fallback; an empty pixmap must never count as a
        # successfully rendered tile. Retry transient failures, without a loop.
        if attempts < 3:
            QTimer.singleShot(round(delay * 1000), lambda: signal.emit(key))

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
            self._sheet_bytes = 0
            self._waiting.clear()
            self._failures.clear()
            self._consumers.clear()
            if self._worker is not None:
                self._worker.drop("")
            return
        self._waiting.difference_update(key for key in list(self._waiting) if key.source == source)
        for key in list(self._failures):
            if key.source == source:
                del self._failures[key]
        for requests in self._consumers.values():
            for page_key in list(requests):
                if page_key[0] == source:
                    del requests[page_key]
        for key in [k for k in self._tiles if k.source == source]:
            self._held -= _weight(self._tiles.pop(key))
        for key in [k for k in self._sheets if k.source == source]:
            self._sheet_bytes -= _weight(self._sheets.pop(key, None))
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
