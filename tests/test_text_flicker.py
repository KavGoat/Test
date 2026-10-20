"""A text box's words are the same pixels in every frame, however they reach
the screen (the user, 2026-10-20, on Windows: "Text flicker still there — add
a text box and write something, then draw a rectangle and move it around and
you can see it"; and before that, words that grew by a percent or were
spaced differently for a moment as a markup was picked out or hovered).

A markup's words reached the screen from the page's squares (drawn by the
processor into a clear picture), and live onto the window — while the
squares at the zoom on screen were still to come, and while the markup was
picked out, changed or neighboured one just drawn. On the graphics card (on
by default) live words were OpenGL's own; on Windows the processor smooths
words on the opaque window against a gamma curve and words in a clear
picture without. A rectangle dragged past the text box took it from one to
the other and back. The words are now always drawn into a clear picture of
their own at the device's pixels and laid on the screen as they are
(ui/markuplayer.paint_words).

Driven as the user does it: a Text Box drawn and typed into with the Text
Box tool, a Rectangle drawn with the Rectangle tool, then dragged about with
real mouse events, the window's own pixels (its backing store, partial
repaints and all) read after every frame. The graphics card is tried in a
window of its own under a virtual X display, where there is one.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QGuiApplication, QImage, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from tests.test_usability import drag, press_key, type_text

ZOOMS = [1.0, 0.75, 1.5, 1.237, 0.913]
WORDS = "Flicker check: the quick brown fox jumps"
#: set in the child process that draws with the graphics card
CHILD = "CALCFORGE_FLICKER_ON_THE_CARD"


def _pump(qapp, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.003)


def _pixels(image: QImage) -> np.ndarray:
    image = image.convertToFormat(QImage.Format_RGB32)
    raw = np.frombuffer(bytes(image.constBits()), np.uint8)
    return raw.reshape(image.height(), image.bytesPerLine())[:, :image.width() * 4] \
        .reshape(image.height(), image.width(), 4)[:, :, :3].astype(int)


def _on_screen(window) -> np.ndarray:
    """What the window shows: its own pixels as last painted, partial
    repaints included (not a fresh paint of the whole view, as grab is)."""
    viewport = window.view.viewport()
    shot = QGuiApplication.primaryScreen().grabWindow(window.winId())
    corner = viewport.mapTo(window, QPoint(0, 0))
    ratio = shot.devicePixelRatio()
    return _pixels(shot.toImage().copy(QRect(
        round(corner.x() * ratio), round(corner.y() * ratio),
        round(viewport.width() * ratio), round(viewport.height() * ratio))))


def _move(viewport, point: QPoint, buttons=Qt.LeftButton) -> None:
    QApplication.sendEvent(viewport, QMouseEvent(
        QEvent.MouseMove, QPointF(point), QPointF(viewport.mapToGlobal(point)),
        Qt.NoButton, buttons, Qt.NoModifier))


def _device_box(view, item, rect) -> tuple:
    """*rect* of *item* on the viewport, in device pixels: (top, bottom,
    left, right)."""
    ratio = view.viewport().devicePixelRatioF()
    box = view.mapFromScene(item.mapToScene(rect)).boundingRect()
    return (int(box.top() * ratio), int(box.bottom() * ratio),
            int(box.left() * ratio), int(box.right() * ratio))


def _text_box_and_rectangle(window, qapp, zoom: float):
    """A Text Box with a line of words and a Rectangle below it, both drawn
    with their tools, at *zoom*."""
    window.show()
    QTest.qWaitForWindowExposed(window)
    view = window.view
    view.set_zoom(zoom)
    frame = view.scene().frames[0]
    view.centerOn(frame.mapToScene(QPointF(260, 200)))
    _pump(qapp, 0.2)

    def at(x, y):
        return frame.mapToScene(QPointF(x, y))

    window.select_tool("text")
    a, b = at(100, 100), at(330, 140)
    drag(view, a.x(), a.y(), b.x(), b.y())
    box = view.editing_item()
    type_text(view, WORDS)
    press_key(view, Qt.Key_Escape)
    _pump(qapp, 0.3)
    window.select_tool("rect")
    a, b = at(120, 170), at(200, 230)
    drag(view, a.x(), a.y(), b.x(), b.y())
    window.select_tool("select")
    rect = next(item for item in view.scene().ordered_markups() if item is not box)
    assert box.text() == WORDS
    return view, frame, box, rect


def _words(view, box) -> tuple:
    """Where the box's words are: inside its border, clear of it."""
    top, bottom, left, right = _device_box(view, box, box.text_rect())
    return top + 2, bottom - 2, left + 2, right - 2


def _clear_of(view, item, words) -> np.ndarray:
    """The part of the words' region *item* (with its handles and turning
    handle) does not cover."""
    top, bottom, left, right = words
    mask = np.ones((bottom - top, right - left), bool)
    ratio = view.viewport().devicePixelRatioF()
    over = view.mapFromScene(item.mapToScene(item.boundingRect())).boundingRect() \
        .adjusted(-14, -44, 14, 14)
    y0, y1 = int(over.top() * ratio) - top, int(over.bottom() * ratio) - top
    x0, x1 = int(over.left() * ratio) - left, int(over.right() * ratio) - left
    mask[max(y0, 0):max(y1, 0), max(x0, 0):max(x1, 0)] = False
    return mask


def drag_the_rectangle_about(window, qapp, zoom: float) -> list:
    """Drag the rectangle up into, along and across the text box, with
    pauses (so the page's squares are drawn in between); how many of the
    words' pixels changed in each frame, where the rectangle is not."""
    view, frame, box, rect = _text_box_and_rectangle(window, qapp, zoom)
    _pump(qapp, 1.0)
    viewport = view.viewport()
    origin = rect.pos()
    start = view.mapFromScene(rect.mapToScene(rect.boundingRect().center()))
    QTest.mousePress(viewport, Qt.LeftButton, Qt.NoModifier, start)
    _move(viewport, start + QPoint(1, 1))
    qapp.processEvents()
    words = _words(view, box)
    top, bottom, left, right = words
    before = _on_screen(window)[top:bottom, left:right]
    first_clear = _clear_of(view, rect, words)
    changed = []
    point = start
    for step in range(36):
        point = start + QPoint(step * 8, (-1) ** step * 3 - 70 + step)
        _move(viewport, point)
        qapp.processEvents()
        if step % 12 == 11:
            _pump(qapp, 0.6)
        now = _on_screen(window)[top:bottom, left:right]
        clear = _clear_of(view, rect, words) & first_clear
        changed.append(int(((np.abs(now - before).max(axis=2) > 0) & clear).sum()))
    QTest.mouseRelease(viewport, Qt.LeftButton, Qt.NoModifier, point)
    assert (rect.pos() - origin).manhattanLength() > 100, "the rectangle was dragged"
    return changed


@pytest.mark.parametrize("zoom", ZOOMS)
def test_the_words_stay_put_while_a_rectangle_is_dragged_past(window, qapp, zoom):
    changed = drag_the_rectangle_about(window, qapp, zoom)
    assert not any(changed), (
        f"the text box's words changed in {sum(1 for c in changed if c)} of "
        f"{len(changed)} frames (up to {max(changed)} pixels)")


@pytest.mark.parametrize("zoom", [1.0, 1.5, 1.237])
def test_the_words_stay_put_as_the_box_is_picked_out_hovered_and_let_go(window, qapp, zoom):
    view, frame, box, rect = _text_box_and_rectangle(window, qapp, zoom)
    _pump(qapp, 1.0)
    viewport = view.viewport()
    words = _words(view, box)
    top, bottom, left, right = words

    def shown():
        qapp.processEvents()
        return _on_screen(window)[top:bottom, left:right]

    settled = shown()
    middle = view.mapFromScene(box.mapToScene(box.text_rect().center()))
    seen = []
    QTest.mouseClick(viewport, Qt.LeftButton, Qt.NoModifier, middle)
    assert box.isSelected()
    seen.append(("picked out", shown()))
    for dx in range(-60, 61, 15):
        _move(viewport, middle + QPoint(dx, 2), Qt.NoButton)
        seen.append(("hovered", shown()))
    _pump(qapp, 0.8)
    seen.append(("picked out, still", shown()))
    away = view.mapFromScene(frame.mapToScene(QPointF(420, 320)))
    QTest.mouseClick(viewport, Qt.LeftButton, Qt.NoModifier, away)
    assert not box.isSelected()
    seen.append(("let go", shown()))
    _pump(qapp, 1.0)
    seen.append(("let go, settled", shown()))
    for when, pixels in seen:
        moved = int((np.abs(pixels - settled).max(axis=2) > 0).sum())
        assert moved == 0, f"{when}: {moved} of the words' pixels changed"


# ---------------------------------------------------------------------------
# the graphics card
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not os.environ.get(CHILD), reason="run in its own process, on the card")
@pytest.mark.parametrize("zoom", [1.0, 0.75, 1.5, 1.237])
def test_on_the_card(window, qapp, zoom):
    assert window.view.gpu, "drawing with the graphics card"
    changed = drag_the_rectangle_about(window, qapp, zoom)
    assert not any(changed), (
        f"on the card, the words changed in {sum(1 for c in changed if c)} of "
        f"{len(changed)} frames (up to {max(changed)} pixels)")


def _opengl_under_x() -> bool:
    if shutil.which("xvfb-run") is None:
        return False
    probe = ("from PySide6.QtWidgets import QApplication\n"
             "from PySide6.QtGui import QOpenGLContext\n"
             "app = QApplication([])\n"
             "raise SystemExit(0 if QOpenGLContext().create() else 1)\n")
    env = dict(os.environ, QT_QPA_PLATFORM="xcb")
    try:
        done = subprocess.run(["xvfb-run", "-a", sys.executable, "-c", probe], env=env,
                              capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0


@pytest.mark.skipif(bool(os.environ.get(CHILD)), reason="the child itself")
def test_the_words_stay_put_on_the_graphics_card():
    """The same drag in a window drawn with OpenGL (Preferences ▸ Draw with
    the graphics card, on by default), under a virtual X display."""
    if not _opengl_under_x():
        pytest.skip("no X display with OpenGL to draw on")
    env = dict(os.environ, QT_QPA_PLATFORM="xcb", **{CHILD: "1"})
    done = subprocess.run(
        ["xvfb-run", "-a", "-s", "-screen 0 1600x1000x24", sys.executable, "-m", "pytest",
         "-p", "no:cacheprovider", "-q", "-rA", "-x", os.path.abspath(__file__), "-k", "on_the_card"],
        env=env, capture_output=True, text=True, timeout=600,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    tail = "\n".join(line for line in done.stdout.splitlines()
                     if "frames" in line or "PASSED" in line or "FAILED" in line
                     or "SKIPPED" in line or "Error" in line)
    assert done.returncode == 0, tail
    assert done.stdout.count("PASSED ") == 4, tail
