"""Changing the colours in a scanned or imported sheet.

A drawing that came in as a PDF is a picture, so the only way to make its
lines read differently under a markup is to change the pixels. Two things are
worth doing: swapping one colour for another, and pulling everything dark
enough to be a line onto one colour — which is what turns a black-and-white
sheet grey so red markups sit on top of it.
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
    replacement = qRgba(target.red(), target.green(), target.blue(), 255)
    for y in range(out.height()):
        for x in range(out.width()):
            pixel = out.pixel(x, y)
            if qAlpha(pixel) and _distance(pixel, source) <= tolerance:
                out.setPixel(x, y, replacement)
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
