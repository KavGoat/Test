"""Words in markups hold still (the user, 2026-10-19, on Windows: "text
inside markups flicker a little bit and have a slight size change when click
on it or placing other markup or when I select something and revert to
correct size after").

What it was. A markup nobody is touching is drawn from its page's squares
(ui/markuplayer.py); one picked out, just changed or beside a markup being
placed is drawn live for a moment, then goes back. The two drawings were not
the same picture:

- the squares lie on whole pixels of the screen, so at 125 % and 150 % (and
  wherever the page sits part way through a pixel) everything in them lands
  up to half a pixel from where the live drawing put it, and every letter
  falls on the pixels differently;
- in a square, a picture with a clear background, text can only be smoothed
  in grey; live, on the opaque window, it was smoothed in the screen's
  colour fringes (ClearType on Windows) — heavier and a touch wider.

So the words jumped and swelled as a markup went live and back. Now the live
drawing is laid on the squares' pixels and page text is smoothed in grey
both ways.

Each scale runs in a process of its own (the screen's scale is fixed when the
application starts). A text box and a callout are drawn and typed into with
the real tools; then the text box is clicked, the callout is clicked, a
rectangle is placed and the selection is let go, and after each step the
words are held against the same words once everything has settled into the
squares again — and against the words before anything was touched.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

#: a channel this far apart is rounding in the smoothing, not a moved letter
TOLERANCE = 24


@pytest.mark.parametrize("scale", ["1.0", "1.25", "1.5"])
def test_words_in_markups_do_not_move_or_resize_when_they_go_live_and_back(scale, tmp_path):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR=scale)
    run = subprocess.run([sys.executable, os.path.abspath(__file__), scale, str(tmp_path)],
                         env=env, cwd=REPO, capture_output=True, text=True, timeout=600)
    lines = [line for line in run.stdout.splitlines() if line.startswith("{")]
    assert run.returncode == 0 and lines, run.stdout[-3000:] + run.stderr[-3000:]
    report = json.loads(lines[-1])
    assert report["ratio"] == pytest.approx(float(scale))
    # the steps did take the markups out of the squares and back, or the
    # comparison would prove nothing
    assert report["went_live"], report
    assert report["back_in_squares"], report
    bad = {name: found for name, found in report["steps"].items() if found}
    assert not bad, (f"at {scale}: words differ from the settled drawing "
                     f"(pixels, largest difference): {bad}; pictures in {tmp_path}")


# -- the driver, run in its own process ---------------------------------------

def _sandbox() -> str:
    import tempfile

    box = tempfile.mkdtemp(prefix="calcforge-text-steady-")
    for variable in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
                     "XDG_STATE_HOME"):
        os.environ[variable] = os.path.join(box, variable.lower())
        os.makedirs(os.environ[variable], exist_ok=True)
    os.environ["CALCFORGE_SETTINGS_FILE"] = os.path.join(box, "settings.ini")
    os.environ["CALCFORGE_MARKFORGE_SETTINGS_FILE"] = os.path.join(box, "absent.ini")
    return box


def _drive(scale: str, out: str) -> dict:
    import numpy
    import pymupdf
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication

    from calcforge.app import build_application

    app = QApplication.instance() or build_application([])
    from calcforge.io import pdftiles
    from calcforge.items.text import CalloutItem, TextItem
    from calcforge.ui.mainwindow import MainWindow
    from tests.test_usability import click, drag, type_text

    box = _sandbox()
    path = os.path.join(box, "sheet.pdf")
    document = pymupdf.open()
    document.new_page(width=842, height=595)
    document.save(path)

    window = MainWindow()
    window.confirm_discard = lambda: True
    window.interactive_prompts = False
    window.resize(1280, 860)
    window.show()
    app.processEvents()
    window.open_from_command_line(path)
    view = window.view
    viewport = view.viewport()
    frame = view.scene().frames[0]
    layer = frame.layer
    origin = frame.mapToScene(QPointF(0, 0))

    def at(x, y):
        """A point on the page, in the scene, where the helpers want it."""
        return origin.x() + x, origin.y() + y

    def pump(seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.003)

    def settle() -> None:
        """Until every markup is back in the squares and they are drawn."""
        end = time.monotonic() + 8
        while time.monotonic() < end:
            pump(0.05)
            viewport.grab()
            if layer.wanted is None or layer.hot or layer.pending or pdftiles.TILES.held():
                continue
            step, seen = layer.wanted[0], layer.wanted[1]
            squares = layer.tiles.get(step, {})
            if any(layer._needs(squares.get(key)) for key in layer._keys(seen, step)
                   if layer._drawn_in(QRectF(key[0] * 256 / step, key[1] * 256 / step,
                                             256 / step, 256 / step))):
                continue
            idle = layer._idle
            if idle is None or not idle.isActive():
                break
        pump(0.05)

    def pixels(image: QImage):
        image = image.convertToFormat(QImage.Format_RGB32)
        raw = numpy.frombuffer(image.constBits(), numpy.uint8, image.sizeInBytes())
        return raw.reshape(image.height(), image.bytesPerLine())[:, :image.width() * 4] \
            .reshape(image.height(), image.width(), 4)[:, :, :3].astype(int)

    # a text box and a callout, drawn and typed into as a person does
    window.select_tool("text")
    drag(view, *at(100, 120), *at(330, 160))
    type_text(view, "Hello World 123 Wy")
    view.end_item_edit()
    window.select_tool("callout")
    click(view, *at(330, 300))
    click(view, *at(420, 220))
    type_text(view, "Callout gjq")
    view.end_item_edit()
    window.select_tool("select")
    text = [i for i in view.scene().ordered_markups() if type(i) is TextItem][-1]
    callout = [i for i in view.scene().ordered_markups() if isinstance(i, CalloutItem)][-1]
    view.scene().clearSelection()
    settle()

    def words(item):
        """Where the item's words are on the device: (top, left, bottom,
        right) in whole pixels, and the fraction the page sits off them."""
        ratio = viewport.devicePixelRatioF()
        rect = item.text_rect().adjusted(1, 1, -1, -1)
        corner = view.mapFromScene(item.mapToScene(rect.topLeft()))
        far = view.mapFromScene(item.mapToScene(rect.bottomRight()))
        exact = view.viewportTransform().map(item.mapToScene(rect.topLeft()))
        return ((int(corner.y() * ratio) + 1, int(corner.x() * ratio) + 1,
                 int(far.y() * ratio) - 1, int(far.x() * ratio) - 1),
                (round(exact.x() * ratio % 1, 3), round(exact.y() * ratio % 1, 3)))

    def cut(image, place):
        top, left, bottom, right = place
        return image[top:bottom, left:right]

    def differs(name, one, other):
        apart = numpy.abs(one - other).max(axis=2)
        wrong = apart > TOLERANCE
        if not wrong.any():
            return []
        for label, picture in (("shown", one), ("settled", other)):
            height, width = picture.shape[:2]
            rgb = numpy.ascontiguousarray(picture.astype(numpy.uint8))
            QImage(rgb.data, width, height, width * 3, QImage.Format_RGB888) \
                .scaled(width * 4, height * 4).save(os.path.join(out, f"{scale}-{name}-{label}.png"))
        return [int(wrong.sum()), int(apart.max())]

    image = pixels(viewport.grab().toImage())
    before = {id(item): (cut(image, words(item)[0]), words(item)[1])
              for item in (text, callout)}
    found, went_live, back = {}, False, True

    def step(name, action):
        nonlocal went_live, back
        action()
        app.processEvents()
        live = [item for item in (text, callout) if item not in layer.members]
        went_live = went_live or bool(live)
        now = pixels(viewport.grab().toImage())
        places = {id(item): words(item) for item in (text, callout)}
        settle()
        back = back and text in layer.members and callout in layer.members
        settled = pixels(viewport.grab().toImage())
        for item in (text, callout):
            place, phase = places[id(item)]
            label = f"{name}-{type(item).__name__}"
            # just after the step, against the same view settled
            found[label] = differs(label, cut(now, place), cut(settled, place))
            # and against the words before anything was touched, where the
            # page lies on the pixels as it did then
            first, first_phase = before[id(item)]
            if first_phase == phase:
                found[label + "-before"] = differs(label + "-before", first,
                                                   cut(settled, place)[:first.shape[0],
                                                                       :first.shape[1]])

    def place_rectangle():
        window.select_tool("rect")
        drag(view, *at(600, 380), *at(680, 440))
        window.select_tool("select")

    step("click-text", lambda: click(view, *at(110, 125)))
    step("click-callout", lambda: click(view, *at(425, 225)))
    step("place-rect", place_rectangle)
    step("select-nothing", lambda: click(view, *at(700, 120)))
    # and each of them changed outright, the way the squares let go of a
    # markup that is picked out and dragged, restyled or typed into
    step("changed", lambda: (layer.touched(text), layer.touched(callout)))
    report = {"ratio": viewport.devicePixelRatioF(), "went_live": went_live,
              "back_in_squares": back, "steps": found}
    window.close()
    pdftiles.TILES.shut_down()
    return report


if __name__ == "__main__":
    sys.path.insert(0, REPO)
    print(json.dumps(_drive(sys.argv[1], sys.argv[2])), flush=True)
    os._exit(0)          # past multiprocessing's exit hooks: the renderers are stopped
