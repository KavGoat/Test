"""Zooming without repainting (the user, 2026-10-02: "While zooming things
repaint ... This needs to be extra fast").

What a zoom looked like before: every notch asked the render processes for a
new set of squares, each frame drew every zoom it had passed through stacked
on top of each other (thirty thousand pictures in one gesture on a marked-up
Bluebeam file), and squares landed one by one over a blurred page all the way
through. These hold the pieces that put that right.
"""
from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QImage, QPixmap, QWheelEvent


def _cache():
    from calcforge.io import pdftiles

    cache = pdftiles.TileCache()
    asked: list = []

    def ask(key, data, page, sheet):
        asked.append(key)
        cache._waiting.add(key)

    cache._ask = ask
    return cache, asked


def _fill(cache, keys):
    """Every one of *keys* arrives, a plain square."""
    for key in keys:
        cache._waiting.add(key)
        size = round(1024)
        image = QImage(size, size, QImage.Format_RGB32)
        image.fill(Qt.white)
        cache._tile_arrived(key, image)


PAGE = QRectF(0, 0, 2384, 1684)                       # A1


def test_a_zoom_on_the_way_draws_one_zoom_under_it_not_every_zoom_passed(qapp):
    """Stand-ins: the nearest zoom that covers the page, not a stack."""
    from calcforge.io import pdftiles

    cache, asked = _cache()
    rungs = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2]
    for rung in rungs:
        asked.clear()
        cache.tiles("pdf", b"%PDF-", 0, PAGE, rung, PAGE)
        _fill(cache, [key for key in asked if isinstance(key, pdftiles.TileKey)])
    asked.clear()
    ready, missing, covered = cache.tiles("pdf", b"%PDF-", 0, PAGE, 1.3, PAGE,
                                          say_covered=True)
    assert missing and covered
    sizes = {round(pixmap.width() / where.width(), 2) for where, pixmap in ready}
    assert sizes == {1.2}, f"one zoom stands in, the nearest: {sizes}"


def test_a_sharper_zoom_is_preferred_to_a_softer_one(qapp):
    from calcforge.io import pdftiles

    cache, asked = _cache()
    for rung in (1.0, 2.0):
        asked.clear()
        cache.tiles("pdf", b"%PDF-", 0, PAGE, rung, PAGE)
        _fill(cache, [key for key in asked if isinstance(key, pdftiles.TileKey)])
    ready, _missing = cache.tiles("pdf", b"%PDF-", 0, PAGE, 1.4, PAGE)
    assert {round(p.width() / w.width(), 2) for w, p in ready} == {2.0}


def test_nothing_new_is_asked_for_while_a_zoom_is_moving(qapp):
    from calcforge.io import pdftiles

    cache, asked = _cache()
    cache.hold(5.0)
    ready, missing = cache.tiles("pdf", b"%PDF-", 0, PAGE, 3.0, PAGE)
    assert missing and not [k for k in asked if isinstance(k, pdftiles.TileKey)]
    cache.let_go()
    cache.tiles("pdf", b"%PDF-", 0, PAGE, 3.0, PAGE)
    assert [k for k in asked if isinstance(k, pdftiles.TileKey)], \
        "and they are asked for once it stops"


def test_the_screen_goes_sharp_all_at_once(qapp):
    """Until every square on screen is in, the zoom before stands in for all
    of them: no patchwork of sharp squares over a blurred page."""
    from calcforge.io import pdftiles

    cache, asked = _cache()
    cache.tiles("pdf", b"%PDF-", 0, PAGE, 1.0, PAGE)
    _fill(cache, [k for k in asked if isinstance(k, pdftiles.TileKey)])
    asked.clear()
    cache.tiles("pdf", b"%PDF-", 0, PAGE, 2.0, PAGE)
    wanted = [k for k in asked if isinstance(k, pdftiles.TileKey)]
    assert len(wanted) > 1
    _fill(cache, wanted[1:])                         # all but one are in
    ready, missing = cache.tiles("pdf", b"%PDF-", 0, PAGE, 2.0, PAGE)
    assert missing
    assert {round(p.width() / w.width(), 2) for w, p in ready} == {1.0}, \
        "the old zoom stands in for the whole screen until the last arrives"
    _fill(cache, wanted[:1])
    ready, missing = cache.tiles("pdf", b"%PDF-", 0, PAGE, 2.0, PAGE)
    assert not missing
    assert {round(p.width() / w.width(), 2) for w, p in ready} == {2.0}


def test_the_index_follows_the_cache_out(qapp, monkeypatch):
    """Squares thrown out to keep inside the memory ceiling are gone from the
    index too — a stand-in that no longer exists is a crash or a hole."""
    from calcforge.io import pdftiles

    cache, asked = _cache()
    monkeypatch.setattr(pdftiles, "CACHE_BYTES", 1024 * 1024 * 4 * 3)
    for rung in (0.5, 1.0, 2.0):
        asked.clear()
        cache.tiles("pdf", b"%PDF-", 0, PAGE, rung, PAGE)
        _fill(cache, [k for k in asked if isinstance(k, pdftiles.TileKey)])
    indexed = {key for rungs in cache._index.values() for keys in rungs.values()
               for key in keys}
    assert indexed == set(cache._tiles)
    cache.forget("pdf")
    assert not cache._index


def test_a_markup_preview_is_made_for_its_own_box(qapp):
    """A markup's preview is drawn for the box its file gives it — x, y, width,
    height, as the markup's own drawing reads it — or it stands in for the
    wrong patch of the page (a picture missing mid-zoom, 2026-10-02)."""
    from calcforge.io import pdftiles

    cache, asked = _cache()
    box = QRectF(643, 180, 169, 207)
    cache.annotation_preview("pdf", b"%PDF-", 0, PAGE, 0.5, 12, box)
    assert asked
    left, top, right, bottom = asked[0].box
    assert (left, top, right, bottom) == (643, 180, 812, 387)
    asked.clear()
    _fill(cache, list(cache._waiting))
    cache.annotation_preview("pdf", b"%PDF-", 0, PAGE, 3.0, 12, box)
    assert not asked, "once is enough: a preview is any zoom of it"
    ready = cache.annotation_tiles("pdf", b"%PDF-", 0, PAGE, 3.0, box, 12, box)
    assert ready, "and it stands in while the zoom wanted is drawn"


@pytest.fixture
def pdf_window(qapp, tmp_path, window):
    import fitz

    path = tmp_path / "markups.pdf"
    document = fitz.open()
    for number in range(3):
        page = document.new_page(width=595, height=842)
        page.insert_text((72, 100), f"Sheet {number + 1}", fontsize=24)
        note = page.add_freetext_annot(fitz.Rect(300, 300, 500, 360), "A note",
                                       fontsize=12)
        note.update()
    document.save(path)
    window.confirm_discard = lambda: True
    window.open_path(str(path))
    window.rebuild_scenes()
    qapp.processEvents()
    return window


def _wheel(view, notches, at):
    from calcforge.ui import preferences

    held = Qt.NoModifier if preferences.current().wheel_zooms() else Qt.ControlModifier
    event = QWheelEvent(at, view.viewport().mapToGlobal(at), QPoint(0, 0),
                        QPoint(0, 120 * notches), Qt.NoButton, held,
                        Qt.NoScrollPhase, False)
    from PySide6.QtWidgets import QApplication
    QApplication.sendEvent(view.viewport(), event)


def test_a_notch_of_zoom_glides_and_keeps_the_point_under_the_pointer(pdf_window, qapp):
    view = pdf_window.view
    view.set_zoom(1.0)
    at = QPointF(view.viewport().width() * 0.3, view.viewport().height() * 0.4)
    under = view.viewportTransform().inverted()[0].map(at)
    start = view.zoom()
    _wheel(view, 1, at)
    assert view.zoom() == pytest.approx(start), "a notch glides, it does not jump"
    deadline = time.monotonic() + 3
    seen = set()
    while view.glide.zooming is not None and time.monotonic() < deadline:
        qapp.processEvents()
        seen.add(round(view.zoom(), 4))
    assert len(seen) > 2, "it passes through zooms on the way"
    assert view.zoom() == pytest.approx(start * 1.0015 ** 120, rel=1e-6)
    still = view.viewportTransform().map(under)
    assert abs(still.x() - at.x()) <= 1.0 and abs(still.y() - at.y()) <= 1.0


def test_a_zoom_on_the_wheel_waits_then_draws_the_zoom_it_stopped_at(pdf_window, qapp):
    from calcforge.io import pdftiles

    view = pdf_window.view
    at = QPointF(view.viewport().rect().center())
    _wheel(view, 2, at)
    assert pdftiles.TILES.held(), "nothing new is drawn while it moves"
    view.finish_scrolling()
    deadline = time.monotonic() + 3
    while pdftiles.TILES.held() and time.monotonic() < deadline:
        qapp.processEvents()
    assert not pdftiles.TILES.held()
    deadline = time.monotonic() + 1
    while view._zoom_settled.isActive() and time.monotonic() < deadline:
        qapp.processEvents()
    view.viewport().grab()
    step = pdftiles.zoom_step(view.zoom() * view.viewport().devicePixelRatioF())
    assert any(isinstance(key, pdftiles.TileKey) and key.scale == step
               for key in list(pdftiles.TILES._waiting) + list(pdftiles.TILES._tiles)), \
        "once it settles, the zoom it stopped at is asked for"


def test_markups_off_screen_have_their_look_made_ahead(pdf_window, qapp):
    """A Bluebeam markup scrolled or zoomed into view is not a hole first."""
    from calcforge.io import pdftiles

    view = pdf_window.view
    scene = view.scene()
    pdf_window.go_to_page(0)
    view.viewport().grab()
    qapp.processEvents()
    third = scene.frames[2]
    markups = [item for item in third.markups() if item.still_theirs]
    assert markups
    source = third.page.pdf_key
    wanted = {key.xref for key in list(pdftiles.TILES._waiting) + list(pdftiles.TILES._tiles)
              if isinstance(key, pdftiles.AnnotationTileKey) and key.source == source
              and key.index == third.page.pdf_page_index}
    assert {item.from_annotation for item in markups} <= wanted


def test_a_sharp_idle_screen_is_drawn_ahead_at_twice_the_zoom(qapp):
    """So a zoom in shrinks something sharper rather than stretching something
    softer: the page never goes soft and then sharpens (the user, 2026-10-02:
    "Why is there page sharpening? Bluebeam handles it much better")."""
    from calcforge.io import pdftiles

    cache, asked = _cache()
    view = QRectF(0, 0, 600, 400)
    cache.tiles("pdf", b"%PDF-", 0, PAGE, 1.0, view)
    cache.ahead("pdf", b"%PDF-", 0, PAGE, 1.0, view)
    assert not [k for k in asked if k.scale == 2.0], "not while the screen is still coming"
    _fill(cache, list(cache._waiting))
    asked.clear()
    cache.ahead("pdf", b"%PDF-", 0, PAGE, 1.0, view)
    ahead = [k for k in asked if isinstance(k, pdftiles.TileKey)]
    assert ahead and {k.scale for k in ahead} == {2.0}
    # a zoom elsewhere on the page does not give them up
    cache.tiles("pdf", b"%PDF-", 0, PAGE, 1.0, view)
    assert set(ahead) <= cache._waiting
    _fill(cache, ahead)
    ready, missing, covered = cache.tiles("pdf", b"%PDF-", 0, PAGE, 1.7, view,
                                          say_covered=True)
    assert missing and covered
    assert {round(p.width() / w.width(), 2) for w, p in ready} == {2.0}, \
        "zoomed in, the sharper drawing stands in"


def test_nothing_is_drawn_ahead_while_a_zoom_moves(qapp):
    cache, asked = _cache()
    cache.hold(5.0)
    cache.ahead("pdf", b"%PDF-", 0, PAGE, 1.0, QRectF(0, 0, 600, 400))
    assert not asked


def test_a_zoom_has_where_it_is_going_drawn_while_it_moves(pdf_window, qapp):
    """The user, 2026-10-08: "on zoom it is blurry and then takes a split
    second to render, Bluebeam ... it's always sharp". The squares of the zoom
    a glide is heading for are asked for at the notch, not after it stops."""
    from calcforge.io import pdftiles

    view = pdf_window.view
    view.set_zoom(1.0)
    at = QPointF(view.viewport().rect().center())
    _wheel(view, 3, at)
    target = view.glide.zooming[0]
    step = pdftiles.zoom_step(target * view.viewport().devicePixelRatioF())
    assert pdftiles.TILES.held(), "still moving"
    asked = [key for key in list(pdftiles.TILES._waiting) + list(pdftiles.TILES._tiles)
             if isinstance(key, pdftiles.TileKey) and key.scale == step]
    assert asked, "the zoom it is heading for is being drawn already"
    view.finish_scrolling()


def test_a_zoom_heading_elsewhere_gives_up_the_last_ones(qapp):
    from calcforge.io import pdftiles

    cache, asked = _cache()
    view = QRectF(0, 0, 600, 400)
    cache.hold(5.0)
    cache.expect("pdf", b"%PDF-", 0, PAGE, 2.0, view)
    first = {k for k in cache._waiting if k.scale == 2.0}
    assert first
    cache.expect("pdf", b"%PDF-", 0, PAGE, 3.0, view)
    assert not first & cache._waiting, "the zoom that is no longer coming"
    assert {k.scale for k in cache._waiting} == {3.0}
    # and a repaint mid-zoom does not give them up either
    cache.tiles("pdf", b"%PDF-", 0, PAGE, 2.5, view)
    assert {k.scale for k in cache._waiting} == {3.0}
