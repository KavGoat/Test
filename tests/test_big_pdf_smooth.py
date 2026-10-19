"""A big marked-up drawing set scrolls and zooms smoothly (the user,
2026-10-19, on Windows, with a 162-sheet, 24 MB steel set: "very slow to zoom
and scroll. I noticed Bluebeam has low res for zoomed out etc. ... Needs to be
buttery smooth").

What it was, measured on that set: every frame of a scroll or a zoom had Qt
ask each of the set's 1,144 markups — on every page, on screen or not — how
big it was, a call into Python apiece (20 ms a frame); each wheel notch of a
zoom worked out stand-ins for every markup it would land on (40 ms); a page
scrolled onto laid the whole window out again (80 ms); and a page flicked into
view before anything of it was drawn was a blank sheet.

These drive a synthetic set with the same traits — A1 sheets, heavy line
work, an embedded picture, a few dozen markups a sheet and the same stamp on
every one — with the real wheel, and hold the window's own work to a frame
budget (the time the window's thread spends, not how long the drawing
processes take), every page on screen to having something of itself drawn
in every frame, and the settled window to what a fresh start draws.
"""
from __future__ import annotations

import math
import statistics
import time

import pytest
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QImage, QWheelEvent
from PySide6.QtWidgets import QApplication

#: the sheets' own colour, edge to edge: anything of a page drawn is this or
#: the line work on it, never the white of a sheet nothing has been drawn on
TINT = (0.80, 0.88, 1.0)
#: and as many sheets and markups as the user's set has, near enough: what
#: a frame cost there was in proportion to the markups on every page
PAGES = 36
MARKUPS = 32

#: the window's work for one frame of a gesture, in milliseconds of its
#: thread's time (generous for a loaded test machine)
MEDIAN_BUDGET = 16.0
P95_BUDGET = 40.0


def _heavy_set(path, pages: int = PAGES) -> str:
    import random

    import pymupdf

    rng = random.Random(1019)
    document = pymupdf.open()
    picture = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 192, 128), 0)
    picture.set_rect(picture.irect, (90, 130, 170))
    stamp = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 120, 60), 0)
    stamp.set_rect(stamp.irect, (200, 40, 40))
    stamp.set_rect(pymupdf.IRect(10, 10, 110, 50), (250, 250, 210))
    for number in range(pages):
        width, height = 2384.0, 1684.0                     # A1
        page = document.new_page(width=width, height=height)
        page.draw_rect(page.rect, color=None, fill=TINT)
        shape = page.new_shape()
        for _ in range(4000):                               # heavy line work
            x, y = rng.uniform(0, width), rng.uniform(0, height)
            shape.draw_line((x, y), (x + rng.uniform(-90, 90), y + rng.uniform(-90, 90)))
        shape.finish(color=(0.1, 0.1, 0.35), width=0.35)
        shape.commit()
        page.insert_image(pymupdf.Rect(1900, 80, 2280, 330), pixmap=picture)
        page.insert_text((120, 160), f"STEEL FRAMING PLAN {number + 1}", fontsize=40)
        for k in range(MARKUPS - 1):                        # markups
            x, y = 150 + (k % 6) * 340, 300 + (k // 6) * 220
            if k % 3 == 0:
                note = page.add_freetext_annot(pymupdf.Rect(x, y, x + 220, y + 60),
                                               f"Check weld {number}.{k}", fontsize=14,
                                               fill_color=(1, 1, 0.6))
                note.update()
            elif k % 3 == 1:
                box = page.add_rect_annot(pymupdf.Rect(x, y, x + 200, y + 120))
                box.set_colors(stroke=(1, 0, 0))
                box.update()
            else:
                line = page.add_line_annot((x, y), (x + 180, y + 90))
                line.set_colors(stroke=(0, 0.5, 0))
                line.update()
        page.add_stamp_annot(pymupdf.Rect(1700, 1300, 2200, 1550), stamp=stamp)
    document.save(str(path), deflate=True)
    return str(path)


# -- driving the window ---------------------------------------------------------

def _pump(app, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.004)


def _settle(app, view, limit: float = 60.0, previews: bool = False) -> None:
    """Until nothing is moving and nothing on screen is still to be drawn —
    with *previews*, until every page's preview is in too."""
    from calcforge.io import pdftiles

    tiles = pdftiles.TILES
    deadline = time.monotonic() + limit
    quiet = 0
    while time.monotonic() < deadline and quiet < 25:
        app.processEvents()
        settling = getattr(view, "_zoom_settled", None)
        waiting = [key for key in tiles._waiting if not getattr(key, "preview", False)]
        busy = (tiles.held() or waiting or view.glide.timer.isActive()
                or (settling is not None and settling.isActive()))
        if previews and not busy:
            busy = any(not tiles.has_preview(frame.page.pdf_key, int(frame.page.pdf_page_index),
                                             True, frame.markups_drawn_alone())
                       for frame in view.scene().frames)
        quiet = 0 if busy else quiet + 1
        time.sleep(0.005)
    assert time.monotonic() < deadline, "the set never settled"
    _pump(app, 0.05)


def _shown(window, viewport) -> QImage:
    """What the window holds: its own pixels, cut to the canvas."""
    held = window.backingStore().paintDevice()
    corner = viewport.mapTo(window, QPoint(0, 0))
    return held.copy(QRect(corner, viewport.size())).convertToFormat(QImage.Format_RGB32)


def _blank_pixels(view, image: QImage) -> int:
    """How many pixels inside the pages on screen are the white of a sheet
    with nothing drawn on it."""
    import numpy

    raw = numpy.frombuffer(image.constBits(), numpy.uint8, image.sizeInBytes())
    pixels = raw.reshape(image.height(), image.bytesPerLine())[:, :image.width() * 4] \
        .reshape(image.height(), image.width(), 4)[:, :, :3]
    white = (pixels >= 254).all(axis=2)
    seen = QRect(QPoint(0, 0), view.viewport().size())
    count = 0
    for frame in view.scene().frames:
        box = view.mapFromScene(frame.mapRectToScene(frame.page_rect())).boundingRect()
        box = box.intersected(seen).adjusted(4, 4, -4, -4)
        if box.width() <= 0 or box.height() <= 0:
            continue
        count += int(white[box.top():box.bottom(), box.left():box.right()].sum())
    return count


class _Frames:
    """The window's own work, frame by frame, while a gesture runs."""

    def __init__(self, app, window, view):
        self.app, self.window, self.view = app, window, view
        self.work: list = []
        self.blank: list = []

    def _turn(self, before=None) -> None:
        start = time.thread_time()
        if before is not None:
            before()
        self.app.processEvents()
        took = (time.thread_time() - start) * 1000.0
        if took > 0.3:                       # something was done this turn
            self.work.append(took)
            self.blank.append(_blank_pixels(self.view, _shown(self.window,
                                                              self.view.viewport())))

    def wheel(self, notches: int, at: QPointF, every: float, scroll: bool) -> None:
        viewport = self.view.viewport()
        for _ in range(abs(notches)):
            event = QWheelEvent(at, QPointF(viewport.mapToGlobal(at.toPoint())),
                                QPoint(0, 0), QPoint(0, 120 if notches > 0 else -120),
                                Qt.NoButton,
                                Qt.ControlModifier if scroll else Qt.NoModifier,
                                Qt.NoScrollPhase, False)
            self._turn(lambda: QApplication.sendEvent(viewport, event))
            end = time.monotonic() + every
            while time.monotonic() < end:
                time.sleep(0.006)            # a frame apart
                self._turn()

    def glide_out(self, seconds: float = 0.6) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            time.sleep(0.006)
            self._turn()

    def check(self, what: str) -> None:
        assert self.work, f"{what}: nothing was drawn"
        ordered = sorted(self.work)
        median = statistics.median(ordered)
        p95 = ordered[min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)]
        assert median < MEDIAN_BUDGET and p95 < P95_BUDGET, (
            f"{what}: the window's work per frame was {median:.1f} ms (median), "
            f"{p95:.1f} ms (95th percentile) over {len(ordered)} frames")
        assert not any(self.blank), (
            f"{what}: a page on screen was left blank: {max(self.blank)} white "
            f"pixels in one frame")


@pytest.fixture(scope="module")
def heavy_set(tmp_path_factory):
    return _heavy_set(tmp_path_factory.mktemp("steel") / "steel.pdf")


@pytest.fixture
def heavy_window(window, qapp, heavy_set):
    window.resize(1280, 860)
    window.show()
    qapp.processEvents()
    window.open_from_command_line(heavy_set)
    view = window.view
    _settle(qapp, view, previews=True)
    yield window
    window.hide()


def test_scrolling_a_big_set_keeps_to_the_frame_budget_and_no_page_is_blank(heavy_window, qapp):
    window, view = heavy_window, heavy_window.view
    middle = QPointF(view.viewport().width() / 2, view.viewport().height() / 2)
    view.fit_width()
    _settle(qapp, view)
    frames = _Frames(qapp, window, view)
    frames.wheel(-14, middle, every=0.09, scroll=True)       # a person's pace
    frames.glide_out()
    frames.wheel(-30, middle, every=0.01, scroll=True)       # a flick
    frames.glide_out()
    frames.check("scrolling at fit width")

    # a whole page a screen, flicked through sheets never drawn at this zoom:
    # each shows its preview until its squares come
    view.turn_to_page(0)
    view.fit_page()
    _settle(qapp, view)
    frames = _Frames(qapp, window, view)
    frames.wheel(-40, middle, every=0.012, scroll=True)
    frames.glide_out()
    frames.check("flicking through the set at fit page")

    # the scroll bar's thumb dragged down the whole set: every frame a page
    # nothing sharper has been drawn of yet
    bar = view.verticalScrollBar()
    frames = _Frames(qapp, window, view)
    start, end = bar.value(), bar.maximum()
    for step in range(1, 31):
        frames._turn(lambda step=step: bar.setValue(start + (end - start) * step // 30))
        time.sleep(0.012)
        frames._turn()
    frames.glide_out(0.3)
    frames.check("dragging the scroll bar through the set")


def test_zooming_a_big_set_by_wheel_keeps_to_the_frame_budget_and_no_page_is_blank(
        heavy_window, qapp):
    window, view = heavy_window, heavy_window.view
    view.turn_to_page(3)
    view.fit_page()
    _settle(qapp, view)
    at = QPointF(view.viewport().width() * 0.4, view.viewport().height() * 0.45)
    frames = _Frames(qapp, window, view)
    frames.wheel(12, at, every=0.06, scroll=False)           # in, notch by notch
    frames.glide_out()
    frames.wheel(-22, at, every=0.03, scroll=False)          # and right out
    frames.glide_out()
    frames.check("zooming by wheel")
    assert view.zoom() < 0.15, view.zoom()


def test_a_settled_view_is_exactly_what_a_fresh_start_draws(heavy_window, qapp):
    """Once still, nothing of the soft pictures that stood in is left: the
    window is pixel for pixel what it is when everything is drawn afresh at
    that zoom (within antialiasing rounding)."""
    import numpy

    from calcforge.io import pdftiles

    window, view = heavy_window, heavy_window.view
    viewport = view.viewport()
    at = QPointF(viewport.width() * 0.6, viewport.height() * 0.5)
    frames = _Frames(qapp, window, view)
    frames.wheel(6, at, every=0.03, scroll=False)
    frames.wheel(-3, at, every=0.03, scroll=False)
    frames.wheel(-8, at, every=0.01, scroll=True)
    _settle(qapp, view)
    viewport.repaint()
    qapp.processEvents()
    after_gestures = _shown(window, viewport)

    pdftiles.TILES.forget()                  # nothing drawn: everything afresh
    for frame in view.scene().frames:
        frame.layer.clear()
        frame.update()
    _settle(qapp, view)
    viewport.repaint()
    qapp.processEvents()
    fresh = _shown(window, viewport)

    def pixels(image):
        raw = numpy.frombuffer(image.constBits(), numpy.uint8, image.sizeInBytes())
        return raw.reshape(image.height(), image.bytesPerLine())[:, :image.width() * 4] \
            .reshape(image.height(), image.width(), 4)[:, :, :3].astype(int)

    apart = numpy.abs(pixels(after_gestures) - pixels(fresh)).max(axis=2)
    assert int((apart > 8).sum()) == 0, (
        f"{int((apart > 8).sum())} pixels differ from a fresh start, by up to {apart.max()}")


# -- the pieces ---------------------------------------------------------------------

def test_every_page_has_a_preview_drawn_in_the_background(heavy_window):
    from calcforge.io import pdftiles

    view = heavy_window.view
    for frame in view.scene().frames:
        page = frame.page
        picture = pdftiles.TILES.preview(page.pdf_key, b"", int(page.pdf_page_index),
                                         frame.page_rect(), True,
                                         ask=False, without=frame.markups_drawn_alone())
        assert picture is not None
        assert max(picture.width(), picture.height()) == pdftiles.PREVIEW_EDGE


def test_previews_wait_behind_what_the_screen_wants(qapp):
    """The render processes take what the screen wants first, newest first,
    and only then the previews, in the order they were asked for."""
    from calcforge.io import pdftiles

    worker = pdftiles._Worker()
    wanted = worker._wanted
    keys = [pdftiles.SheetKey("pdf", i, True, (), pdftiles.PREVIEW_EDGE) for i in range(3)]
    tiles = [pdftiles.TileKey("pdf", 0, 1.0, col, 0, True) for col in range(2)]
    for key in keys:
        wanted.add(key)
        worker.submit(key, b"%PDF-", 100.0, 100.0, later=True)
    for key in tiles:
        wanted.add(key)
        worker.submit(key, b"%PDF-", 100.0, 100.0)
    order = []
    while (job := worker._next()) is not None:
        order.append(job[0])
    assert order == [tiles[1], tiles[0]] + keys


def test_a_preview_asked_for_on_screen_jumps_the_queue(qapp):
    from calcforge.io import pdftiles

    cache = pdftiles.TileCache()
    submitted = []

    class Worker:
        def submit(self, key, data, width, height, later=False):
            submitted.append((key, later))

    cache._worker = Worker()
    page = QRectF(0, 0, 595, 842)
    for index in range(3):
        cache.preview("pdf", b"%PDF-", index, page, later=True)
    assert [later for _key, later in submitted] == [True, True, True]
    cache.preview("pdf", b"%PDF-", 2, page)                  # now wanted on screen
    assert submitted[-1] == (submitted[2][0], False)
    cache.preview("pdf", b"%PDF-", 2, page)
    assert len(submitted) == 4, "and only once"
    cache._worker = None


def test_squares_of_pages_left_behind_are_given_up_but_not_their_pictures(qapp):
    from calcforge.io import pdftiles

    cache = pdftiles.TileCache()
    cache._ask = lambda key, *args, **kw: cache._waiting.add(key)
    page = QRectF(0, 0, 2384, 1684)
    for index in range(4):
        cache.tiles("pdf", b"%PDF-", index, page, 1.0, page)
        cache.sheet("pdf", b"%PDF-", index, page)
    cache.give_up_out_of_sight({("pdf", 2)})
    left = {key.index for key in cache._waiting if isinstance(key, pdftiles.TileKey)}
    assert left == {2}
    assert any(isinstance(key, pdftiles.SheetKey) and key.index == 0
               for key in cache._waiting), "a page's picture is kept asked for"


def test_pages_tell_qt_their_markups_stay_in_without_changing_what_a_click_finds(
        window, qapp):
    """A page whose markups all lie inside it tells Qt so, and Qt then
    passes it by when it is not being repainted; a page with a markup out on
    the desk does not, and the moment a markup starts to move its page stops
    saying so — a markup is found where it is, on the page or off it."""
    from PySide6.QtWidgets import QGraphicsItem

    from calcforge.items.shapes import RectItem

    window.show()
    qapp.processEvents()
    view = window.view
    frame = view.scene().frames[0]
    item = RectItem()
    item.rect = QRectF(0, 0, 40, 30)
    frame.add_markup(item, QPointF(60, 60))

    def painted_a_moment_later():
        for _ in range(8):
            time.sleep(0.15)
            qapp.processEvents()
            view.viewport().repaint()

    def told() -> bool:
        return bool(frame.flags() & QGraphicsItem.ItemContainsChildrenInShape)

    painted_a_moment_later()
    assert told(), "every markup inside the page: it says so"
    assert item in view.scene().items(item.mapToScene(QPointF(20, 15)))

    item.setPos(QPointF(frame.page_rect().right() + 120, 20))     # out on the desk
    assert not told(), "a markup moving: straight away it no longer says so"
    assert item in view.scene().items(item.mapToScene(QPointF(20, 15)))
    painted_a_moment_later()
    assert not told(), "and with a markup off the page it does not say so again"
    assert item in view.scene().items(item.mapToScene(QPointF(20, 15)))

    item.setPos(QPointF(80, 80))
    painted_a_moment_later()
    assert told()
    assert item in view.scene().items(item.mapToScene(QPointF(20, 15)))


def test_the_same_stamp_on_every_sheet_is_one_picture(tmp_path):
    """A set stamped on every sheet carries a copy of the stamp each; it is
    drawn and kept once, and every sheet's stamp shows that one picture."""
    from calcforge.core.document import Document
    from calcforge.io import pdfio
    from calcforge.pdf import engine

    import pymupdf

    path = _heavy_set(tmp_path / "stamped.pdf", pages=4)
    source = pymupdf.open(path)
    prints = set()
    for index in range(source.page_count):
        page = source[index]
        for annotation in page.annots():
            if annotation.type[1] == "Stamp":
                prints.add(engine.appearance_fingerprint(source, index, annotation.xref))
    assert len(prints) == 1 and None not in prints

    document = Document()
    found = pdfio.markups(path, list(range(4)), keep_the_look=True, document=document)
    pictures = {payload.get("their_picture_asset") for made in found.values()
                for payload in made if payload.get("their_picture_asset")}
    assert len(pictures) == 1, pictures
    assert len(document.assets) == 1
