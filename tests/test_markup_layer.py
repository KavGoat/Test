"""A page's markups drawn into squares (ui/markuplayer.py).

The user, 2026-10-05: "Try putting like a 1000 markups on one sheet and
trying scrolling or zooming or panning or adding pages. It starts lagging."
Markups nobody is touching are drawn once into squares and shown from them;
these hold that it looks exactly the same, that nothing changed is ever shown
stale, and that markups drawn that way are still markups — clicked, moved,
deleted, printed.
"""
from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QImage


def _pump(qapp, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.002)


def _settled(qapp, view, layer, limit=5.0):
    """Until every markup that can be is in the squares and they are drawn."""
    end = time.monotonic() + limit
    while time.monotonic() < end:
        view.viewport().grab()
        qapp.processEvents()
        if not layer.hot and not layer.pending and layer.members:
            idle = layer._idle
            if idle is None or not idle.isActive():
                break
        time.sleep(0.01)
    view.viewport().grab()
    qapp.processEvents()


def _markups(frame):
    from calcforge.items.measure import MeasureItem  # noqa: F401
    from calcforge.items.shapes import PolyItem, RectItem
    from calcforge.items.text import CalloutItem, TextItem

    made = []
    for i in range(24):
        x, y = 40 + (i % 6) * 90, 40 + (i // 6) * 90
        kind = i % 6
        if kind == 0:
            item = RectItem("rect", QRectF(0, 0, 60, 40))
            item.style.fill = "#88c0ff"
        elif kind == 1:
            item = RectItem("cloud", QRectF(0, 0, 70, 50))
        elif kind == 2:
            item = PolyItem("arrow", [QPointF(0, 0), QPointF(60, 30)])
        elif kind == 3:
            item = TextItem(f"Note {i}", QRectF(0, 0, 70, 30))
        elif kind == 4:
            item = CalloutItem(f"C{i}", QRectF(0, 0, 50, 24), [QPointF(-20, 40)])
        else:
            item = PolyItem("ink", [QPointF(j * 3, 8 * ((j % 4) - 2)) for j in range(20)])
        item.style.opacity = 0.8 if i % 5 == 0 else 1.0
        frame.add_markup(item, QPointF(x, y))
        made.append(item)
    return made


def _image(view):
    return view.viewport().grab().toImage().convertToFormat(QImage.Format_RGB32)


def _close(view) -> float:
    """How much may differ: anti-aliasing only. At a whole-number scale a
    square lands on the same pixels as the markup drawn live; at 125% or 150%
    it can sit up to half a pixel off, which shifts the grey of every edge."""
    ratio = view.viewport().devicePixelRatioF()
    return 0.002 if abs(ratio - round(ratio)) < 1e-6 else 0.012


def _difference(a: QImage, b: QImage) -> float:
    import numpy as np

    def array(image):
        raw = np.frombuffer(bytes(image.constBits()), np.uint8)
        return raw.reshape(image.height(), image.bytesPerLine())[:, :image.width() * 4] \
            .reshape(image.height(), image.width(), 4)[:, :, :3].astype(int)
    first, second = array(a), array(b)
    # A pixel of slack: at a fractional scale (150% on Windows) a square sits
    # up to half a pixel off where the markup would have been drawn live,
    # which moves anti-aliasing, not ink.
    nearest = None
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            shifted = np.roll(np.roll(first, dy, 0), dx, 1)
            off = np.abs(shifted - second).max(axis=2)
            nearest = off if nearest is None else np.minimum(nearest, off)
    return float((nearest > 40).mean())


@pytest.fixture
def busy_page(window, qapp):
    view = window.view
    frame = view.scene().frames[0]
    items = _markups(frame)
    view.set_zoom(1.0)
    view.centerOn(frame.mapToScene(QPointF(280, 200)))
    _settled(qapp, view, frame.layer)
    return window, frame, items


def test_markups_go_into_the_squares_and_look_the_same(busy_page, qapp):
    window, frame, items = busy_page
    layer = frame.layer
    assert len(layer.members) == len(items), "untouched markups are drawn from squares"
    from PySide6.QtWidgets import QGraphicsItem
    assert all(item.flags() & QGraphicsItem.ItemHasNoContents for item in layer.members)
    from_squares = _image(window.view)
    layer.enabled = False
    layer.release_all()
    _pump(qapp, 0.05)
    live = _image(window.view)
    assert _difference(from_squares, live) < _close(window.view)


def test_a_markup_in_the_squares_is_still_clicked_and_moved(busy_page, qapp):
    window, frame, items = busy_page
    view = window.view
    target = items[0]
    assert target in frame.layer.members
    centre = view.mapFromScene(target.mapToScene(target.boundingRect().center()))
    found = view.scene().items(view.mapToScene(centre))
    assert target in found, "drawn from squares, still there to click"
    target.setSelected(True)
    assert target in frame.layer.members, "picked out, it stays in the squares"
    before = _image(view)
    target.moveBy(200, 0)
    assert target not in frame.layer.members, "moved, it is drawn live"
    _pump(qapp, 0.02)
    moved = _image(view)
    # where it was is empty now: no ghost left in a square
    target.setSelected(False)
    _settled(qapp, view, frame.layer)
    again = _image(view)
    assert target in frame.layer.members
    assert _difference(moved, again) < _close(window.view)
    assert _difference(before, moved) > 0.0005


def test_a_picked_out_markup_in_the_squares_shows_its_handles(busy_page, qapp):
    window, frame, items = busy_page
    view = window.view
    for item in items[:3]:
        item.setSelected(True)
    _pump(qapp, 0.05)
    assert all(item in frame.layer.members for item in items[:3])
    with_squares = _image(view)
    frame.layer.enabled = False
    frame.layer.release_all()
    _pump(qapp, 0.05)
    assert _difference(with_squares, _image(view)) < _close(window.view)


def test_a_changed_markup_is_never_shown_stale(busy_page, qapp):
    window, frame, items = busy_page
    view = window.view
    target = items[0]
    target.style.fill = "#ff0000"
    target.update()
    _pump(qapp, 0.02)
    changed = _image(view)
    _settled(qapp, view, frame.layer)
    settled = _image(view)
    assert target in frame.layer.members
    assert _difference(changed, settled) < _close(window.view)
    frame.layer.enabled = False
    frame.layer.release_all()
    _pump(qapp, 0.05)
    assert _difference(settled, _image(view)) < _close(window.view)


def test_a_deleted_markup_goes(busy_page, qapp):
    window, frame, items = busy_page
    view = window.view
    target = items[1]
    frame.remove_markup(target)
    _pump(qapp, 0.02)
    gone = _image(view)
    frame.layer.enabled = False
    frame.layer.release_all()
    _pump(qapp, 0.05)
    assert _difference(gone, _image(view)) < _close(window.view)


def test_markups_in_the_squares_still_print(busy_page, qapp):
    from PySide6.QtGui import QPainter

    window, frame, items = busy_page
    assert frame.layer.members

    def printed():
        image = QImage(595, 842, QImage.Format_RGB32)
        image.fill(Qt.white)
        painter = QPainter(image)
        frame.render_page(painter, QRectF(image.rect()), for_print=True)
        painter.end()
        return image

    with_squares = printed()
    frame.layer.enabled = False
    frame.layer.release_all()
    assert _difference(with_squares, printed()) < 0.001
    blank = QImage(595, 842, QImage.Format_RGB32)
    blank.fill(Qt.white)
    assert _difference(with_squares, blank) > 0.01, "the markups are in the print"


def test_a_thousand_markups_scroll_without_painting_each_one(window, qapp):
    """The point of it: with the squares drawn, a repaint calls no markup's
    paint at all."""
    from calcforge.items.shapes import RectItem

    view = window.view
    frame = view.scene().frames[0]
    for i in range(1000):
        frame.add_markup(RectItem("rect", QRectF(0, 0, 12, 8)),
                         QPointF(20 + (i % 40) * 13, 20 + (i // 40) * 11))
    _settled(qapp, view, frame.layer, limit=15)
    assert len(frame.layer.members) == 1000, (len(frame.layer.pending), len(frame.layer.hot), frame.layer.wanted)
    for item in frame.markups():
        item.setSelected(True)           # all picked out: still from the squares
    qapp.processEvents()
    painted = []
    original = RectItem.paint
    RectItem.paint = lambda self, *a: (painted.append(self), original(self, *a))
    try:
        view.verticalScrollBar().setValue(view.verticalScrollBar().value() + 40)
        view.viewport().grab()
    finally:
        RectItem.paint = original
    assert not painted
