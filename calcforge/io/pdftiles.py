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

import math
import os

from dataclasses import dataclass
from typing import Optional

import atexit
import time
import threading
import weakref

from PySide6.QtCore import (QCoreApplication, QObject, QRectF, Qt, QThread,
                            Signal, QTimer)
from PySide6.QtGui import QImage, QPixmap, QRegion


#: How big a tile is, in screen pixels.
#:
#: The process-pool benchmark compares 512, 1024 and 2048 pixels over the
#: same area. 1024 gives the best balance of complete-view latency, first-tile
#: latency and shared-buffer memory. See docs/PDF_PERFORMANCE.md.
TILE = 1024

#: The longest edge of the small picture kept of a whole page.
THUMBNAIL_EDGE = 1100

def _installed_memory() -> int:
    """Physical memory in bytes, or 0 when the system will not say."""
    try:
        return int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES"))
    except (AttributeError, OSError, ValueError):
        pass
    try:                                    # Windows
        import ctypes

        class _Status(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                        ("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong),
                        ("page_total", ctypes.c_ulonglong),
                        ("page_free", ctypes.c_ulonglong),
                        ("virtual_total", ctypes.c_ulonglong),
                        ("virtual_free", ctypes.c_ulonglong),
                        ("extended", ctypes.c_ulonglong)]
        status = _Status()
        status.length = ctypes.sizeof(_Status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.total)
    except Exception:                       # noqa: BLE001
        pass
    return 0


#: How much of the tile cache to keep, in bytes of image. An eighth of the
#: machine's memory, between 192 MB and 2 GB: a workstation keeps every zoom
#: of every sheet it has shown, so going back is instant, and a small laptop
#: still has a hard ceiling rather than a hope.
CACHE_BYTES = max(192 * 1024 * 1024,
                  min(_installed_memory() // 8, 2048 * 1024 * 1024))
SHEET_CACHE_BYTES = max(32 * 1024 * 1024, CACHE_BYTES // 6)

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
    """The resolution to render tiles at for a painter showing *scale*.

    The zoom on screen itself, to four significant figures, so a tile's
    pixels land one-to-one on the screen's. Rendering a rung above and
    shrinking it to fit is what made the page look softer than a pasted
    snapshot of the same lines, which Qt draws as vectors at exactly the
    screen's resolution. A new zoom is one round of rendering; the tiles of
    the zoom before stand in until it arrives.
    """
    scale = min(max(float(scale), 0.02), 64.0)
    return float(f"{scale:.4g}")


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
class AnnotationTileKey:
    """One square of one of the page's own markups, drawn alone as its file
    draws it, at one rung of the zoom ladder. The page is drawn without its
    markups and each markup nobody has changed lays this over it, so taking
    one over — or undoing that — changes nothing about the page's tiles: no
    re-render, no flash (Calcs.pdf, 2026-10-01)."""
    source: str
    index: int
    xref: int
    scale: float
    col: int
    row: int
    #: The markup's box on the page, in points (left, top, right, bottom).
    box: tuple

    def page_rect(self, pixels=None) -> QRectF:
        size = TILE / self.scale
        tile = QRectF(self.col * size, self.row * size, size, size)
        left, top, right, bottom = self.box
        return tile.intersected(QRectF(left, top, right - left, bottom - top))


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
                                      name='CalcForge PDF renderer')
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

        with tempfile.TemporaryDirectory(prefix='calcforge-render-') as folder:
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
                            if isinstance(key, AnnotationTileKey):
                                part = key.page_rect()
                                slot['job'] = job
                                slot['pipe'].send(('annotation', path, key.index, key.xref,
                                                   (part.left(), part.top(), part.right(),
                                                    part.bottom()), key.scale))
                                continue
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
                                # In the screen's own pixel format, here off the
                                # window's thread: converting each tile there as
                                # it arrived was a 10 ms freeze apiece, felt as
                                # stutter while scrolling (2026-10-01).
                                image = image.convertToFormat(
                                    QImage.Format_ARGB32_Premultiplied if alpha
                                    else QImage.Format_RGB32)
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
        # What is drawn of each page (and of each of its markups), by zoom:
        # {page key: {scale: {key, ...}}}. Finding what can stand in for a
        # zoom still coming used to mean looking through every tile cached —
        # thousands, once a few sheets had been zoomed about — for every page
        # and every markup on every frame of a zoom (2026-10-02).
        self._index: dict = {}
        # Until when new squares are not asked for: a zoom on the wheel goes
        # through a dozen zooms in half a second, and drawing each of them was
        # all the render processes did while the one wanted waited behind them.
        self._held_until = 0.0
        # Squares asked for ahead — what is on screen at twice the zoom, drawn
        # while nothing else is wanted (see ahead()). A zoom does not give
        # them up the way it gives up the zoom before it.
        self._ahead: set = set()
        #: Counts the markups drawn from squares not all here yet, so whoever
        #: keeps a drawing of them (ui/markuplayer.py) knows to draw it again.
        self.short = 0

    # -- the thread --------------------------------------------------------
    def _started(self) -> _Worker:
        if self._worker is not None:
            return self._worker
        worker = _Worker(self._waiting)
        worker.setObjectName("calcforge-pdf")
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

    # -- a zoom in progress --------------------------------------------------
    def hold(self, seconds: float = 0.15) -> None:
        """Ask for no new squares for *seconds*: the zoom on screen is still
        moving, and what is already drawn stands in, scaled, until it stops.
        Each call pushes the end out; whoever is zooming repaints when it
        comes, which asks for the squares of the zoom it stopped at."""
        self._held_until = max(self._held_until, time.monotonic() + seconds)

    def held(self) -> bool:
        return time.monotonic() < self._held_until

    def let_go(self) -> None:
        self._held_until = 0.0

    # -- ahead of the zoom ------------------------------------------------------
    #: The most squares drawn ahead for one page or markup at once.
    MOST_AHEAD = 16

    def _busy(self) -> bool:
        """Whether anything is wanted that is not ahead-of-time."""
        return len(self._waiting) > len(self._ahead & self._waiting)

    def ahead(self, source: str, data: bytes, index: int, page: QRectF,
              scale: float, region: QRectF, annotations: bool = True,
              without: tuple = ()) -> None:
        """With the screen sharp and nothing else to draw, draw what is on
        screen at twice the zoom. A zoom in then has something sharper than
        it needs to stand in while its own zoom is drawn — shrunk, it is
        crisp — so the page never goes soft and then sharpens; the moment
        the zoom wanted arrives, nothing visible changes. Bluebeam's zoom
        looks like that (the user, 2026-10-02)."""
        if self.held() or self._busy() or not data:
            return
        step = zoom_step(min(scale * 2.0, 64.0))
        keys = self._squares(TileKey, source, index, step, QRectF(region).intersected(page),
                             annotations, tuple(without))
        self._ask_ahead(keys, ("page", source, index, annotations, tuple(without)),
                        data, page)

    def _squares(self, kind, source, index, step, wanted, *rest) -> list:
        if wanted.isEmpty():
            return []
        size = TILE / step
        return [kind(source, index, step, col, row, *rest)
                for row in range(max(int(wanted.top() // size), 0),
                                 int((wanted.bottom() - 1e-6) // size) + 1)
                for col in range(max(int(wanted.left() // size), 0),
                                 int((wanted.right() - 1e-6) // size) + 1)]

    def _ask_ahead(self, keys, page_key, data, page) -> None:
        # what was ahead for this page before, and is not now, is given up
        stale = {key for key in self._ahead
                 if self._page_of(key) == page_key and key not in keys}
        self._waiting.difference_update(stale)
        self._ahead.difference_update(stale)
        if len(keys) > self.MOST_AHEAD:
            return
        for key in keys:
            if key not in self._tiles and key not in self._waiting:
                self._ahead.add(key)
                self._ask(key, data, page, sheet=False)

    # -- the index -------------------------------------------------------------
    @staticmethod
    def _page_of(key):
        if isinstance(key, AnnotationTileKey):
            return ("markup", key.source, key.index, key.xref)
        return ("page", key.source, key.index, key.annotations, key.without)

    def _keep(self, key, pixmap: QPixmap) -> None:
        self._held -= _weight(self._tiles.pop(key, None))
        self._tiles[key] = pixmap
        self._held += _weight(pixmap)
        self._index.setdefault(self._page_of(key), {}).setdefault(
            key.scale, set()).add(key)

    def _drop(self, key) -> None:
        pixmap = self._tiles.pop(key, None)
        self._held -= _weight(pixmap)
        page = self._index.get(self._page_of(key))
        if page is None:
            return
        rung = page.get(key.scale)
        if rung is not None:
            rung.discard(key)
            if not rung:
                del page[key.scale]
        if not page:
            del self._index[self._page_of(key)]

    def _stand_ins(self, page_key, step: float, region: QRectF,
                   pixels=False, already=()) -> tuple[list, bool]:
        """What other zooms have of *region*, and whether it covers it.

        Not every zoom ever drawn, stacked: the nearest that covers it — a
        little sharper by choice, since shrinking looks better than
        stretching — and, only where that one has gaps, the next nearest
        under it. Stacking every rung a zoom had passed through was thirty
        thousand pictures drawn over each other in one gesture on a marked-up
        page (Calcs.pdf, 2026-10-02). Drawn worst first, so the best is on top.
        """
        page = self._index.get(page_key) or {}

        def unlikeness(scale: float) -> float:
            apart = math.log2(scale / step)
            # sharper is better than softer; far sharper is a lot of squares
            return apart * 0.6 if 0 < apart <= 2 else abs(apart) + (4 if apart > 2 else 0)

        wanted = QRectF(region)
        area = max(wanted.width() * wanted.height(), 1e-9)
        unit = 16.0                      # coverage on a grid of 1/16 point
        chosen, covered = [], QRegion()

        def cover(where):
            nonlocal covered
            part = where.intersected(wanted)
            if part.isEmpty():
                return
            covered = covered.united(QRegion(
                math.floor(part.left() * unit), math.floor(part.top() * unit),
                max(math.ceil(part.width() * unit), 1),
                max(math.ceil(part.height() * unit), 1)))

        def inside():
            return sum(r.width() * r.height() for r in covered) / unit / unit

        for where in already:
            cover(where)
        if inside() >= area * 0.999:
            return [], True
        for scale in sorted((s for s in page if s != step), key=unlikeness)[:6]:
            here = []
            for key in page[scale]:
                pixmap = self._tiles.get(key)
                if pixmap is None or pixmap.isNull():
                    continue
                where = key.page_rect(pixmap) if pixels else key.page_rect()
                if where.intersects(wanted):
                    here.append((where, pixmap))
            if not here:
                continue
            chosen.append(here)
            for where, _pixmap in here:
                cover(where)
            if inside() >= area * 0.999 or len(chosen) >= 3:
                break
        drawn = [entry for here in reversed(chosen) for entry in here]
        return drawn, inside() >= area * 0.999

    def tiles(self, source: str, data: bytes, index: int, page: QRectF,
              scale: float, region: QRectF, annotations: bool = True,
              without: tuple = (), consumer=None, say_covered: bool = False,
              shown: Optional[QRectF] = None):
        """Every tile of *region* that is ready, and whether any is missing.

        The missing ones are asked for on the way past. Whether anything is
        missing is what decides if the small picture of the page needs drawing
        underneath: once the tiles cover what is on screen, it does not, and
        skipping it saves a full-page scaled blit on every repaint.

        With *say_covered*, a third answer: whether what is ready, other zooms
        standing in, covers *shown* (what is on screen; *region* without it)
        without the small picture.
        """
        step = zoom_step(scale)
        without = tuple(without)
        size = TILE / step

        def answer(ready, missing, covers):
            return (ready, missing, covers) if say_covered else (ready, missing)

        if size <= 0:
            return answer([], True, False)
        wanted = QRectF(region).intersected(page)
        if wanted.isEmpty():
            return answer([], False, True)
        seen = wanted if shown is None else QRectF(shown).intersected(wanted)
        first_col = max(int(wanted.left() // size), 0)
        last_col = int((wanted.right() - 1e-6) // size)
        first_row = max(int(wanted.top() // size), 0)
        last_row = int((wanted.bottom() - 1e-6) // size)
        self._stop_wanting(source, index, step, without, consumer, wanted)
        held = self.held()
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
            # the squares for this zoom are still coming: what is already
            # drawn of this page at another zoom. Zooming in on a sheet that
            # was sharp should not go soft on the way — the rung below is half
            # the resolution, not a thumbnail of the entire drawing — and
            # these are drawn under the tiles that are ready.
            on_screen_missing = any(key.page_rect().intersects(seen)
                                    and self._failures.get(key, (0,))[0] < 3
                                    for key in wanting)
            standing, covers = self._standing_in(source, index, step, seen,
                                                 annotations, without)
            if on_screen_missing and covers:
                # All at once: what is on screen goes sharp in one go when the
                # last of its squares is in, not square by square over a
                # blurred page — a patchwork that reads as the page being
                # repainted (the user, 2026-10-02).
                ready = standing
            else:
                standing, covers = self._standing_in(
                    source, index, step, seen, annotations, without,
                    already=[where for where, _pixmap in ready])
                ready = standing + ready
        else:
            covers = True
        if held:
            # mid-zoom: what is here stands in, and nothing new is started
            return answer(ready, missing, covers)
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
        return answer(ready, missing, covers)

    def annotation_tiles(self, source: str, data: bytes, index: int, page: QRectF,
                         scale: float, region: QRectF, xref: int, box: QRectF
                         ) -> list[tuple[QRectF, QPixmap]]:
        """One of the page's markups as its file draws it: the squares of it
        inside *region* that are ready (other zooms standing in for the ones
        still coming), asking for the rest."""
        step = zoom_step(scale)
        size = TILE / step
        outer = QRectF(box).intersected(page)
        wanted = QRectF(region).intersected(outer)
        if size <= 0 or wanted.isEmpty():
            return []
        edges = (math.floor(outer.left()), math.floor(outer.top()),
                 math.ceil(outer.right()), math.ceil(outer.bottom()))
        first_col, last_col = int(wanted.left() // size), int((wanted.right() - 1e-6) // size)
        first_row, last_row = int(wanted.top() // size), int((wanted.bottom() - 1e-6) // size)
        # (Nothing outstanding is given up on here: a markup is small, and two
        # views of the same page at different zooms would keep cancelling each
        # other's squares of it, so neither ever arrived.)
        ready, wanting = [], []
        for row in range(max(first_row, 0), last_row + 1):
            for col in range(max(first_col, 0), last_col + 1):
                key = AnnotationTileKey(source, index, xref, step, col, row, edges)
                found = self._tiles.get(key)
                if found is not None:
                    if not found.isNull():
                        ready.append((key.page_rect(), found))
                    continue
                wanting.append(key)
        if not wanting and not self.held() and not self._busy():
            # all of it here: draw it ahead at twice the zoom (ahead())
            twice = zoom_step(min(step * 2.0, 64.0))
            size2 = TILE / twice
            keys = [AnnotationTileKey(source, index, xref, twice, col, row, edges)
                    for row in range(max(int(wanted.top() // size2), 0),
                                     int((wanted.bottom() - 1e-6) // size2) + 1)
                    for col in range(max(int(wanted.left() // size2), 0),
                                     int((wanted.right() - 1e-6) // size2) + 1)]
            self._ask_ahead(keys, ("markup", source, index, xref), data, page)
        if wanting:
            self.short += 1
            others, covers = self._stand_ins(("markup", source, index, xref),
                                             step, wanted)
            # all at once, as the page does (TileCache.tiles)
            ready = others if covers else others + ready
            if not self.held():
                for key in wanting[:MOST_TILES_AT_ONCE]:
                    self._ask(key, data, page, sheet=False)
            elif not ready:
                # Mid-zoom, and nothing of it drawn at any zoom: a markup just
                # come into view as the page zooms out. Not left out until the
                # zoom stops: its preview stands in.
                self.annotation_preview(source, data, index, page, step, xref, outer)
        return ready

    def annotation_preview(self, source: str, data: bytes, index: int, page: QRectF,
                           scale: float, xref: int, box: QRectF) -> None:
        """Make sure something of a markup is drawn, at whatever zoom: if
        nothing is, ask for it at a modest one — the power of two above
        *scale*, but no more than 2, so the same for every notch of a zoom
        and a few squares at most. It stands in until the zoom wanted
        arrives; zoomed out, it is the zoom wanted."""
        if self._index.get(("markup", source, index, xref)):
            return
        outer = QRectF(box).intersected(page)
        if outer.isEmpty():
            return
        edges = (math.floor(outer.left()), math.floor(outer.top()),
                 math.ceil(outer.right()), math.ceil(outer.bottom()))
        rung = min(2.0 ** math.ceil(math.log2(max(float(scale), 0.02))), 2.0)
        size = TILE / rung
        for row in range(max(int(outer.top() // size), 0),
                         int((outer.bottom() - 1e-6) // size) + 1):
            for col in range(max(int(outer.left() // size), 0),
                             int((outer.right() - 1e-6) // size) + 1):
                key = AnnotationTileKey(source, index, xref, rung, col, row, edges)
                if key not in self._tiles:
                    self._ask(key, data, page, sheet=False)

    def _standing_in(self, source: str, index: int, step: float,
                     region: QRectF, annotations: bool, without: tuple = (),
                     already=()) -> tuple[list[tuple[QRectF, QPixmap]], bool]:
        """What is already drawn of this page at other zooms, and whether it,
        with *already* (what the zoom wanted has ready), covers *region* —
        see :meth:`_stand_ins`."""
        return self._stand_ins(("page", source, index, annotations, tuple(without)),
                               step, region, pixels=True, already=already)

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
                 if isinstance(key, TileKey) and key not in self._ahead
                 and key.source == source
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
        self._ahead.discard(key)
        if image.isNull():
            self._render_failed(key)
            return
        self._failures.pop(key, None)
        self._keep(key, QPixmap.fromImage(image))
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
            self._drop(next(iter(self._tiles)))

    def forget(self, source: str = "") -> None:
        if not source:
            self._tiles.clear()
            self._index.clear()
            self._sheets.clear()
            self._held = 0
            self._sheet_bytes = 0
            self._waiting.clear()
            self._ahead.clear()
            self._failures.clear()
            self._consumers.clear()
            if self._worker is not None:
                self._worker.drop("")
            return
        self._waiting.difference_update(key for key in list(self._waiting) if key.source == source)
        self._ahead.difference_update(key for key in list(self._ahead) if key.source == source)
        for key in list(self._failures):
            if key.source == source:
                del self._failures[key]
        for requests in self._consumers.values():
            for page_key in list(requests):
                if page_key[0] == source:
                    del requests[page_key]
        for key in [k for k in self._tiles if k.source == source]:
            self._drop(key)
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
