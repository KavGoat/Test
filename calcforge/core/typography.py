"""Font sizing in pixel units for consistent page rendering.

Page coordinates are PostScript points. A font sized in points would
be four times too large on a 300dpi printer. Pixel sizing pins text
to scene units and lets QPainter's transform handle scaling.
"""
from __future__ import annotations

import sys

from PySide6.QtGui import QFont, QFontMetricsF


def serif_family() -> str:
    if sys.platform == "win32":
        return "Cambria"
    if sys.platform == "darwin":
        return "Times New Roman"
    return "DejaVu Serif"


def sans_family() -> str:
    if sys.platform == "win32":
        return "Segoe UI"
    if sys.platform == "darwin":
        return "Helvetica Neue"
    return "DejaVu Sans"


def make_page_font(family: str = "", size_pt: float = 10.0,
                   bold: bool = False, italic: bool = False) -> QFont:
    if not family or family == "serif":
        family = serif_family()
    elif family == "sans-serif":
        family = sans_family()
    font = QFont(family)
    font.setPixelSize(int(size_pt))
    font.setBold(bold)
    font.setItalic(italic)
    return font


def text_width(text: str, font: QFont) -> float:
    fm = QFontMetricsF(font)
    return fm.horizontalAdvance(text)


def text_height(font: QFont) -> float:
    fm = QFontMetricsF(font)
    return fm.ascent() + fm.descent()


def text_ascent(font: QFont) -> float:
    return QFontMetricsF(font).ascent()


def text_descent(font: QFont) -> float:
    return QFontMetricsF(font).descent()


def line_height(font: QFont) -> float:
    fm = QFontMetricsF(font)
    return fm.height()
