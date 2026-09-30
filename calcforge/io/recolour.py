"""Changing the colours in a scanned or imported sheet or image.

A drawing that came in as a PDF is a picture, so the only way to make its
lines read differently under a markup is to change the pixels. Two things are
worth doing: swapping one colour for another, and pulling everything dark
enough to be a line onto one colour — which is what turns a black-and-white
sheet grey so red markups sit on top of it. Photos additionally support
greyscale conversion and making one selected colour transparent.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, qAlpha, qBlue, qGreen, qRed, qRgba


def _distance(pixel: int, colour: QColor) -> int:
    """How far a pixel is from a colour, as the largest channel difference."""
    return max(abs(qRed(pixel) - colour.red()),
               abs(qGreen(pixel) - colour.green()),
               abs(qBlue(pixel) - colour.blue()))


def swap_colour(image: QImage, source: QColor, target: QColor,
                tolerance: int = 40) -> QImage:
    """Every pixel near *source* becomes *target*; everything else is left."""
    out = image.convertToFormat(QImage.Format_ARGB32)
    for y in range(out.height()):
        for x in range(out.width()):
            pixel = out.pixel(x, y)
            if qAlpha(pixel) and _distance(pixel, source) <= tolerance:
                out.setPixel(x, y, qRgba(target.red(), target.green(), target.blue(), qAlpha(pixel)))
    return out


def recolour_lines(image: QImage, target: QColor, threshold: int = 128) -> QImage:
    """Pull everything dark enough to be a line onto *target*.

    The darkness of each pixel is kept as its weight, so a thin grey line
    stays lighter than a thick black one and the drawing does not turn into a
    flat stencil.
    """
    out = image.convertToFormat(QImage.Format_ARGB32)
    for y in range(out.height()):
        for x in range(out.width()):
            pixel = out.pixel(x, y)
            if not qAlpha(pixel):
                continue
            luma = (qRed(pixel) * 299 + qGreen(pixel) * 587 + qBlue(pixel) * 114) // 1000
            if luma >= threshold:
                continue
            weight = (threshold - luma) / max(threshold, 1)
            out.setPixel(x, y, qRgba(
                round(255 - (255 - target.red()) * weight),
                round(255 - (255 - target.green()) * weight),
                round(255 - (255 - target.blue()) * weight), 255))
    return out


def to_greyscale(image: QImage) -> QImage:
    """Convert RGB channels to luminance while preserving each pixel's alpha."""
    out = image.convertToFormat(QImage.Format_ARGB32)
    for y in range(out.height()):
        for x in range(out.width()):
            pixel = out.pixel(x, y)
            grey = (qRed(pixel) * 299 + qGreen(pixel) * 587
                    + qBlue(pixel) * 114) // 1000
            out.setPixel(x, y, qRgba(grey, grey, grey, qAlpha(pixel)))
    return out


def make_colour_transparent(image: QImage, source: QColor,
                            tolerance: int = 40) -> QImage:
    """Clear alpha for pixels near *source*, retaining every other pixel."""
    out = image.convertToFormat(QImage.Format_ARGB32)
    for y in range(out.height()):
        for x in range(out.width()):
            pixel = out.pixel(x, y)
            if qAlpha(pixel) and _distance(pixel, source) <= tolerance:
                out.setPixel(x, y, qRgba(qRed(pixel), qGreen(pixel),
                                         qBlue(pixel), 0))
    return out


def colourise(image: QImage, colour: QColor) -> QImage:
    """Tint the whole image one colour, keeping its light and shade.

    Bluebeam's Colorize: the drawing becomes red, or green, or whatever is
    asked for, and stays readable because each pixel keeps how light or dark
    it was. Black and white is the same operation with a grey, which is why
    that is not a separate thing to implement.
    """
    out = image.convertToFormat(QImage.Format_ARGB32)
    red, green, blue = colour.red(), colour.green(), colour.blue()
    for y in range(out.height()):
        for x in range(out.width()):
            pixel = out.pixel(x, y)
            alpha = qAlpha(pixel)
            if not alpha:
                continue
            # How light this pixel is, 0..1, used to scale the tint. White
            # stays white so paper does not turn into a block of colour.
            level = (qRed(pixel) * 299 + qGreen(pixel) * 587
                     + qBlue(pixel) * 114) / 255000.0
            out.setPixel(x, y, qRgba(
                round(red + (255 - red) * level),
                round(green + (255 - green) * level),
                round(blue + (255 - blue) * level), alpha))
    return out


# ---------------------------------------------------------------------------
# The same operations on line work, which is what a PDF page actually holds
# ---------------------------------------------------------------------------

def _near(hex_colour: str, colour: QColor, tolerance: int) -> bool:
    """Whether a stored "#rrggbb" is within *tolerance* of *colour*."""
    if not hex_colour:
        return False
    other = QColor(hex_colour)
    if not other.isValid():
        return False
    return max(abs(other.red() - colour.red()),
               abs(other.green() - colour.green()),
               abs(other.blue() - colour.blue())) <= tolerance


def swap_line_colour(items, source: QColor, target: QColor,
                     tolerance: int = 40) -> int:
    """Change every line near *source* to *target*. Says how many changed.

    A page that came in from a PDF keeps its line work as line work, so
    changing its colours is a change to the lines rather than to a picture of
    them: the drawing stays as sharp as it was and still prints as vectors.
    Repainting only the raster underneath left the lines their old colour on
    top of a recoloured picture, which is the one result nobody wanted.
    """
    name = target.name()
    changed = 0
    for item in items:
        if hasattr(item, "change_colours"):
            changed += item.change_colours(source, target, tolerance)
            continue
        style = getattr(item, "style", None)
        if style is None:
            continue
        for field in ("stroke", "fill"):
            if _near(getattr(style, field, ""), source, tolerance):
                setattr(style, field, name)
                changed += 1
        item.update()
    return changed


def colourise_lines(items, colour: QColor) -> int:
    """Put every line onto *colour*, keeping fills lighter than strokes."""
    name = colour.name()
    lighter = QColor(colour).lighter(150).name()
    changed = 0
    for item in items:
        if hasattr(item, "change_colours"):
            changed += item.change_colours(None, colour)
            continue
        style = getattr(item, "style", None)
        if style is None:
            continue
        if getattr(style, "stroke", ""):
            style.stroke = name
            changed += 1
        if getattr(style, "fill", ""):
            style.fill = lighter
            changed += 1
        item.update()
    return changed


def common_colours(image: QImage, most: int = 8) -> list[QColor]:
    """The colours a sheet is mostly made of, for offering as the one to change."""
    small = image.scaled(160, 160, Qt.KeepAspectRatio)
    counts: dict[int, int] = {}
    for y in range(small.height()):
        for x in range(small.width()):
            pixel = small.pixel(x, y)
            if not qAlpha(pixel):
                continue
            key = (qRed(pixel) & 0xF0) << 16 | (qGreen(pixel) & 0xF0) << 8 | (qBlue(pixel) & 0xF0)
            counts[key] = counts.get(key, 0) + 1
    ordered = sorted(counts.items(), key=lambda pair: -pair[1])[:most]
    return [QColor((key >> 16) & 0xFF, (key >> 8) & 0xFF, key & 0xFF) for key, _ in ordered]
