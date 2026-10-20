"""Zoomed out, a drawing's line work is crisp and dark, as Bluebeam's (the
user, 2026-10-20: "Fuzzy is not good enough, speed is better but Bluebeam
looks better in zoomed out mode and more legible even though quality looks
the same").

Smoothed at the zoom on screen, a hairline a pixel wide that fell half way
between two rows of pixels came out as two rows of half grey, and one that
fell on a row as one row of black: the same sheet's lines were black or pale
by where they happened to land, double lines ran into a grey band, coloured
lines went pastel. Zoomed out (fewer pixels than points), the page's line
work is now drawn onto the pixels (MuPDF's centre-of-pixel rule): every
hairline exactly one solid row of pixels, unbroken along a slope. Words stay
smoothed, and so does line work from 100 % up.

On a synthetic sheet only — thin lines at every fraction of a pixel, a
sloping hairline, hatching, a red line and small words.
"""
from __future__ import annotations

import time

import numpy as np
import pymupdf
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage

#: hairlines, their widths in points, and where they start down the page
WIDTHS = (0.0, 0.1, 0.25, 0.5)
TOP, PITCH, ACROSS = 40.0, 13.37, (40.0, 560.0)
#: the darkest a hairline's darkest row may be, zoomed out: near black (the
#: smoothed hairline that fell between two rows was 118, a mid grey)
DARK = 40


def _sheet(path=None) -> pymupdf.Document:
    document = pymupdf.open()
    page = document.new_page(width=600, height=800)
    shape = page.new_shape()
    for group, width in enumerate(WIDTHS):
        for k in range(12):
            y = TOP + (group * 12 + k) * PITCH
            shape.draw_line((ACROSS[0], y), (ACROSS[1], y))
            shape.finish(color=(0, 0, 0), width=width)
    # a hairline at a shallow slope, and a red one
    shape.draw_line((40, 700), (560, 730))
    shape.finish(color=(0, 0, 0), width=0.1)
    shape.draw_line((40, 760), (560, 760.4))
    shape.finish(color=(0.9, 0, 0), width=0.25)
    # hatching
    for k in range(30):
        shape.draw_line((300 + k * 6, 690), (330 + k * 6, 650))
        shape.finish(color=(0, 0, 0), width=0.13)
    shape.commit()
    page.insert_text((40, 790), "GENERAL ARRANGEMENT  SECTION A-A", fontsize=16, fontname="helv")
    if path is not None:
        document.save(path)
    return document


def _luminance(raster) -> np.ndarray:
    pixels = np.frombuffer(raster.samples, np.uint8)
    pixels = pixels.reshape(raster.height, raster.stride)[:, :raster.width * 3]
    return pixels.reshape(raster.height, raster.width, 3).astype(int)


def _render(scale: float) -> np.ndarray:
    from calcforge.pdf import engine

    document = _sheet()
    drawing = engine.display_list(document, 0)
    raster = engine.raster_from(drawing, (0.0, 0.0, 600.0, 800.0), scale)
    document.close()
    return _luminance(raster)


def _hairlines(rgb: np.ndarray, scale: float):
    """For each horizontal hairline: its darkest row's mean, and how many rows
    are dark (below 128) in the middle of it."""
    grey = rgb.mean(axis=2)
    left, right = int(ACROSS[0] * scale) + 2, int(ACROSS[1] * scale) - 2
    for index in range(len(WIDTHS) * 12):
        y = (TOP + index * PITCH) * scale
        band = grey[int(y) - 2:int(y) + 3, left:right]
        rows = band.mean(axis=1)
        yield float(rows.min()), int((rows < 128).sum())


@pytest.mark.parametrize("scale", [0.25, 0.37, 0.5, 0.75])
def test_a_zoomed_out_hairline_is_one_dark_pixel_wherever_it_falls(scale):
    for darkest, rows in _hairlines(_render(scale), scale):
        assert darkest <= DARK, f"a hairline came out grey ({darkest:.0f}) at {scale}"
        assert rows == 1, f"a hairline came out {rows} pixels wide at {scale}"


@pytest.mark.parametrize("scale", [0.25, 0.5])
def test_a_sloping_hairline_is_unbroken_and_a_red_one_stays_red(scale):
    rgb = _render(scale)
    grey = rgb.mean(axis=2)
    for x in range(int(45 * scale), int(555 * scale)):
        y = (700 + 30 * (x / scale - 40) / 520) * scale
        column = grey[int(y) - 2:int(y) + 3, x]
        assert column.min() <= DARK, f"a gap in a sloping hairline at x={x}"
    red = rgb[int(760 * scale) - 2:int(760 * scale) + 3, int(50 * scale):int(550 * scale)]
    reddest = red[np.argmin(red[:, :, 1].mean(axis=1))]
    assert reddest[:, 0].mean() > 200 and reddest[:, 1].mean() < 40, "the red line went pink"


def test_from_a_hundred_per_cent_up_line_work_is_smoothed_as_before():
    scale = 2.0
    grey = _render(scale).mean(axis=2)
    slope = grey[int(700 * scale):int(732 * scale), int(60 * scale):int(540 * scale)]
    between = ((slope > 40) & (slope < 215)).sum()
    assert between > 200, "a sloping line at 200 % is smoothed"


@pytest.mark.parametrize("scale", [0.25, 0.5])
def test_words_stay_smoothed_zoomed_out(scale):
    grey = _render(scale).mean(axis=2)
    words = grey[int(774 * scale):int(794 * scale), int(40 * scale):int(330 * scale)]
    assert ((words > 40) & (words < 215)).sum() > 0.3 * (words < 215).sum()


def test_the_rule_is_for_the_screen_only():
    """Drawing a zoomed-out square leaves MuPDF smoothing as it was, for a
    print or an export drawn in the same process."""
    from pymupdf import mupdf

    before = mupdf.fz_graphics_aa_level()
    _render(0.25)
    assert mupdf.fz_graphics_aa_level() == before == 8


def test_the_window_shows_crisp_hairlines_zoomed_out(window, qapp, tmp_path):
    """The same, through the window: drawn by the render processes, shown at
    50 %."""
    from calcforge.io import pdftiles

    path = str(tmp_path / "sheet.pdf")
    _sheet(path).close()
    window.show()
    window.open_from_command_line(path)
    view = window.view
    view.set_zoom(0.5)
    frame = view.scene().frames[0]
    view.centerOn(frame.mapToScene(QPointF(300, 400)))
    deadline = time.monotonic() + 30
    quiet = 0
    while time.monotonic() < deadline and quiet < 20:
        qapp.processEvents()
        waiting = [key for key in pdftiles.TILES._waiting if not getattr(key, "preview", False)]
        quiet = 0 if waiting or pdftiles.TILES.held() else quiet + 1
        time.sleep(0.01)
    image = view.viewport().grab().toImage().convertToFormat(QImage.Format_RGB32)
    raw = np.frombuffer(bytes(image.constBits()), np.uint8)
    grey = raw.reshape(image.height(), image.bytesPerLine())[:, :image.width() * 4] \
        .reshape(image.height(), image.width(), 4)[:, :, :3].mean(axis=2)
    ratio = view.viewport().devicePixelRatioF()
    for index in range(len(WIDTHS) * 12):
        at = view.mapFromScene(frame.mapToScene(QPointF(300, TOP + index * PITCH)))
        y, x = int(at.y() * ratio), int(at.x() * ratio)
        rows = grey[y - 3:y + 4, x - 100:x + 100].mean(axis=1)
        assert rows.min() <= DARK, f"hairline {index} is grey ({rows.min():.0f}) on screen"
