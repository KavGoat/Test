"""Zoomed out, a drawing's line work — and a markup's — is clear and dark
with smooth edges, as Bluebeam's (the user, 2026-10-20: "Fuzzy is not good
enough ... Bluebeam looks better in zoomed out mode and more legible"; and
2026-10-21: "Fuzzy is better but too contrasty when zoomed out, think you did
too much. That should also apply to markups though").

Smoothed at a pixel wide, a hairline half way between two rows of pixels came
out as two rows of mid grey (118), one on a row as black: the same sheet's
lines were black or pale by where they fell. Drawn onto the pixels instead,
every line was one hard black row: stair-stepped on a slope, hatching in
moiré. Now, below 100 %, no line is thinner than a pixel and a bit
(pdf/engine.ZOOMED_OUT_LINE_PIXELS), still smoothed: wherever a hairline
falls its darkest row is three-quarters dark or more and its edges are soft.
Markups drawn on screen keep to the same width, so a markup's hairline looks
like the drawing's. Words, 100 % and up, prints and exports are as before.

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
#: zoomed out, a hairline's darkest row is at least this dark wherever it
#: falls (smoothed at one pixel it was 118 between two rows), and its ink —
#: how many pixels' worth of black across it, a neighbour's edge included at
#: 25 % — within INK
DARK = 80
INK = (1.2, 2.7)
#: a markup's widths (a width of none is no line at all)
MARKUP_WIDTHS = (0.1, 0.25, 0.5)
#: a grey between paper and black: smoothing


def _soft(values) -> bool:
    return bool(((values > 40) & (values < 215)).any())


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
    """For each horizontal hairline: its darkest row's mean, how many pixels
    of black its rows hold between them, and its rows' means."""
    grey = rgb.mean(axis=2)
    left, right = int(ACROSS[0] * scale) + 2, int(ACROSS[1] * scale) - 2
    for index in range(len(WIDTHS) * 12):
        y = (TOP + index * PITCH) * scale
        rows = grey[int(y) - 2:int(y) + 3, left:right].mean(axis=1)
        yield float(rows.min()), float(((255 - rows) / 255).sum()), rows


@pytest.mark.parametrize("scale", [0.25, 0.37, 0.5, 0.75])
def test_a_zoomed_out_hairline_is_dark_wherever_it_falls_with_soft_edges(scale):
    found = list(_hairlines(_render(scale), scale))
    for darkest, ink, _rows in found:
        assert darkest <= DARK, f"a hairline came out grey ({darkest:.0f}) at {scale}"
        assert INK[0] <= ink <= INK[1], f"a hairline held {ink:.2f} pixels of ink at {scale}"
    # not one hard row each: the edges are smoothed
    softened = sum(1 for _darkest, _ink, rows in found if _soft(rows))
    assert softened >= len(found) // 2, f"only {softened} hairlines smoothed at {scale}"


@pytest.mark.parametrize("scale", [0.25, 0.5])
def test_a_sloping_hairline_is_unbroken_and_smooth_and_a_red_one_stays_red(scale):
    rgb = _render(scale)
    grey = rgb.mean(axis=2)
    along = []
    for x in range(int(45 * scale), int(555 * scale)):
        y = (700 + 30 * (x / scale - 40) / 520) * scale
        column = grey[int(y) - 2:int(y) + 3, x]
        assert column.min() <= DARK + 20, f"a gap in a sloping hairline at x={x}"
        along.append(column)
    assert _soft(np.concatenate(along)), "the sloping hairline is stair-stepped, not smoothed"
    red = rgb[int(760 * scale) - 2:int(760 * scale) + 3, int(50 * scale):int(550 * scale)]
    reddest = red[np.argmin(red[:, :, 1].mean(axis=1))]
    assert reddest[:, 0].mean() > 200 and reddest[:, 1].mean() < 90, "the red line went pink"


def test_from_a_hundred_per_cent_up_line_work_is_as_before():
    from calcforge.pdf import engine

    assert engine.thinnest_line(1.0) == engine.thinnest_line(2.0) == engine.MIN_LINE_PIXELS
    assert engine.thinnest_line(0.99) == engine.ZOOMED_OUT_LINE_PIXELS
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
    """Drawing a zoomed-out square leaves MuPDF as it was, for a print or an
    export drawn in the same process."""
    from pymupdf import mupdf

    from calcforge.pdf import engine

    width, level = mupdf.fz_graphics_min_line_width(), mupdf.fz_graphics_aa_level()
    _render(0.25)
    assert mupdf.fz_graphics_min_line_width() == width == engine.MIN_LINE_PIXELS
    assert mupdf.fz_graphics_aa_level() == level == 8


def _pump(qapp, seconds: float, view=None) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        qapp.processEvents()
        if view is not None:
            view.viewport().grab()
        time.sleep(0.01)


def _side_by_side(window, qapp, tmp_path, zoom: float):
    """Hairlines of the drawing on the left and markup lines of the same
    weights at the same heights on the right, shown at *zoom*: for each, the
    darkest row and ink of the drawing's line and of the markup's."""
    from calcforge.io import pdftiles
    from calcforge.items.shapes import PolyItem

    heights = [TOP + k * PITCH for k in range(len(MARKUP_WIDTHS) * 10)]
    weights = [MARKUP_WIDTHS[k % len(MARKUP_WIDTHS)] for k in range(len(heights))]
    document = pymupdf.open()
    page = document.new_page(width=600, height=800)
    for y, width in zip(heights, weights):
        page.draw_line((40, y), (280, y), width=width, color=(0, 0, 0))
    path = str(tmp_path / "side.pdf")
    document.save(path)
    document.close()
    window.show()
    window.open_from_command_line(path)
    view = window.view
    frame = view.scene().frames[0]
    for y, width in zip(heights, weights):
        line = PolyItem("line", [QPointF(0, 0), QPointF(240, 0)])
        line.style.stroke = "#000000"
        line.style.width = width
        frame.add_markup(line, QPointF(320, y))
    _pump(qapp, 0.5)
    view.set_zoom(zoom)
    view.centerOn(frame.mapToScene(QPointF(300, 250)))
    deadline = time.monotonic() + 30
    quiet = 0
    while time.monotonic() < deadline and quiet < 30:
        qapp.processEvents()
        view.viewport().grab()
        waiting = [key for key in pdftiles.TILES._waiting if not getattr(key, "preview", False)]
        busy = waiting or pdftiles.TILES.held() or frame.layer.hot or frame.layer.pending
        quiet = 0 if busy else quiet + 1
        time.sleep(0.01)
    assert abs(view.zoom() - zoom) < 1e-9
    image = view.viewport().grab().toImage().convertToFormat(QImage.Format_RGB32)
    raw = np.frombuffer(bytes(image.constBits()), np.uint8)
    grey = raw.reshape(image.height(), image.bytesPerLine())[:, :image.width() * 4] \
        .reshape(image.height(), image.width(), 4)[:, :, :3].mean(axis=2)
    ratio = view.viewport().devicePixelRatioF()
    found = []
    for y in heights:
        pair = []
        for x in (160, 440):
            at = view.mapFromScene(frame.mapToScene(QPointF(x, y)))
            down, across = int(at.y() * ratio), int(at.x() * ratio)
            assert 4 <= down < grey.shape[0] - 4
            rows = grey[down - 3:down + 4, across - 30:across + 30].mean(axis=1)
            pair.append((float(rows.min()), float(((255 - rows) / 255).sum())))
        found.append(pair)
    return found


@pytest.mark.parametrize("zoom", [0.37, 0.5])
def test_on_screen_a_markup_hairline_is_as_clear_as_the_drawings(window, qapp, tmp_path, zoom):
    """Through the window — the drawing by the render processes, the markups
    from the page's squares — a markup's hairline and the drawing's of the
    same weight are the same dark, smooth line."""
    found = _side_by_side(window, qapp, tmp_path, zoom)
    drawing = [pdf for pdf, _markup in found]
    markups = [markup for _pdf, markup in found]
    for (darkest, ink), kind in [(d, "drawing") for d in drawing] + [(m, "markup") for m in markups]:
        assert darkest <= DARK + 10, f"a {kind} hairline is grey ({darkest:.0f}) on screen"
        assert INK[0] <= ink <= INK[1], f"a {kind} hairline holds {ink:.2f} pixels of ink"
    assert abs(np.mean([d for d, _ in drawing]) - np.mean([d for d, _ in markups])) <= 12
    assert abs(np.mean([i for _, i in drawing]) - np.mean([i for _, i in markups])) <= 0.15


def test_at_a_hundred_per_cent_markup_lines_are_as_before(window, qapp, tmp_path):
    """From 100 % up a markup's hairline is drawn at its own width, as
    before: a quarter-point line is a faint quarter of a pixel."""
    found = _side_by_side(window, qapp, tmp_path, 1.0)
    for (pdf, markup), width in zip(found, [MARKUP_WIDTHS[k % len(MARKUP_WIDTHS)]
                                            for k in range(len(found))]):
        if width == 0.25:
            assert 0.05 < markup[1] < 0.5, "a quarter-point markup line widened at 100 %"


def test_a_markup_pen_off_screen_is_its_own_width():
    """Asked for outside painting on screen — a print, an export, its size —
    a markup's pen is its own width."""
    from calcforge.items.base import Style

    style = Style(stroke="#000000", width=0.25)
    assert style.pen().widthF() == pytest.approx(0.25)
