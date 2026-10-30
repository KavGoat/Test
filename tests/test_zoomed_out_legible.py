"""Zoomed out, the drawing's line work is clear with smooth edges and the
markups on it are sharp, as in Bluebeam (the user, 2026-10-20: "Fuzzy is not
good enough ... Bluebeam looks better in zoomed out mode and more legible";
2026-10-21: "too contrasty ... think you did too much", "maybe markups don't
fuzzy at all?"; 2026-10-22: "Markup still fuzzy, only PDF lines should be
fuzzy; the min line width should reduce based on how much it's zoomed out";
2026-10-30: "revert the pdf line work to what it was, only make the markups
always sharp and this includes markups from other editors").

The drawing (pdf/engine.thinnest_line): below 100 % no line thinner than
1.4 device pixels just below 100 %, easing by the same step for each halving
of the zoom to one pixel at 25 % and below, still smoothed — dark and soft
where there is room, and a dense sheet far out does not fill in.

Somebody else's markups — the file's own annotations, drawn on their own
(pdf/engine.sharp_at) — are drawn on the pixels below 100 %: every line at
least a pixel and a hair, nothing smoothed into grey; their words keep their
smoothing.

Markups (ui/markuplayer.drawn_sharp): below 100 % every stroke — lines,
rectangles, slants, clouds, ellipses, arrows, freehand — is drawn without
smoothing, a whole number of device pixels wide, one at least: solid ink on
whole pixels, nothing part-covered, unbroken along a curve. Words, fills and
hatches, 100 % and up, prints and exports are as before.

On synthetic sheets only.
"""
from __future__ import annotations

import time

import numpy as np
import pymupdf
import pytest
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QImage, QPolygonF

#: the drawing's hairlines: their widths in points, where they start down
#: the page and how far apart (three pixels apart at 12 %)
WIDTHS = (0.0, 0.1, 0.25)
TOP, PITCH, ACROSS = 40.0, 26.74, (40.0, 560.0)
LINES = 6 * len(WIDTHS)
#: MuPDF's smoothing is in steps: a hairline's ink, in pixels across, comes
#: within this of the width it is drawn at
INK_SLACK = 0.12
#: a markup's widths (a width of none is no line at all)
MARKUP_WIDTHS = (0.1, 0.25, 0.5)
#: where the markup lines down the page start, across it
DOWN = 40.0
#: paper and ink: a markup drawn sharp has nothing in between
PAPER, INK = 250, 5


def _soft(values) -> bool:
    """A grey between paper and black: smoothing."""
    return bool(((values > 40) & (values < 215)).any())


def _sheet(path=None) -> pymupdf.Document:
    document = pymupdf.open()
    page = document.new_page(width=600, height=800)
    shape = page.new_shape()
    for index in range(LINES):
        y = TOP + index * PITCH
        shape.draw_line((ACROSS[0], y), (ACROSS[1], y))
        shape.finish(color=(0, 0, 0), width=WIDTHS[index % len(WIDTHS)])
    # a hairline at a shallow slope, and a red one
    shape.draw_line((40, 700), (560, 730))
    shape.finish(color=(0, 0, 0), width=0.1)
    shape.draw_line((40, 760), (560, 760.4))
    shape.finish(color=(0.9, 0, 0), width=0.25)
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
    """For each horizontal hairline: its rows' means across the line, and
    how many pixels of black they hold between them."""
    grey = rgb.mean(axis=2)
    left, right = int(ACROSS[0] * scale) + 2, int(ACROSS[1] * scale) - 2
    for index in range(LINES):
        y = (TOP + index * PITCH) * scale
        rows = grey[int(y) - 1:int(y) + 2, left:right].mean(axis=1)
        yield rows, float(((255 - rows) / 255).sum())


# ---------------------------------------------------------------------------
# the drawing
# ---------------------------------------------------------------------------

def test_the_drawings_thinnest_line_eases_down_with_the_zoom():
    from calcforge.pdf import engine

    curve = {scale: engine.thinnest_line(scale) for scale in
             (2.0, 1.0, 0.99, 0.75, 0.5, 0.37, 0.25, 0.12, 0.05)}
    assert curve[2.0] == curve[1.0] == engine.MIN_LINE_PIXELS
    assert curve[0.99] == pytest.approx(engine.ZOOMED_OUT_LINE_PIXELS, abs=0.01)
    assert curve[0.75] == pytest.approx(1.32, abs=0.01)
    assert curve[0.5] == pytest.approx(1.2, abs=0.01)
    assert curve[0.37] == pytest.approx(1.11, abs=0.01)
    assert curve[0.25] == curve[0.12] == curve[0.05] == engine.MIN_LINE_PIXELS
    widths = [curve[s] for s in (0.99, 0.75, 0.5, 0.37, 0.25)]
    assert widths == sorted(widths, reverse=True), "never wider further out"


@pytest.mark.parametrize("scale", [0.75, 0.5, 0.37, 0.25, 0.12])
def test_a_zoomed_out_hairline_is_as_wide_as_the_curve_says_with_soft_edges(scale):
    from calcforge.pdf import engine

    wanted = engine.thinnest_line(scale)
    found = list(_hairlines(_render(scale), scale))
    for rows, ink in found:
        assert abs(ink - wanted) <= INK_SLACK, \
            f"a hairline held {ink:.2f} pixels of ink at {scale}, not {wanted:.2f}"
    softened = sum(1 for rows, _ink in found if _soft(rows))
    assert softened >= len(found) // 2, f"only {softened} hairlines smoothed at {scale}"


@pytest.mark.parametrize("scale", [0.25, 0.5])
def test_a_sloping_hairline_is_unbroken_and_smooth_and_a_red_one_stays_red(scale):
    rgb = _render(scale)
    grey = rgb.mean(axis=2)
    along = []
    for x in range(int(45 * scale), int(555 * scale)):
        y = (700 + 30 * (x / scale - 40) / 520) * scale
        column = grey[int(y) - 2:int(y) + 3, x]
        assert column.min() <= 140, f"a gap in a sloping hairline at x={x}"
        along.append(column)
    assert _soft(np.concatenate(along)), "the sloping hairline is stair-stepped, not smoothed"
    red = rgb[int(760 * scale) - 2:int(760 * scale) + 3, int(50 * scale):int(550 * scale)]
    reddest = red[np.argmin(red[:, :, 1].mean(axis=1))]
    assert reddest[:, 0].mean() > 200 and reddest[:, 1].mean() < 140, "the red line went pale"


def test_from_a_hundred_per_cent_up_line_work_is_as_before():
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


def _annotated_sheet() -> pymupdf.Document:
    """A sheet with somebody else's markups: hairline Line annotations across
    the page, one sloping, and a FreeText with words."""
    document = pymupdf.open()
    page = document.new_page(width=600, height=800)
    for index in range(LINES):
        y = TOP + index * PITCH
        line = page.add_line_annot((ACROSS[0], y), (ACROSS[1], y))
        line.set_border(width=WIDTHS[index % len(WIDTHS)])
        line.set_colors(stroke=(0, 0, 0))
        line.update()
    slope = page.add_line_annot((40, 700), (560, 730))
    slope.set_border(width=0.1)
    slope.set_colors(stroke=(0, 0, 0))
    slope.update()
    note = page.add_freetext_annot(pymupdf.Rect(40, 770, 400, 796),
                                   "GENERAL ARRANGEMENT  SECTION A-A", fontsize=16)
    note.update()
    return document


def _render_annotations(scale: float) -> np.ndarray:
    """Every annotation of the sheet drawn on its own, as the renderer draws
    them (io/pdfrender.render_annotation), laid over white."""
    from calcforge.pdf import engine

    document = _annotated_sheet()
    xrefs = [annotation.xref for annotation in document[0].annots()]
    engine.without_page_content(document, 0)
    canvas = np.full((int(800 * scale), int(600 * scale), 3), 255.0)
    for xref in xrefs:
        drawing = engine.annotation_display_list(document, 0, xref)
        assert drawing is not None
        raster = engine.raster_from(drawing, (0.0, 0.0, 600.0, 800.0), scale, alpha=True)
        pixels = np.frombuffer(raster.samples, np.uint8)
        pixels = pixels.reshape(raster.height, raster.stride)[:, :raster.width * 4]
        pixels = pixels.reshape(raster.height, raster.width, 4).astype(float)
        alpha = pixels[:, :, 3:4] / 255.0
        h, w = min(canvas.shape[0], raster.height), min(canvas.shape[1], raster.width)
        canvas[:h, :w] = canvas[:h, :w] * (1 - alpha[:h, :w]) + pixels[:h, :w, :3] * alpha[:h, :w]
    document.close()
    return canvas


@pytest.mark.parametrize("scale", [0.75, 0.5, 0.37, 0.25, 0.12])
def test_somebody_elses_hairline_markup_is_whole_pixels_of_black_zoomed_out(scale):
    from calcforge.pdf import engine

    assert engine.sharp_at(scale, True) and not engine.sharp_at(scale, False)
    found = list(_hairlines(_render_annotations(scale), scale))
    for rows, ink in found:
        assert not _soft(rows), f"a markup hairline smoothed at {scale}: {rows.round()}"
        assert 1 - 1e-6 <= ink <= 2 + 1e-6, f"a markup hairline held {ink:.2f} rows at {scale}"
    single = sum(1 for _rows, ink in found if ink < 1.5)
    assert single >= len(found) * 3 // 4, f"only {single} of {len(found)} hairlines one row at {scale}"


@pytest.mark.parametrize("scale", [0.75, 0.5, 0.25, 0.15])
def test_somebody_elses_sloping_hairline_is_unbroken_zoomed_out(scale):
    grey = _render_annotations(scale).mean(axis=2)
    for x in range(int(45 * scale), int(555 * scale)):
        y = (700 + 30 * (x / scale - 40) / 520) * scale
        assert grey[int(y) - 2:int(y) + 3, x].min() <= 140, f"a gap in a sloping hairline at x={x}"


@pytest.mark.parametrize("scale", [0.25, 0.5])
def test_somebody_elses_words_stay_smoothed_zoomed_out(scale):
    grey = _render_annotations(scale).mean(axis=2)
    words = grey[int(770 * scale):int(796 * scale), int(40 * scale):int(400 * scale)]
    assert ((words > 40) & (words < 215)).sum() > 0.3 * max((words < 215).sum(), 1)


def test_from_a_hundred_per_cent_up_somebody_elses_markups_are_as_before():
    from calcforge.pdf import engine

    assert not engine.sharp_at(1.0, True) and not engine.sharp_at(2.0, True)
    grey = _render_annotations(2.0).mean(axis=2)
    slope = grey[int(700 * 2):int(732 * 2), int(60 * 2):int(540 * 2)]
    assert ((slope > 40) & (slope < 215)).sum() > 200, "a sloping markup at 200 % is smoothed"


def test_the_rule_is_for_the_screen_only():
    """Drawing a zoomed-out square leaves MuPDF as it was, for a print or an
    export drawn in the same process."""
    from pymupdf import mupdf

    from calcforge.pdf import engine

    width, level = mupdf.fz_graphics_min_line_width(), mupdf.fz_graphics_aa_level()
    _render(0.5)
    assert mupdf.fz_graphics_min_line_width() == width == engine.MIN_LINE_PIXELS
    assert mupdf.fz_graphics_aa_level() == level == 8


# ---------------------------------------------------------------------------
# markups
# ---------------------------------------------------------------------------

def _pump(qapp, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.01)


def _markups_beside_the_drawing(window, qapp, tmp_path, zoom: float):
    """The drawing's hairlines on the left; on the right and below, black
    markups: lines across and down the page at sub-pixel places, a
    rectangle, a sloping line, a cloud, an ellipse, a polyline with a
    slanting leg, an arrow and a freehand stroke; shown at *zoom*. The
    window's pixels (grey), where things are on them (at) and the markups."""
    from calcforge.io import pdftiles
    from calcforge.items.shapes import PolyItem, RectItem

    heights = [TOP + k * PITCH for k in range(len(MARKUP_WIDTHS) * 4)]
    weights = [MARKUP_WIDTHS[k % len(MARKUP_WIDTHS)] for k in range(len(heights))]
    document = pymupdf.open()
    page = document.new_page(width=600, height=1000)
    for y, width in zip(heights, weights):
        page.draw_line((40, y), (280, y), width=width, color=(0, 0, 0))
    path = str(tmp_path / "side.pdf")
    document.save(path)
    document.close()
    window.show()
    window.open_from_command_line(path)
    view = window.view
    frame = view.scene().frames[0]
    made = {}

    def black(name, item, width):
        item.style.stroke = "#000000"
        item.style.width = width
        item.style.fill = ""
        frame.add_markup(item, item.pos())
        made[name] = item
        return item

    for k, (y, width) in enumerate(zip(heights, weights)):
        black(f"across{k}", PolyItem("line", [QPointF(320, y), QPointF(560, y)]), width)
    for k, width in enumerate(weights):
        black(f"down{k}", PolyItem("line", [QPointF(DOWN + k * PITCH / 2, 400),
                                            QPointF(DOWN + k * PITCH / 2, 520)]), width)
    black("rect", RectItem("rect", QRectF(400.3, 400.6, 150.2, 90.7)), 0.5)
    black("slope", PolyItem("line", [QPointF(40, 560), QPointF(560, 600)]), 0.25)
    black("cloud", RectItem("cloud", QRectF(330, 640, 200, 110)), 0.5)
    black("ellipse", RectItem("ellipse", QRectF(60, 640, 200, 110)), 0.25)
    black("polyline", PolyItem("polyline", [QPointF(60, 780), QPointF(160, 780),
                                            QPointF(160, 820), QPointF(260, 860)]), 0.5)
    black("arrow", PolyItem("arrow", [QPointF(330, 780), QPointF(520, 850)]), 0.5)
    black("ink", PolyItem("ink", [QPointF(330 + j * 9, 870 + 12 * ((j % 4) - 1.5))
                                  for j in range(20)]), 0.5)
    _pump(qapp, 0.5)
    view.set_zoom(zoom)
    view.centerOn(frame.mapToScene(QPointF(300, 450)))
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

    def at(x, y):
        point = view.mapFromScene(frame.mapToScene(QPointF(x, y)))
        down, across = int(point.y() * ratio), int(point.x() * ratio)
        assert 3 <= down < grey.shape[0] - 3 and 3 <= across < grey.shape[1] - 3
        return down, across

    def around(item):
        box = view.mapFromScene(item.mapToScene(item.boundingRect())).boundingRect()
        return grey[max(int(box.top() * ratio) - 2, 0):int(box.bottom() * ratio) + 3,
                    max(int(box.left() * ratio) - 2, 0):int(box.right() * ratio) + 3]

    return grey, at, around, made, heights, weights


def _one_solid_row(profile) -> bool:
    """One row (or column) of solid ink, paper either side: no soft edge."""
    ink = 255 - np.asarray(profile)
    return int((ink >= 230).sum()) == 1 and int(((ink > 12) & (ink < 230)).sum()) == 0


@pytest.mark.parametrize("zoom", [0.25, 0.5])
def test_zoomed_out_every_markup_stroke_is_sharp(window, qapp, tmp_path, zoom):
    """Through the window — the markups from the page's squares — every
    markup's strokes, slanting, curved and freehand ones too, are solid ink
    on whole pixels: no pixel part-covered, as Revu draws markups zoomed
    out; and a slanting line, an ellipse and a cloud are unbroken."""
    from calcforge.items.base import cloud_path

    grey, at, around, made, _heights, _weights = _markups_beside_the_drawing(
        window, qapp, tmp_path, zoom)
    for name, item in made.items():
        pixels = around(item)
        soft = (pixels > INK) & (pixels < PAPER)
        assert not soft.any(), f"the {name} has {int(soft.sum())} soft pixels at {zoom}"
        assert (pixels <= INK).any(), f"the {name} is not drawn at {zoom}"
    for x in range(60, 540, 3):
        down, across = at(x, 560 + 40 * (x - 40) / 520)
        assert grey[down - 2:down + 3, across].min() <= INK, f"a gap in the slope at {x}"
    for name in ("cloud", "ellipse"):
        item = made[name]
        rect = item.local_rect()
        if name == "cloud":
            outline = cloud_path(QPolygonF([rect.topLeft(), rect.topRight(), rect.bottomRight(),
                                            rect.bottomLeft()]), item.cloud_radius,
                                 inverted=item.cloud_invert)
        else:
            from PySide6.QtGui import QPainterPath
            outline = QPainterPath()
            outline.addEllipse(rect)
        for step in range(240):
            point = item.mapToParent(outline.pointAtPercent(step / 240))
            down, across = at(point.x(), point.y())
            assert grey[down - 1:down + 2, across - 1:across + 2].min() <= INK, \
                f"the {name} is broken at {step / 2.4:.0f} %"


@pytest.mark.parametrize("zoom", [0.25, 0.37, 0.5])
def test_zoomed_out_a_markup_line_is_one_solid_pixel(window, qapp, tmp_path, zoom):
    """A markup's thin line across or down the screen is one solid dark pixel
    wide, wherever it falls; the drawing's hairline beside it stays soft."""
    grey, at, _around, _made, heights, weights = _markups_beside_the_drawing(
        window, qapp, tmp_path, zoom)
    for y in heights:
        down, across = at(440, y)
        rows = grey[down - 1:down + 3, across - 20:across + 20].mean(axis=1)
        assert _one_solid_row(rows), f"a markup line across is soft: {rows.round()}"
    for k in range(len(weights)):
        down, across = at(DOWN + k * PITCH / 2, 460)
        columns = grey[down - 10:down + 10, across - 1:across + 3].mean(axis=0)
        assert _one_solid_row(columns), f"a markup line down is soft: {columns.round()}"
    softened = 0
    for y in heights:
        down, across = at(160, y)
        softened += _soft(grey[down - 1:down + 3, across - 20:across + 20].mean(axis=1))
    assert softened > 0, "the drawing's hairlines went sharp too"


def test_at_a_hundred_per_cent_markup_lines_are_as_before(window, qapp, tmp_path):
    """From 100 % up a markup's hairline is drawn at its own width, smoothed,
    as before: a quarter-point line is a faint quarter of a pixel."""
    grey, at, _around, _made, heights, weights = _markups_beside_the_drawing(
        window, qapp, tmp_path, 1.0)
    checked = 0
    for y, width in zip(heights, weights):
        if width == 0.25 and 200 < y < 330:
            down, across = at(440, y)
            rows = grey[down - 3:down + 4, across - 20:across + 20].mean(axis=1)
            ink = float(((255 - rows) / 255).sum())
            assert 0.05 < ink < 0.5, "a quarter-point markup line widened at 100 %"
            checked += 1
    assert checked


def test_a_markup_pen_off_screen_is_its_own_width():
    """Asked for outside painting on screen — a print, an export, its size —
    a markup's pen is its own width."""
    from calcforge.items.base import Style

    style = Style(stroke="#000000", width=0.25)
    assert style.pen().widthF() == pytest.approx(0.25)
