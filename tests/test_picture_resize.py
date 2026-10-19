"""Resizing a picture by its handles (the user, 2026-10-19, on Windows, with a
photo: docs/qa/user_shots/2026-10-19_image_resize_grey_box.jpg): "Issue with
resizing photos and with [a grey] box appearing in the back. Resizing also
should keep aspect locked unless I hold shift. It also had a bug where I was
[resizing] and the image moved while resizing."

What it was:

- The grey box. A page's markups are drawn into squares (ui/markuplayer.py).
  A square wholly inside a picture has every pixel opaque, and Qt then drops
  the alpha channel when it turns the drawing into a pixmap. Made smaller, the
  picture left that square; the part of it it left was cleared — to opaque
  black, there being no alpha to clear — and the dark box stood behind the
  picture, larger than it, until the page was drawn again. It needs a square
  wholly covered, so it showed at 150 % and at Windows' 125 % screen scale.
- The aspect lock. A picture's own corners kept the proportions unless Shift
  was held, but its scale-box corners (the ones just outside it) did the
  opposite: free unless Shift was held. Every corner now keeps them; Shift
  frees them. Edges stretch the one way, as in Revu.
- The picture moving. In proportion, only the width was read and the height
  was then set from the top down, so dragging a top corner moved the bottom of
  the picture; a scale-box corner scaled about the scale box's corner, a few
  points off the picture, so the picture crept with every step of the drag;
  and a turned picture kept turning about its old middle, so after an undo or
  a reopen (both turn it about its middle) it came back somewhere else.

Every drag here is real mouse events through the viewport.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import time

if __name__ == "__main__":                       # the driver, in a process of its own
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPicture
from PySide6.QtWidgets import QApplication

from calcforge.items.media import ImageItem
from calcforge.items.snapshot import SnapshotItem
from tests.test_usability import _mouse, click

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

CORNERS = ("nw", "ne", "se", "sw")
EDGES = ("n", "e", "s", "w")
SCALE_CORNERS = ("scale_nw", "scale_ne", "scale_se", "scale_sw")
OPPOSITE = {"nw": "se", "ne": "sw", "se": "nw", "sw": "ne",
            "n": "s", "s": "n", "e": "w", "w": "e"}


# -- helpers -------------------------------------------------------------------

def _photo(width: int = 240, height: int = 160) -> QImage:
    """A picture like the user's: a dark band of lines over a plain grey."""
    image = QImage(width, height, QImage.Format_ARGB32)
    image.fill(QColor(70, 70, 78))
    painter = QPainter(image)
    painter.fillRect(0, 0, width, height // 2, QColor(30, 40, 60))
    painter.end()
    return image


def _pasted(window, at=QPointF(150, 150), image=None) -> ImageItem:
    """A picture pasted from another program, the way the user put it there."""
    QApplication.clipboard().setImage(image or _photo())
    assert window.paste_picture_from_clipboard()
    picture = next(i for i in window.scene.frames[0].markups() if isinstance(i, ImageItem))
    picture.setPos(at)
    return picture


def _snapshot(window, at=QPointF(150, 150)) -> SnapshotItem:
    recording = QPicture()
    painter = QPainter(recording)
    painter.fillRect(QRectF(0, 0, 200, 120), QColor(40, 90, 40))
    painter.end()
    window.view.begin_snapshot()
    snapshot = SnapshotItem(QRectF(0, 0, 200, 120))
    snapshot.set_picture(recording)
    snapshot.setParentItem(window.scene.frames[0])
    snapshot.setPos(at)
    window.view.commit_snapshot("Add snapshot")
    return next(i for i in window.scene.frames[0].markups() if isinstance(i, SnapshotItem))


def _point(item, key: str) -> QPointF:
    points = dict(item.handle_points())
    points.update(item.scale_points())
    return item.mapToScene(points[key])


def _corner(item, key: str) -> QPointF:
    """Where corner or edge *key* of the picture itself is, on the canvas."""
    return item.mapToScene(item.handle_points()[key])


def _select(window, item) -> None:
    centre = item.mapToScene(item.local_rect().center())
    click(window.view, centre.x(), centre.y())
    assert item.isSelected()


def _drag_handle(window, item, key: str, by: QPointF, steps: int = 8,
                 modifiers=Qt.NoModifier) -> None:
    """Press on handle *key*, move by *by* (canvas points) in steps, let go."""
    view = window.view
    viewport = view.viewport()
    start = _point(item, key)
    QApplication.sendEvent(viewport, _mouse(view, QEvent.MouseButtonPress,
                                            start.x(), start.y(), modifiers=modifiers))
    assert view._mode == "resize" and view._handle_key == key, (view._mode, key)
    for step in range(1, steps + 1):
        x = start.x() + by.x() * step / steps
        y = start.y() + by.y() * step / steps
        QApplication.sendEvent(viewport, _mouse(view, QEvent.MouseMove, x, y,
                                                Qt.NoButton, Qt.LeftButton, modifiers))
    QApplication.sendEvent(viewport, _mouse(view, QEvent.MouseButtonRelease,
                                            start.x() + by.x(), start.y() + by.y(),
                                            modifiers=modifiers))


def _ratio(item) -> float:
    rect = item.local_rect().normalized()
    return rect.width() / rect.height()


def _close(a: QPointF, b: QPointF, within: float = 0.5) -> bool:
    return math.hypot(a.x() - b.x(), a.y() - b.y()) <= within


# -- the aspect lock ---------------------------------------------------------------

@pytest.mark.parametrize("key", CORNERS + SCALE_CORNERS)
def test_a_picture_corner_keeps_its_proportions_and_shift_frees_them(window, key):
    picture = _pasted(window)
    _select(window, picture)
    before = _ratio(picture)
    outward = QPointF(-1 if "w" in key else 1, -1 if "n" in key else 1)
    # pulled out mostly sideways: in proportion it grows both ways
    _drag_handle(window, picture, key, QPointF(outward.x() * 60, outward.y() * 12))
    assert _ratio(picture) == pytest.approx(before, rel=1e-3), key
    assert picture.local_rect().width() > 240 + 40
    # Shift held: free
    _drag_handle(window, picture, key, QPointF(outward.x() * -50, outward.y() * 30),
                 modifiers=Qt.ShiftModifier)
    assert abs(_ratio(picture) - before) > 0.2, key


@pytest.mark.parametrize("key", EDGES)
def test_a_picture_edge_stretches_it_one_way(window, key):
    picture = _pasted(window)
    _select(window, picture)
    rect = picture.local_rect()
    out = {"n": QPointF(0, -40), "s": QPointF(0, 40), "e": QPointF(40, 0),
           "w": QPointF(-40, 0)}[key]
    _drag_handle(window, picture, key, out)
    now = picture.local_rect()
    if key in "ns":
        assert now.width() == pytest.approx(rect.width())
        assert now.height() == pytest.approx(rect.height() + 40, abs=1.0)
    else:
        assert now.height() == pytest.approx(rect.height())
        assert now.width() == pytest.approx(rect.width() + 40, abs=1.0)


def test_a_snapshot_corner_keeps_its_proportions_and_shift_frees_them(window):
    snapshot = _snapshot(window)
    _select(window, snapshot)
    before = _ratio(snapshot)
    for key in ("se", "scale_nw"):
        out = QPointF(-1 if "w" in key else 1, -1 if "n" in key else 1)
        _drag_handle(window, snapshot, key, QPointF(out.x() * 50, out.y() * 5))
        assert _ratio(snapshot) == pytest.approx(before, rel=1e-3), key
    _drag_handle(window, snapshot, "sw", QPointF(30, 40), modifiers=Qt.ShiftModifier)
    assert abs(_ratio(snapshot) - before) > 0.2


def test_the_status_bar_says_what_a_corner_and_shift_do(window):
    picture = _pasted(window)
    _select(window, picture)
    view = window.view
    start = _point(picture, "se")
    viewport = view.viewport()
    QApplication.sendEvent(viewport, _mouse(view, QEvent.MouseButtonPress, start.x(), start.y()))
    QApplication.sendEvent(viewport, _mouse(view, QEvent.MouseMove, start.x() + 10,
                                            start.y() + 10, Qt.NoButton, Qt.LeftButton))
    assert "Shift: free resize" in window.status_hint.text()
    QApplication.sendEvent(viewport, _mouse(view, QEvent.MouseMove, start.x() + 20,
                                            start.y() + 10, Qt.NoButton, Qt.LeftButton,
                                            Qt.ShiftModifier))
    assert window.status_hint.text().startswith("Free resize")
    QApplication.sendEvent(viewport, _mouse(view, QEvent.MouseButtonRelease,
                                            start.x() + 20, start.y() + 10))
    start = _point(picture, "e")
    QApplication.sendEvent(viewport, _mouse(view, QEvent.MouseButtonPress, start.x(), start.y()))
    QApplication.sendEvent(viewport, _mouse(view, QEvent.MouseMove, start.x() + 10,
                                            start.y(), Qt.NoButton, Qt.LeftButton))
    assert "edge stretches one way" in window.status_hint.text()
    QApplication.sendEvent(viewport, _mouse(view, QEvent.MouseButtonRelease,
                                            start.x() + 10, start.y()))


def test_other_markups_keep_shift_for_proportions(window):
    from calcforge.items.shapes import RectItem
    window.view.begin_snapshot()
    box = RectItem(QRectF(0, 0, 200, 100))
    box.setParentItem(window.scene.frames[0])
    box.setPos(150, 150)
    window.view.commit_snapshot("Add rectangle")
    box = next(i for i in window.scene.frames[0].markups() if isinstance(i, RectItem))
    _select(window, box)
    _drag_handle(window, box, "se", QPointF(60, 10))
    assert _ratio(box) != pytest.approx(2.0, rel=1e-2)          # free
    box.set_local_rect(QRectF(0, 0, 200, 100))
    anchor = _corner(box, "nw")
    _drag_handle(window, box, "se", QPointF(60, 10), modifiers=Qt.ShiftModifier)
    assert _ratio(box) == pytest.approx(2.0, rel=1e-3)          # Shift: in proportion
    assert _close(_corner(box, "nw"), anchor)


def test_the_rotation_handle_of_a_picture_turns_freely(window):
    picture = _pasted(window)
    _select(window, picture)
    centre = picture.mapToScene(picture.local_rect().center())
    top = _point(picture, "rot")
    # a turn of about 20 degrees, not a multiple of 15: Shift is not held
    radius = centre.y() - top.y()
    angle = math.radians(20)
    end = QPointF(centre.x() + radius * math.sin(angle), centre.y() - radius * math.cos(angle))
    _drag_handle(window, picture, "rot", end - top, steps=4)
    assert abs(picture.rotation() - round(picture.rotation() / 15) * 15) > 1


# -- the picture stays where it is -------------------------------------------------

def _anchor_test(window, picture, keys) -> None:
    for key in keys:
        own = key[len("scale_"):] if key.startswith("scale_") else key
        fixed = OPPOSITE[own]
        for direction in (1, -1):
            before = _corner(picture, fixed)
            # outwards, then back in: along the picture's own axes, so a turn
            # of it does not turn the drag into the other way
            local = {"n": QPointF(0, -1), "s": QPointF(0, 1), "e": QPointF(1, 0),
                     "w": QPointF(-1, 0)}
            way = QPointF(0, 0)
            for letter in own:
                way += local[letter]
            origin = picture.mapToScene(QPointF(0, 0))
            along = picture.mapToScene(way * 30 * direction) - origin
            _drag_handle(window, picture, key, along + QPointF(0.3, -0.4) * direction)
            after = _corner(picture, fixed)
            assert _close(before, after), (key, direction, before, after)


@pytest.mark.parametrize("turn", [0, 30, 90])
def test_the_opposite_corner_or_edge_stays_put(window, turn):
    picture = _pasted(window, at=QPointF(200, 220))
    if turn:
        picture.set_item_rotation(turn)
    _select(window, picture)
    _anchor_test(window, picture, CORNERS + EDGES + SCALE_CORNERS)
    _anchor_test(window, picture, CORNERS)           # free (Shift) as well below
    for key in CORNERS:
        fixed = _corner(picture, OPPOSITE[key])
        _drag_handle(window, picture, key, QPointF(7, 11), modifiers=Qt.ShiftModifier)
        assert _close(_corner(picture, OPPOSITE[key]), fixed), key


def test_the_opposite_corner_stays_put_on_a_turned_page_and_a_turned_view(window):
    picture = _pasted(window, at=QPointF(200, 220))
    window.rotate_page(0, clockwise=True)
    picture = next(i for i in window.scene.frames[0].markups() if isinstance(i, ImageItem))
    assert round(picture.rotation()) % 360 == 90
    window.view.set_zoom(1.0)
    window.view.centerOn(picture.mapToScene(picture.local_rect().center()))
    _select(window, picture)
    _anchor_test(window, picture, ("nw", "se", "e", "scale_ne"))
    window.view.rotate_view(clockwise=True)
    window.view.set_zoom(1.0)
    window.view.centerOn(picture.mapToScene(picture.local_rect().center()))
    _anchor_test(window, picture, ("sw", "n", "scale_se"))


def test_a_turned_picture_resized_comes_back_where_it_was_after_undo_redo_and_reopen(
        window, tmp_path):
    picture = _pasted(window, at=QPointF(200, 220))
    picture.set_item_rotation(30)
    _select(window, picture)
    _drag_handle(window, picture, "nw", QPointF(-30, -10))
    where = {key: _corner(picture, key) for key in CORNERS}
    size = picture.local_rect().size()
    stack = window.undo_stack
    stack.undo()
    stack.redo()
    again = next(i for i in window.scene.frames[0].markups() if isinstance(i, ImageItem))
    for key in CORNERS:
        assert _close(_corner(again, key), where[key]), key
    path = str(tmp_path / "turned.pdf")
    window.document.path = path
    assert window.save_document()
    window.open_from_command_line(path)
    reopened = next(i for i in window.scene.frames[0].markups() if isinstance(i, ImageItem))
    assert reopened.local_rect().size().width() == pytest.approx(size.width(), abs=0.01)
    assert reopened.local_rect().size().height() == pytest.approx(size.height(), abs=0.01)
    for key in CORNERS:
        assert _close(_corner(reopened, key), where[key]), key


# -- undo, and the file -------------------------------------------------------------

def test_one_resize_is_one_undo_step_and_the_file_keeps_the_size(window, tmp_path):
    picture = _pasted(window)
    _select(window, picture)
    stack = window.undo_stack
    count = stack.count()
    before = picture.local_rect().size()
    _drag_handle(window, picture, "se", QPointF(60, 40), steps=12)
    assert stack.count() == count + 1
    assert "Resize" in stack.undoText()
    grown = next(i for i in window.scene.frames[0].markups()
                 if isinstance(i, ImageItem)).local_rect().size()
    assert grown.width() == pytest.approx(before.width() * 1.25, rel=0.02)
    stack.undo()
    back = next(i for i in window.scene.frames[0].markups() if isinstance(i, ImageItem))
    assert back.local_rect().size() == before
    stack.redo()
    path = str(tmp_path / "picture.pdf")
    window.document.path = path
    assert window.save_document()
    window.open_from_command_line(path)
    reopened = next(i for i in window.scene.frames[0].markups() if isinstance(i, ImageItem))
    assert reopened.local_rect().width() == pytest.approx(grown.width(), abs=0.01)
    assert reopened.local_rect().height() == pytest.approx(grown.height(), abs=0.01)
    assert reopened.pixmap() is not None and not reopened.pixmap().isNull()


# -- nothing left behind, on screen ------------------------------------------------

@pytest.mark.parametrize("scale", ["1", "1.25"])
def test_resizing_leaves_nothing_behind_the_picture(scale, tmp_path):
    """In a process of its own, at the screen's scale (fixed at start): drags
    of corners and edges at 100 % and 150 %, with and without Shift, pausing
    long enough for the page to take the picture into its squares; after
    every step, and once it has settled, what the window shows and a full
    repaint of it hold nothing but the page outside the picture, and the
    picture's own colours inside it."""
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR=scale)
    run = subprocess.run([sys.executable, os.path.abspath(__file__), scale, str(tmp_path)],
                         env=env, cwd=REPO, capture_output=True, text=True, timeout=600)
    lines = [line for line in run.stdout.splitlines() if line.startswith("{")]
    assert run.returncode == 0 and lines, run.stdout[-3000:] + run.stderr[-3000:]
    report = json.loads(lines[-1])
    assert report["ratio"] == pytest.approx(float(scale))
    assert report["checked"] > 100
    assert not report["bad"], f"left behind or wrong (see {tmp_path}): {report['bad']}"


# -- the driver, run in its own process ----------------------------------------------

def _sandbox() -> None:
    import tempfile

    box = tempfile.mkdtemp(prefix="calcforge-picture-resize-")
    for variable in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
                     "XDG_STATE_HOME"):
        os.environ[variable] = os.path.join(box, variable.lower())
        os.makedirs(os.environ[variable], exist_ok=True)
    os.environ["CALCFORGE_SETTINGS_FILE"] = os.path.join(box, "settings.ini")
    os.environ["CALCFORGE_MARKFORGE_SETTINGS_FILE"] = os.path.join(box, "absent.ini")


def _drive(scale: str, out: str) -> dict:
    import numpy
    from PySide6.QtCore import QPoint, QRect

    from calcforge.app import build_application

    _sandbox()
    app = QApplication.instance() or build_application([])
    from calcforge.io import pdftiles
    from calcforge.ui.mainwindow import MainWindow

    window = MainWindow()
    window.confirm_discard = lambda: True
    window.interactive_prompts = False
    window.resize(1280, 860)
    window.show()
    app.processEvents()
    window.new_document(confirm=False)
    view = window.view
    viewport = view.viewport()

    def pump(seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.005)

    def shown() -> QImage:
        held = window.backingStore().paintDevice().copy()
        ratio = viewport.devicePixelRatioF()
        corner = viewport.mapTo(window, QPoint(0, 0))
        left, top = math.floor(corner.x() * ratio), math.floor(corner.y() * ratio)
        right = math.ceil((corner.x() + viewport.width()) * ratio)
        bottom = math.ceil((corner.y() + viewport.height()) * ratio)
        return held.copy(QRect(left, top, right - left, bottom - top)) \
            .convertToFormat(QImage.Format_RGB32)

    def afresh() -> QImage:
        viewport.repaint()
        app.processEvents()
        return shown()

    def pixels(image: QImage):
        height, width = image.height(), image.width()
        raw = numpy.frombuffer(image.constBits(), numpy.uint8, image.sizeInBytes())
        return raw.reshape(height, image.bytesPerLine())[:, :width * 4] \
            .reshape(height, width, 4)[:, :, [2, 1, 0]].astype(int)        # BGRA in memory

    frame = window.document.pages[0].frame
    QApplication.clipboard().setImage(_photo(200, 140))
    window.paste_picture_from_clipboard()
    picture = next(i for i in frame.markups() if isinstance(i, ImageItem))
    picture.setPos(QPointF(160, 160))
    checked, bad = 0, {}

    def check(name: str, image: QImage) -> None:
        """Outside the picture (and its handles): only the white page, or a
        snap guide's blue. Inside it: its own two colours."""
        nonlocal checked
        checked += 1
        ratio = viewport.devicePixelRatioF()
        found = pixels(image)
        height, width = found.shape[:2]

        def box(scene_rect: QRectF, grow: float):
            view_rect = view.mapFromScene(scene_rect).boundingRect()
            return (max(math.floor((view_rect.left() - grow) * ratio), 0),
                    max(math.floor((view_rect.top() - grow) * ratio), 0),
                    min(math.ceil((view_rect.right() + 1 + grow) * ratio), width),
                    min(math.ceil((view_rect.bottom() + 1 + grow) * ratio), height))

        page = box(frame.mapRectToScene(frame.page_rect()), -6)
        outside = numpy.zeros((height, width), bool)
        outside[page[1]:page[3], page[0]:page[2]] = True
        outside[:2, :] = outside[-2:, :] = False         # the view's own border
        outside[:, :2] = outside[:, -2:] = False
        held = box(picture.sceneBoundingRect(), 3)
        outside[held[1]:held[3], held[0]:held[2]] = False
        red, green, blue = found[..., 0], found[..., 1], found[..., 2]
        neutral = (abs(red - green) < 24) & (abs(green - blue) < 24)
        dark = (red + green + blue) < 3 * 170
        left = outside & neutral & dark
        problems = []
        if left.sum() > 12:
            problems.append(f"{int(left.sum())} dark pixels outside the picture")
        # inside: sampled away from its edges and from the line between halves
        rect = picture.local_rect()
        for u in (0.15, 0.35, 0.5, 0.65, 0.85):
            for v, colour in ((0.2, (30, 40, 60)), (0.35, (30, 40, 60)),
                              (0.65, (70, 70, 78)), (0.85, (70, 70, 78))):
                spot = view.mapFromScene(picture.mapToScene(QPointF(
                    rect.left() + rect.width() * u, rect.top() + rect.height() * v)))
                x, y = int(spot.x() * ratio), int(spot.y() * ratio)
                if 0 <= x < width and 0 <= y < height:
                    got = found[y, x]
                    if max(abs(int(got[i]) - colour[i]) for i in range(3)) > 24:
                        problems.append(f"({u},{v}) is {tuple(int(c) for c in got)}")
        if problems:
            bad[name] = problems[:4]
            image.save(os.path.join(out, f"{name}.png"))

    def both(name: str) -> None:
        check(name + "-window", shown())
        check(name + "-repainted", afresh())

    plan = [("s", (0, 70), False), ("e", (80, 0), False), ("se", (-110, -40), False),
            ("scale_se", (70, 30), False), ("n", (0, 50), False),
            ("nw", (-40, -60), True), ("scale_nw", (60, 50), False),
            ("w", (50, 0), False), ("ne", (-30, 40), False), ("sw", (50, 20), True)]
    for zoom in (1.0, 1.5):
        view.set_zoom(zoom)
        view.centerOn(picture.mapToScene(picture.local_rect().center()))
        pump(1.0)
        centre = picture.mapToScene(picture.local_rect().center())
        if not picture.isSelected():
            for kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
                QApplication.sendEvent(viewport, _mouse(view, kind, centre.x(), centre.y()))
        pump(1.0)
        both(f"{zoom}-start")
        for number, (key, (dx, dy), shift) in enumerate(plan):
            modifiers = Qt.ShiftModifier if shift else Qt.NoModifier
            start = _point(picture, key)
            QApplication.sendEvent(viewport, _mouse(view, QEvent.MouseButtonPress,
                                                    start.x(), start.y(), modifiers=modifiers))
            for step in range(1, 7):
                QApplication.sendEvent(viewport, _mouse(
                    view, QEvent.MouseMove, start.x() + dx * step / 6,
                    start.y() + dy * step / 6, Qt.NoButton, Qt.LeftButton, modifiers))
                app.processEvents()
                if step == 3:
                    pump(0.7)          # held still: the page takes it into its squares
                both(f"{zoom}-{number}{key}-step{step}")
            QApplication.sendEvent(viewport, _mouse(view, QEvent.MouseButtonRelease,
                                                    start.x() + dx, start.y() + dy,
                                                    modifiers=modifiers))
            app.processEvents()
            both(f"{zoom}-{number}{key}-let-go")
            pump(1.0)
            both(f"{zoom}-{number}{key}-settled")
    report = {"ratio": viewport.devicePixelRatioF(), "checked": checked, "bad": bad}
    window.close()
    pdftiles.TILES.shut_down()
    return report


if __name__ == "__main__":
    print(json.dumps(_drive(sys.argv[1], sys.argv[2])), flush=True)
    os._exit(0)
