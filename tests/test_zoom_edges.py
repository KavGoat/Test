"""Zooming leaves nothing behind at the page edges (the user, 2026-10-18, on
Windows: "Zooming in and out leaves small artefacts on the page edges").

What it was. At 125 % and 150 % a pixel of the screen is not a whole number
of the window's own pixels, and two things then depended on what had been
painted before:

- a square of the page reached up to a pixel past the sheet (MuPDF draws
  whole pixels), and one of another zoom standing in reached further, over
  the shadow — a sliver along the right and bottom edges that the repaint of
  the page, when its squares came in, did not always reach;
- the part of the window repainted when they came in ended part way through
  a pixel, and the desk was filled only that far, so that pixel came out half
  desk, half whatever was under it: a faint line beside the page.

Each scale runs in a process of its own (the screen's scale is fixed when the
application starts), zooms the way a person does — notches of the real wheel
over the window and Ctrl++ / Ctrl+- on the keyboard — waits for the page to
settle, and holds what the window shows against the same view repainted from
scratch. Then it has parts of the window repainted the way squares coming in
do, and holds that against a full repaint too.
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

#: a channel this far apart is antialiasing rounding, not an artefact
TOLERANCE = 8


@pytest.mark.parametrize("scale", ["1.0", "1.25", "1.5"])
def test_zooming_by_wheel_and_keys_leaves_no_artefacts_at_page_edges(scale, tmp_path):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR=scale)
    run = subprocess.run([sys.executable, os.path.abspath(__file__), scale, str(tmp_path)],
                         env=env, cwd=REPO, capture_output=True, text=True, timeout=600)
    lines = [line for line in run.stdout.splitlines() if line.startswith("{")]
    assert run.returncode == 0 and lines, run.stdout[-3000:] + run.stderr[-3000:]
    report = json.loads(lines[-1])
    assert report["ratio"] == pytest.approx(float(scale))
    assert report["zooms"] == 12, "every notch and key zoomed"
    bad = {name: found for name, found in report["steps"].items() if found}
    assert not bad, (f"at {scale}: the window differs from a full repaint "
                     f"(pixels, largest difference): {bad}; diffs in {tmp_path}")


# -- the driver, run in its own process ---------------------------------------

def _sandbox() -> None:
    import tempfile

    box = tempfile.mkdtemp(prefix="calcforge-zoom-edges-")
    for variable in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
                     "XDG_STATE_HOME"):
        os.environ[variable] = os.path.join(box, variable.lower())
        os.makedirs(os.environ[variable], exist_ok=True)
    os.environ["CALCFORGE_SETTINGS_FILE"] = os.path.join(box, "settings.ini")
    os.environ["CALCFORGE_MARKFORGE_SETTINGS_FILE"] = os.path.join(box, "absent.ini")
    return box


def _drawing(folder: str) -> str:
    """Sheets tinted to their edges, with lines and markups along them, so
    anything drawn past an edge or left over from another zoom shows."""
    import pymupdf

    path = os.path.join(folder, "edges.pdf")
    document = pymupdf.open()
    for number in range(3):
        width, height = 1190.6, 841.9
        page = document.new_page(width=width, height=height)
        page.draw_rect(page.rect, color=None, fill=(0.80, 0.88, 1.0))
        page.draw_rect(page.rect + (6, 6, -6, -6), color=(0, 0, 0), width=1.5)
        for x in range(0, int(width) + 5, 37):
            page.draw_line((x, 0), (x, height), color=(0.2, 0.2, 0.6), width=0.4)
        for y in range(0, int(height) + 5, 41):
            page.draw_line((0, y), (width, y), color=(0.6, 0.2, 0.2), width=0.3)
        page.insert_text((72, 100), f"Sheet {number + 1}", fontsize=24)
        note = page.add_freetext_annot(pymupdf.Rect(width - 160, height - 50, width - 2,
                                                    height - 2),
                                       "Edge note", fontsize=12, fill_color=(1, 1, 0.6))
        note.update()
        box = page.add_rect_annot(pymupdf.Rect(1, 1, 140, 60))
        box.set_colors(stroke=(1, 0, 0))
        box.update()
    document.save(path)
    return path


def _drive(scale: str, out: str) -> dict:
    import math

    import numpy
    from PySide6.QtCore import QPoint, QPointF, QRect, Qt
    from PySide6.QtGui import QImage, QWheelEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from calcforge.app import build_application

    app = QApplication.instance() or build_application([])
    from calcforge.io import pdftiles
    from calcforge.ui.mainwindow import MainWindow

    window = MainWindow()
    window.confirm_discard = lambda: True
    window.interactive_prompts = False
    window.resize(1280, 860)
    window.show()
    app.processEvents()
    window.open_from_command_line(_drawing(_sandbox()))
    view = window.view
    viewport = view.viewport()

    def settle(limit: float = 10.0) -> None:
        deadline = time.monotonic() + limit
        quiet = 0
        while time.monotonic() < deadline and quiet < 30:
            app.processEvents()
            settling = getattr(view, "_zoom_settled", None)
            busy = (pdftiles.TILES.held() or pdftiles.TILES._waiting
                    or view.glide.timer.isActive()
                    or (settling is not None and settling.isActive()))
            quiet = 0 if busy else quiet + 1
            time.sleep(0.005)
        for _ in range(5):
            app.processEvents()
            time.sleep(0.01)

    def shown() -> QImage:
        """What the window holds: its own pixels, cut to the canvas."""
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
            .reshape(height, width, 4)[:, :, :3].astype(int)

    def differs(name: str, now: QImage, whole: QImage) -> list:
        apart = numpy.abs(pixels(now) - pixels(whole)).max(axis=2)
        wrong = apart > TOLERANCE
        if not wrong.any():
            return []
        now.save(os.path.join(out, f"{name}-window.png"))
        whole.save(os.path.join(out, f"{name}-repainted.png"))
        marked = QImage(whole.size(), QImage.Format_RGB32)
        marked.fill(Qt.white)
        for y, x in zip(*numpy.nonzero(wrong)):
            marked.setPixel(int(x), int(y), 0xffff0000)
        marked.save(os.path.join(out, f"{name}-diff.png"))
        return [int(wrong.sum()), int(apart.max())]

    def wheel(notches: int, at: QPointF) -> None:
        for _ in range(abs(notches)):
            event = QWheelEvent(at, QPointF(viewport.mapToGlobal(at.toPoint())),
                                QPoint(0, 0), QPoint(0, 120 if notches > 0 else -120),
                                Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
            QApplication.sendEvent(viewport, event)
            for _ in range(4):                 # a hand's pace between notches
                app.processEvents()
                time.sleep(0.004)

    settle()
    size = viewport.size()
    spots = [QPointF(size.width() * x, size.height() * y)
             for x, y in ((0.5, 0.5), (0.2, 0.3), (0.85, 0.75), (0.35, 0.9), (0.7, 0.1))]
    steps = [("wheel", 3, 0), ("wheel", -2, 1), ("ctrl+", 0, 0), ("wheel", 5, 2),
             ("ctrl-", 0, 0), ("wheel", -4, 3), ("ctrl+", 0, 0), ("wheel", -3, 4),
             ("ctrl-", 0, 0), ("wheel", 2, 2), ("ctrl+", 0, 0), ("ctrl-", 0, 0)]
    found, zooms = {}, 0
    for number, (kind, notches, spot) in enumerate(steps):
        before = view.zoom()
        if kind == "wheel":
            wheel(notches, spots[spot])
        else:
            key = Qt.Key_Plus if kind == "ctrl+" else Qt.Key_Minus
            QTest.keyClick(viewport, key, Qt.ControlModifier)
        settle()
        zooms += abs(view.zoom() - before) > 1e-6
        name = f"{scale}-{number:02d}-{kind}"
        found[name] = differs(name, shown(), afresh())
        # the squares of each page on screen coming in again: the page, and
        # only the page, is repainted (DocumentScene._draw_what_arrived)
        for frame in view.scene().frames:
            frame.update(frame.page_rect())
        app.processEvents()
        found[name + "-squares"] = differs(name + "-squares", shown(), afresh())
    # parts of the window repainted at odd places
    for number in range(12):
        x = (number * 97) % max(size.width() - 60, 1)
        y = (number * 61) % max(size.height() - 60, 1)
        afresh()
        viewport.update(QRect(x, y, 41 + number * 37, 33 + number * 29))
        app.processEvents()
        name = f"{scale}-part-{number:02d}"
        found[name] = differs(name, shown(), afresh())
    report = {"ratio": viewport.devicePixelRatioF(), "zooms": zooms, "steps": found}
    window.close()
    pdftiles.TILES.shut_down()             # and the render processes with it
    return report


if __name__ == "__main__":
    sys.path.insert(0, REPO)
    print(json.dumps(_drive(sys.argv[1], sys.argv[2])), flush=True)
    os._exit(0)          # past multiprocessing's exit hooks: the renderers are stopped
