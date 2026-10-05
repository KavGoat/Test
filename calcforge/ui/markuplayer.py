"""A page's markups drawn once, into squares, and shown from them.

A sheet with a thousand markups was a thousand calls into Python on every
frame of a scroll, a pan or a zoom — 70 to 220 ms a frame (the user,
2026-10-05: "put like a 1000 markups on one sheet ... It starts lagging").
Bluebeam draws its markups with the page; this does the same: each page keeps
its markups drawn into squares at the zoom on screen, and a frame is a few
pictures moved, however many markups there are. While a zoom moves, the
squares of the zoom before stand in, scaled, as the page's own squares do;
squares are drawn while the window is idle, nearest the middle of the screen
first and then just off it, so a scroll lands on squares already drawn.

Only markups nobody is touching are drawn this way. Anything selected, being
drawn, typed into or dragged — anything changed in the last moment — is drawn
live, as before; a moment after it stops changing it goes back into the
squares. It goes on being drawn live until its squares have been drawn again
with it in them, so it is never missing and never shown twice. A highlighter,
which multiplies into the page under it, is always drawn live: in a square of
its own it would have nothing to multiply with.

A markup in the squares keeps its place among the items, so it is still
clicked, hovered and snapped to as before; it is only not painted (Qt's
ItemHasNoContents), and answers Qt's questions about its size from what it was
when it went in.
"""
from __future__ import annotations

import math
import time
from collections import OrderedDict

from PySide6.QtCore import QPointF, QRectF, QTimer
from PySide6.QtGui import QImage, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem

#: The side of a square, in device pixels. Small, so one square is a few
#: markups' drawing — a step of idle work, not a stall.
TILE = 256

#: How long a markup must go unchanged before it is drawn into the squares.
SETTLE_SECONDS = 0.4

#: How much idle time one turn of the event loop spends drawing squares.
IDLE_SECONDS = 0.008

#: Squares above and below what is on screen, drawn ahead: most of a screen.
AHEAD = 0.75

#: Memory for every page's squares together.
CACHE_BYTES = 384 * 1024 * 1024

#: The grid markups are filed in, in points, to find a square's markups.
CELL = 128.0

_ALL: "OrderedDict[tuple, int]" = OrderedDict()     # (id(layer), key) -> bytes
_LAYERS: dict = {}                                   # id(layer) -> layer
_held = [0]
#: Set while squares are being drawn: a markup that asks to be repainted
#: from inside its own paint is not changing.
_drawing = [False]


#: Until when the reader is scrolling, panning, zooming or dragging: squares
#: are drawn in the pauses, not between the frames of a movement.
_busy_until = [0.0]


def busy(seconds: float = 0.15) -> None:
    _busy_until[0] = time.monotonic() + seconds


def _busy() -> bool:
    return time.monotonic() < _busy_until[0]


def _valid(item) -> bool:
    try:
        import shiboken6
        return shiboken6.isValid(item)
    except Exception:                                   # noqa: BLE001
        return True


def _remember(layer, key, pixmap) -> None:
    weight = pixmap.width() * pixmap.height() * 4 if pixmap is not None else 64
    marker = (id(layer), key)
    _held[0] -= _ALL.pop(marker, 0)
    _ALL[marker] = weight
    _held[0] += weight
    while _held[0] > CACHE_BYTES and _ALL:
        (owner, old), size = _ALL.popitem(last=False)
        _held[0] -= size
        holder = _LAYERS.get(owner)
        if holder is not None:
            holder._drop(old, forget=False)


def _touch(layer, key) -> None:
    marker = (id(layer), key)
    if marker in _ALL:
        _ALL.move_to_end(marker)


class _Square:
    __slots__ = ("pixmap", "stale", "redo")

    def __init__(self, pixmap, redo=False):
        self.pixmap = pixmap
        self.stale = False       # something in it changed: drawn again when idle
        self.redo = redo         # drawn with a markup's file drawing not all in


class MarkupLayer:
    """The squares of one page's markups, and which markups are in them."""

    def __init__(self, frame):
        self.frame = frame
        self.tiles: dict = {}            # step -> {(col, row): _Square}
        self.members: set = set()        # drawn from the squares
        self.pending: set = set()        # settled, live until their squares are drawn
        self.hot: dict = {}              # changed lately -> when
        self.boxes: dict = {}            # member or pending -> its box on the page
        self.grid: dict = {}             # (i, j) -> set of members and pending
        self._order = None
        self._suspended: set = set()
        self._settle = None
        self._idle = None
        self.enabled = True
        #: what the screen last showed: (step, page region, its middle)
        self.wanted = None
        #: Counts every change to any markup on the page: whoever keeps a
        #: copy of the page's markups (a thumbnail, an undo snapshot) can tell
        #: whether it is still right without drawing or writing them again.
        self.generation = 0
        _LAYERS[id(self)] = self

    # -- who is in the squares ------------------------------------------------
    def wants(self, item) -> bool:
        """Whether *item* can be drawn from the squares just now."""
        if not self.enabled or not _valid(item) or item.parentItem() is not self.frame:
            return False
        if not item.isVisible() or item.hasFocus():
            return False
        if getattr(item, "IS_CALC", False) or getattr(item, "live", False):
            return False
        if getattr(item, "still_theirs", False) or getattr(item, "split_theirs", False):
            # drawn by its own file, from squares the render processes make:
            # already pictures, and kept in step with them there
            return False
        if getattr(getattr(item, "style", None), "blend", "") == "multiply":
            return False
        if item.flags() & QGraphicsItem.ItemIgnoresTransformations:
            return False
        for child in item.childItems():
            # an editor, a size box: something being worked in
            if child.isVisible() and not getattr(child, "MARKUP_LOOK", False):
                return False
        # off the page, out on the desk: the page's own repaint does not reach
        return self.frame.boundingRect().contains(self._box(item))

    def touched(self, item) -> None:
        """*item* is about to change, or has: draw it live for a moment."""
        if _drawing[0]:
            return
        self.generation += 1
        if item in self.members:
            self._unbake(item)
            self.members.discard(item)
            self._unfile(item, drop=True)        # its old drawing goes now
        elif item in self.pending:
            self.pending.discard(item)
            self._unfile(item, drop=False)
        self.hot[item] = time.monotonic()
        self._arm()

    def forget(self, item) -> None:
        """*item* is leaving the page."""
        self.generation += 1
        if item in self.members:
            self.members.discard(item)
            self._unbake(item)
            self._unfile(item, drop=True)
        elif item in self.pending:
            self.pending.discard(item)
            self._unfile(item, drop=False)
        self.hot.pop(item, None)
        self._suspended.discard(item)

    def _file(self, item) -> None:
        box = self._box(item)
        self.boxes[item] = box
        for cell in self._cells(box):
            self.grid.setdefault(cell, set()).add(item)
        self._order = None

    def _unfile(self, item, drop: bool) -> None:
        box = self.boxes.pop(item, None)
        if box is None:
            box = self._box(item)
        for cell in self._cells(box):
            filed = self.grid.get(cell)
            if filed is not None:
                filed.discard(item)
                if not filed:
                    del self.grid[cell]
        self._order = None
        if drop:
            self.dirty(box)
        else:
            self.stale(box)

    @staticmethod
    def _cells(box: QRectF):
        for i in range(math.floor(box.left() / CELL), math.floor(box.right() / CELL) + 1):
            for j in range(math.floor(box.top() / CELL), math.floor(box.bottom() / CELL) + 1):
                yield (i, j)

    def _arm(self) -> None:
        if self._settle is None:
            self._settle = QTimer(self.frame)
            self._settle.setSingleShot(True)
            self._settle.timeout.connect(self._settle_down)
        if not self._settle.isActive():
            self._settle.start(round(SETTLE_SECONDS * 1000))

    def _settle_down(self) -> None:
        """Markups unchanged for a moment are drawn into the squares."""
        if not _valid(self.frame):
            return
        now = time.monotonic()
        waiting = False
        settled: list = []
        for item, when in list(self.hot.items()):
            if not _valid(item):
                self.hot.pop(item, None)
                continue
            if now - when < SETTLE_SECONDS * 0.9:
                waiting = True
                continue
            self.hot.pop(item, None)
            if self.wants(item) and self._on_screen():
                # still drawn live, until the squares are drawn with it in
                self.pending.add(item)
                self._file(item)
                settled.append(item)
        if len(settled) <= 24:
            # a few: their parts of the squares are drawn now, and they are in
            for item in settled:
                self.dirty(self.boxes[item])
                self.pending.discard(item)
                self.members.add(item)
                self._bake(item)
        else:
            # a crowd (a page opened, a paste): drawn into the squares while
            # the window is idle, each staying live until its squares are in
            for item in settled:
                self.stale(self.boxes[item])
        if waiting:
            self._arm()
        if self.pending:
            self.frame.update()          # the repaint says what the screen shows
        self._wake()

    def _on_screen(self) -> bool:
        frame = self.frame
        return not (frame.print_mode or frame._items_only or frame._pdf_overlay)

    @staticmethod
    def _bake(item) -> None:
        item._baked_rect = None
        item._baked_rect = QRectF(item.boundingRect())
        item.setFlag(QGraphicsItem.ItemHasNoContents, True)
        for child in item.childItems():
            if getattr(child, "MARKUP_LOOK", False):
                child._baked_rect = None
                child._baked_rect = QRectF(child.boundingRect())
                child.setFlag(QGraphicsItem.ItemHasNoContents, True)

    @staticmethod
    def _unbake(item) -> None:
        if not _valid(item):
            return
        item.setFlag(QGraphicsItem.ItemHasNoContents, False)
        item._baked_rect = None
        for child in item.childItems():
            if getattr(child, "MARKUP_LOOK", False):
                child.setFlag(QGraphicsItem.ItemHasNoContents, False)
                child._baked_rect = None

    def suspend(self) -> None:
        """Every markup paints itself again — for a print, an export, a
        thumbnail drawn through the scene. The squares are kept."""
        for item in list(self.members):
            self._unbake(item)
        self._suspended |= self.members
        self.members = set()

    def release_all(self) -> None:
        """Out of the squares for good: everything paints itself."""
        for item in list(self.members) + list(self._suspended):
            self._unbake(item)
        self.members, self.pending, self._suspended = set(), set(), set()
        self.boxes.clear()
        self.grid.clear()
        self._order = None
        self.clear()

    def _resume(self) -> None:
        for item in list(self._suspended):
            if not _valid(item):
                continue
            if item not in self.hot and item in self.boxes and self.wants(item):
                self._bake(item)
                self.members.add(item)
            else:
                if item in self.boxes:
                    self._unfile(item, drop=True)
                if item.parentItem() is self.frame:
                    self.hot[item] = 0.0
                    self._arm()
        self._suspended.clear()

    # -- what is drawn ----------------------------------------------------------
    def _box(self, item) -> QRectF:
        """Where *item* draws, on its page, with its children."""
        try:
            box = item.mapRectToParent(item.boundingRect() | item.childrenBoundingRect())
        except RuntimeError:
            return QRectF()
        return box.adjusted(-2, -2, 2, 2)

    def _keys(self, box: QRectF, step: float):
        size = TILE / step
        for col in range(math.floor(box.left() / size), math.floor(box.right() / size) + 1):
            for row in range(math.floor(box.top() / size), math.floor(box.bottom() / size) + 1):
                yield col, row

    def dirty(self, box: QRectF) -> None:
        """Everything drawn in *box* is wrong. On screen it is drawn again
        there and only there — the markups under *box*, into that part of
        each square: a markup picked up off a crowded sheet costs its own
        neighbours' drawing, not the square's. Other zooms' squares go."""
        if box.isEmpty():
            return
        current = self.wanted[0] if self.wanted else None
        for step in list(self.tiles):
            squares = self.tiles.get(step, {})
            for col, row in self._keys(box, step):
                square = squares.get((col, row))
                if square is None:
                    continue
                if step == current and not square.redo:
                    self._patch(step, col, row, box)
                else:
                    self._drop((step, col, row))

    def stale(self, box: QRectF) -> None:
        """What is drawn in *box* is out of date but not wrong — whatever
        changed is still drawn live over it — so it stands until it is drawn
        again. Other zooms' squares there go: nothing draws over those."""
        if box.isEmpty():
            return
        current = self.wanted[0] if self.wanted else None
        for step in list(self.tiles):
            squares = self.tiles.get(step, {})
            for col, row in self._keys(box, step):
                square = squares.get((col, row))
                if square is None:
                    continue
                if step == current:
                    square.stale = True
                else:
                    self._drop((step, col, row))
        self._wake()

    def clear(self) -> None:
        for step in list(self.tiles):
            for col, row in list(self.tiles.get(step, {})):
                self._drop((step, col, row))
        self.tiles.clear()

    def _drop(self, key, forget: bool = True) -> None:
        step, col, row = key
        squares = self.tiles.get(step)
        if squares is not None:
            squares.pop((col, row), None)
            if not squares:
                del self.tiles[step]
        if forget:
            _held[0] -= _ALL.pop((id(self), key), 0)

    # -- the screen -------------------------------------------------------------
    def paint(self, painter: QPainter, exposed: QRectF, scale: float) -> None:
        """Draw the squares covering *exposed* (page coordinates)."""
        from ..io import pdftiles
        from .scene import _draw_on_the_pixel_grid, _visible_part

        if self._suspended:
            self._resume()
        if not self.members and not self.pending:
            return
        step = pdftiles.zoom_step(scale)
        size = TILE / step
        held = pdftiles.TILES.held()
        seen = _visible_part(self.frame) or exposed
        self.wanted = (step, seen, seen.center())
        squares = self.tiles.get(step, {})
        drawn, standing, idle_work = [], [], False
        rung_deadline = time.perf_counter() + 0.006
        for col, row in self._keys(exposed, step):
            square = squares.get((col, row))
            if square is not None and not (square.redo and not held):
                _touch(self, (step, col, row))
                idle_work = idle_work or square.stale
                if square.pixmap is not None:
                    drawn.append((QRectF(col * size, row * size, size, size), square.pixmap))
                continue
            others = self._stand_ins(step, col, row)
            if not others and held and time.perf_counter() < rung_deadline:
                others = self._rung(step, col, row)
            if others:
                standing.extend(others)
                idle_work = True
                continue
            if square is not None and square.pixmap is not None:
                # drawn mid-zoom, short of a markup's file drawing: shown
                # until drawn again
                drawn.append((QRectF(col * size, row * size, size, size), square.pixmap))
                idle_work = True
                continue
            square = self._draw(step, col, row, held)
            if square.pixmap is not None:
                drawn.append((QRectF(col * size, row * size, size, size), square.pixmap))
        painter.save()
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        for where, pixmap in standing:
            painter.drawPixmap(where, pixmap, QRectF(pixmap.rect()))
        for where, pixmap in drawn:
            _draw_on_the_pixel_grid(painter, where, pixmap)
        painter.restore()
        self._paint_handles(painter, exposed)
        if idle_work or self.pending:
            self._wake()
        else:
            self._wake(ahead_only=True)

    def _paint_handles(self, painter: QPainter, exposed: QRectF) -> None:
        """The handles of the picked-out markups that are drawn from the
        squares: picking one out does not take it out of them."""
        scene = self.frame.scene()
        if scene is None:
            return
        for item in scene.selectedItems():
            if item in self.members and self.boxes.get(item, QRectF()).intersects(exposed):
                transform, _ok = item.itemTransform(self.frame)
                painter.save()
                painter.setWorldTransform(transform * painter.worldTransform())
                item.paint_handles(painter)
                painter.restore()

    def _stand_ins(self, step: float, col: int, row: int) -> list:
        """The squares of the nearest other zoom covering this one."""
        size = TILE / step
        want = QRectF(col * size, row * size, size, size).adjusted(0.01, 0.01, -0.01, -0.01)
        for other in sorted((s for s in self.tiles if s != step),
                            key=lambda s: abs(math.log2(s / step)) - (0.3 if s > step else 0)):
            other_size = TILE / other
            found = []
            for c, r in self._keys(want, other):
                square = self.tiles[other].get((c, r))
                if square is None:
                    found = None
                    break
                if square.pixmap is not None:
                    found.append((QRectF(c * other_size, r * other_size,
                                         other_size, other_size), square.pixmap))
            if found is not None:
                return found
        return []

    def _rung(self, step: float, col: int, row: int) -> list:
        """Mid-zoom with nothing to stand in: draw at the power of two above,
        which every notch of the zoom can then use."""
        rung = min(2.0 ** math.ceil(math.log2(max(step, 0.02))), 64.0)
        if rung == step:
            return []
        size, rung_size = TILE / step, TILE / rung
        want = QRectF(col * size, row * size, size, size).adjusted(0.01, 0.01, -0.01, -0.01)
        found = []
        for c, r in self._keys(want, rung):
            square = self.tiles.get(rung, {}).get((c, r)) or self._draw(rung, c, r, True)
            if square.pixmap is not None:
                found.append((QRectF(c * rung_size, r * rung_size, rung_size, rung_size),
                              square.pixmap))
        return found

    # -- idle work ----------------------------------------------------------------
    def _wake(self, ahead_only: bool = False) -> None:
        if self._idle is None:
            self._idle = QTimer(self.frame)
            self._idle.setSingleShot(True)
            self._idle.timeout.connect(self._work)
        if not self._idle.isActive():
            self._idle.start(0 if not ahead_only else 30)

    def _work(self) -> None:
        """While the window is idle: draw the squares the screen is waiting
        for, nearest its middle first, then the ones just off it; and put the
        markups whose squares now have them in into the squares."""
        from ..io import pdftiles

        if not _valid(self.frame) or self.wanted is None or self._suspended:
            return
        if pdftiles.TILES.held() or _busy():
            self._idle.start(40)
            return
        step, seen, middle = self.wanted
        size = TILE / step
        deadline = time.perf_counter() + IDLE_SECONDS
        squares = self.tiles.get(step, {})
        todo = [key for key in self._keys(seen, step) if self._needs(squares.get(key))]
        ahead = seen.adjusted(-seen.width() * 0.25, -seen.height() * AHEAD,
                              seen.width() * 0.25, seen.height() * AHEAD)
        ahead = ahead.intersected(self.frame.boundingRect())
        later = [key for key in self._keys(ahead, step)
                 if key not in todo and self._needs(squares.get(key))]

        def distance(key):
            return ((key[0] + 0.5) * size - middle.x()) ** 2 + ((key[1] + 0.5) * size - middle.y()) ** 2

        todo.sort(key=distance)
        later.sort(key=distance)
        # and last, the whole page small: whatever a zoom out comes to, it
        # has something to stand in while its own squares are drawn
        overview = self.overview_step()
        page = self.frame.page_rect()
        far = [] if overview >= step else [
            (overview, key) for key in self._keys(page, overview)
            if self._needs(self.tiles.get(overview, {}).get(key))]
        changed = QRectF()
        for key in todo + later:
            if time.perf_counter() > deadline:
                break
            self._draw(step, key[0], key[1], False)
            if key in todo or self.pending:
                where = QRectF(key[0] * size, key[1] * size, size, size)
                changed = changed.united(where) if not changed.isEmpty() else where
        for other, key in far:
            if time.perf_counter() > deadline:
                break
            self._draw(other, key[0], key[1], False)
        self._bake_what_is_drawn(step, ahead)
        if not changed.isEmpty():
            self.frame.update(changed)
        squares = self.tiles.get(step, {})
        if any(self._needs(squares.get(key)) for key in todo + later) or any(
                self._needs(self.tiles.get(other, {}).get(key)) for other, key in far):
            self._idle.start(0)

    def overview_step(self) -> float:
        """The zoom the whole page is kept at: about a thousand pixels across."""
        page = self.frame.page_rect()
        longest = max(page.width(), page.height(), 1.0)
        return 2.0 ** math.floor(math.log2(max(1000.0 / longest, 0.02)))

    @staticmethod
    def _needs(square) -> bool:
        return square is None or square.stale or square.redo

    def _bake_what_is_drawn(self, step: float, region: QRectF) -> None:
        squares = self.tiles.get(step, {})
        for item in list(self.pending):
            if not _valid(item):
                self.pending.discard(item)
                continue
            box = self.boxes.get(item, QRectF()).intersected(region)
            if all((square := squares.get(key)) is not None and not square.stale
                   for key in self._keys(box, step)) or box.isEmpty():
                self.pending.discard(item)
                self.members.add(item)
                self._bake(item)

    def _drawn_in(self, area: QRectF) -> list:
        """Members and pending markups in *area*, in stacking order."""
        found = set()
        for cell in self._cells(area):
            found |= self.grid.get(cell, set())
        if not found:
            return []
        if self._order is None:
            self._order = {item: index for index, item in enumerate(self.frame.childItems())}
        order = self._order
        return sorted((item for item in found
                       if item in order and self.boxes[item].intersects(area) and _valid(item)),
                      key=order.__getitem__)

    def _patch(self, step: float, col: int, row: int, box: QRectF) -> None:
        """Draw *box* of one square again, with what is in the squares now."""
        from ..io import pdftiles

        square = self.tiles[step][(col, row)]
        size = TILE / step
        area = QRectF(col * size, row * size, size, size)
        # the part of the square, out to whole pixels
        left = max(math.floor((box.left() - area.left()) * step) - 1, 0)
        top = max(math.floor((box.top() - area.top()) * step) - 1, 0)
        right = min(math.ceil((box.right() - area.left()) * step) + 1, TILE)
        bottom = min(math.ceil((box.bottom() - area.top()) * step) + 1, TILE)
        if right <= left or bottom <= top:
            return
        pixels = QRectF(left, top, right - left, bottom - top)
        part = QRectF(area.left() + left / step, area.top() + top / step,
                      (right - left) / step, (bottom - top) / step)
        if square.pixmap is not None:
            image = square.pixmap.toImage()
        else:
            image = QImage(TILE, TILE, QImage.Format_ARGB32_Premultiplied)
            image.fill(0)
        painter = QPainter(image)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing
                               | QPainter.SmoothPixmapTransform)
        painter.setClipRect(pixels)
        painter.setCompositionMode(QPainter.CompositionMode_Clear)
        painter.fillRect(pixels, 0)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        base = QTransform()
        base.scale(step, step)
        base.translate(-area.left(), -area.top())
        before = pdftiles.TILES.short
        _drawing[0] = True
        try:
            for item in self._drawn_in(part):
                self._paint_item(painter, item, base)
        finally:
            _drawing[0] = False
            painter.end()
        square.pixmap = QPixmap.fromImage(image)
        square.redo = square.redo or pdftiles.TILES.short != before

    def _draw(self, step: float, col: int, row: int, held: bool) -> _Square:
        """Draw one square: every markup in it, in its stacking order."""
        from ..io import pdftiles

        size = TILE / step
        area = QRectF(col * size, row * size, size, size)
        inside = self._drawn_in(area)
        pixmap = None
        short = False
        if inside:
            image = QImage(TILE, TILE, QImage.Format_ARGB32_Premultiplied)
            image.fill(0)
            painter = QPainter(image)
            painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing
                                   | QPainter.SmoothPixmapTransform)
            base = QTransform()
            base.scale(step, step)
            base.translate(-area.left(), -area.top())
            before = pdftiles.TILES.short
            _drawing[0] = True
            try:
                for item in inside:
                    self._paint_item(painter, item, base)
            finally:
                _drawing[0] = False
                painter.end()
            short = pdftiles.TILES.short != before
            pixmap = QPixmap.fromImage(image)
        square = _Square(pixmap, redo=short)
        self.tiles.setdefault(step, {})[(col, row)] = square
        _remember(self, (step, col, row), pixmap)
        return square

    def _paint_item(self, painter: QPainter, item, base: QTransform) -> None:
        children = [child for child in item.childItems() if child.isVisible()]
        behind = [child for child in children
                  if child.flags() & QGraphicsItem.ItemStacksBehindParent]
        for child in behind:
            self._paint_one(painter, child, base)
        self._paint_one(painter, item, base, own=True)
        for child in children:
            if child not in behind:
                self._paint_one(painter, child, base)

    def _paint_one(self, painter: QPainter, item, base: QTransform, own: bool = False) -> None:
        transform, _ok = item.itemTransform(self.frame)
        painter.save()
        painter.setWorldTransform(transform * base)
        if not own and item.opacity() < 1.0:
            painter.setOpacity(item.opacity())
        option = QStyleOptionGraphicsItem()
        option.exposedRect = item.boundingRect()
        try:
            item.paint(painter, option, None)
        finally:
            painter.restore()
