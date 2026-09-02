"""Vector icons drawn at runtime, so the app needs no image assets."""
from __future__ import annotations

import math
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QIcon, QPainter, QPainterPath,
                           QPen, QPixmap, QPolygonF)

# Icons are drawn, not loaded, so they take the colour of whichever theme is
# on. Dark ink on a dark toolbar is an empty toolbar.
INK = "#2c3340"
ACCENT = "#1971c2"
WARM = "#e8590c"

_THEME_INK = {"light": "#2c3340", "dark": "#c7cedb"}
_THEME_ACCENT = {"light": "#1971c2", "dark": "#57a5ec"}
_THEME_WARM = {"light": "#e8590c", "dark": "#f0854a"}

_theme = "light"


def set_icon_theme(theme: str) -> None:
    """Re-tint every icon for *theme*, and forget the ones already drawn."""
    global INK, ACCENT, WARM, _theme
    _theme = "dark" if theme == "dark" else "light"
    INK = _THEME_INK[_theme]
    ACCENT = _THEME_ACCENT[_theme]
    WARM = _THEME_WARM[_theme]
    icon.cache_clear()
    app_icon.cache_clear()


def icon_theme() -> str:
    return _theme


def _pen(painter: QPainter, colour: str, width: float = 1.6,
         style: Qt.PenStyle = Qt.SolidLine) -> QPen:
    pen = QPen(QColor(colour))
    pen.setWidthF(width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    pen.setStyle(style)
    painter.setPen(pen)
    return pen


def _arrow(painter: QPainter, tail: QPointF, tip: QPointF, colour: str) -> None:
    painter.drawLine(tail, tip)
    angle = math.atan2(tip.y() - tail.y(), tip.x() - tail.x())
    size = 5.0
    spread = math.radians(26)
    head = QPolygonF([
        tip,
        tip - QPointF(math.cos(angle - spread) * size, math.sin(angle - spread) * size),
        tip - QPointF(math.cos(angle + spread) * size, math.sin(angle + spread) * size),
    ])
    painter.setBrush(QBrush(QColor(colour)))
    painter.drawPolygon(head)
    painter.setBrush(Qt.NoBrush)


def _glyph(painter: QPainter, text: str, colour: str, size: float = 13.0,
           bold: bool = True, rect: QRectF = None) -> None:
    font = QFont("Segoe UI")
    font.setFamilies(["Segoe UI", "DejaVu Sans", "sans-serif"])
    font.setPointSizeF(size)
    font.setBold(bold)
    painter.setFont(font)
    painter.setPen(QPen(QColor(colour)))
    painter.drawText(rect or QRectF(0, 0, 24, 24), Qt.AlignCenter, text)


def _draw(name: str, painter: QPainter) -> None:  # noqa: C901 - a flat icon table
    if name == "select":
        _pen(painter, INK, 1.5)
        painter.setBrush(QBrush(QColor(INK)))
        painter.drawPolygon(QPolygonF([QPointF(7, 4), QPointF(7, 18), QPointF(10.6, 14.6),
                                       QPointF(13, 19.5), QPointF(15, 18.6),
                                       QPointF(12.7, 13.8), QPointF(17, 13.2)]))
    elif name == "pan":
        _pen(painter, INK, 1.5)
        path = QPainterPath(QPointF(8, 14))
        path.lineTo(8, 8)
        path.lineTo(10, 6)
        path.lineTo(12, 8)
        path.lineTo(14, 7)
        path.lineTo(16, 9)
        path.lineTo(16, 15)
        path.cubicTo(16, 19, 12, 20, 9, 18)
        painter.drawPath(path)
    elif name == "pen":
        _pen(painter, INK, 1.5)
        painter.drawPolyline(QPolygonF([QPointF(5, 18), QPointF(6.5, 13), QPointF(15, 5)]))
        painter.drawLine(QPointF(13.5, 3.5), QPointF(17.5, 7))
        painter.drawLine(QPointF(15, 5), QPointF(17.5, 7))
    elif name == "highlighter":
        painter.fillRect(QRectF(4, 14, 16, 4), QColor("#ffe066"))
        _pen(painter, INK, 1.4)
        painter.drawPolyline(QPolygonF([QPointF(7, 12), QPointF(12, 5), QPointF(16, 8),
                                        QPointF(11, 14)]))
    elif name == "line":
        _pen(painter, INK, 1.6)
        painter.drawLine(QPointF(5, 18), QPointF(19, 6))
    elif name == "arrow":
        _pen(painter, INK, 1.6)
        _arrow(painter, QPointF(5, 18), QPointF(18, 6), INK)
    elif name == "polyline":
        _pen(painter, INK, 1.6)
        painter.drawPolyline(QPolygonF([QPointF(4, 17), QPointF(9, 8), QPointF(14, 14),
                                        QPointF(20, 5)]))
    elif name == "rect":
        _pen(painter, INK, 1.6)
        painter.drawRect(QRectF(5, 7, 14, 10))
    elif name == "ellipse":
        _pen(painter, INK, 1.6)
        painter.drawEllipse(QRectF(4, 7, 16, 10))
    elif name == "polygon":
        _pen(painter, INK, 1.6)
        painter.drawPolygon(QPolygonF([QPointF(12, 4), QPointF(20, 10), QPointF(17, 19),
                                       QPointF(7, 19), QPointF(4, 10)]))
    elif name in ("cloud", "cloud_rect"):
        _pen(painter, INK, 1.3)
        radius = 3.2
        centres = [(7.5, 8), (12, 6.5), (16.5, 8), (18, 12), (16.5, 16), (12, 17.5),
                   (7.5, 16), (6, 12)]
        for index, (cx, cy) in enumerate(centres):
            rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
            start = 90 - index * (360 / len(centres))
            painter.drawArc(rect, int((start - 110) * 16), int(220 * 16))
    elif name == "highlight":
        painter.fillRect(QRectF(4, 8, 16, 8), QColor("#ffe066"))
        _pen(painter, "#b59a00", 1.0)
        painter.drawRect(QRectF(4, 8, 16, 8))
    elif name == "text":
        _glyph(painter, "T", INK, 14)
        _pen(painter, INK, 1.0, Qt.DotLine)
        painter.drawRect(QRectF(4, 5, 16, 14))
    elif name == "callout":
        _pen(painter, INK, 1.4)
        painter.drawRoundedRect(QRectF(8, 4, 12, 9), 2, 2)
        _arrow(painter, QPointF(9, 12), QPointF(4, 19), INK)
    elif name == "note":
        _pen(painter, "#b8860b", 1.2)
        painter.setBrush(QBrush(QColor("#ffe066")))
        painter.drawRoundedRect(QRectF(5, 5, 14, 14), 2, 2)
        _pen(painter, "#8a6d0b", 1.0)
        for offset in range(3):
            painter.drawLine(QPointF(8, 9 + offset * 3), QPointF(16, 9 + offset * 3))
    elif name == "stamp":
        _pen(painter, WARM, 1.6)
        painter.drawRoundedRect(QRectF(3, 8, 18, 9), 2, 2)
        _glyph(painter, "OK", WARM, 6.5, True, QRectF(3, 8, 18, 9))
    elif name == "image":
        _pen(painter, INK, 1.4)
        painter.drawRect(QRectF(4, 6, 16, 12))
        painter.setBrush(QBrush(QColor(INK)))
        painter.drawEllipse(QPointF(8.5, 10), 1.4, 1.4)
        painter.setBrush(Qt.NoBrush)
        painter.drawPolyline(QPolygonF([QPointF(5, 17), QPointF(10, 12), QPointF(13, 15),
                                        QPointF(16, 11), QPointF(19, 17)]))
    elif name == "math":
        _pen(painter, ACCENT, 1.5)
        painter.drawLine(QPointF(5, 12), QPointF(13, 12))
        _glyph(painter, "x", ACCENT, 8, True, QRectF(4, 3, 10, 9))
        _glyph(painter, "y", ACCENT, 8, True, QRectF(4, 12, 10, 9))
        _glyph(painter, "=", ACCENT, 9, True, QRectF(13, 6, 10, 12))
    elif name == "plot":
        _pen(painter, INK, 1.2)
        painter.drawLine(QPointF(5, 4), QPointF(5, 19))
        painter.drawLine(QPointF(5, 19), QPointF(20, 19))
        _pen(painter, ACCENT, 1.6)
        path = QPainterPath(QPointF(6, 16))
        path.cubicTo(QPointF(10, 4), QPointF(15, 4), QPointF(19, 13))
        painter.drawPath(path)
        _pen(painter, WARM, 1.3)
        path2 = QPainterPath(QPointF(6, 18))
        path2.cubicTo(QPointF(11, 11), QPointF(15, 11), QPointF(19, 16))
        painter.drawPath(path2)
    elif name == "table":
        _pen(painter, INK, 1.3)
        painter.drawRect(QRectF(4, 6, 16, 12))
        painter.drawLine(QPointF(4, 10), QPointF(20, 10))
        painter.drawLine(QPointF(4, 14), QPointF(20, 14))
        painter.drawLine(QPointF(9.3, 6), QPointF(9.3, 18))
        painter.drawLine(QPointF(14.6, 6), QPointF(14.6, 18))
    elif name == "measure_length":
        _pen(painter, ACCENT, 1.5)
        _arrow(painter, QPointF(6, 16), QPointF(18, 8), ACCENT)
        _arrow(painter, QPointF(18, 8), QPointF(6, 16), ACCENT)
    elif name == "measure_area":
        _pen(painter, ACCENT, 1.4)
        painter.setBrush(QBrush(QColor(25, 113, 194, 55)))
        painter.drawPolygon(QPolygonF([QPointF(4, 15), QPointF(9, 5), QPointF(19, 8),
                                       QPointF(17, 18)]))
    elif name == "measure_angle":
        _pen(painter, ACCENT, 1.5)
        painter.drawLine(QPointF(5, 18), QPointF(19, 18))
        painter.drawLine(QPointF(5, 18), QPointF(16, 6))
        painter.drawArc(QRectF(-1, 12, 12, 12), 0, 45 * 16)
    elif name == "measure_radius":
        _pen(painter, ACCENT, 1.4)
        painter.drawEllipse(QRectF(4, 4, 16, 16))
        _arrow(painter, QPointF(12, 12), QPointF(19, 8), ACCENT)
    elif name == "count":
        _pen(painter, "#c2255c", 1.5)
        painter.drawEllipse(QRectF(5, 5, 11, 11))
        _glyph(painter, "3", "#c2255c", 8, True, QRectF(12, 10, 11, 11))
    elif name == "calibrate":
        _pen(painter, WARM, 1.5)
        painter.drawLine(QPointF(4, 16), QPointF(20, 16))
        for x in (5, 10, 15, 19):
            painter.drawLine(QPointF(x, 16), QPointF(x, 11))
        _glyph(painter, "?", WARM, 9, True, QRectF(6, 2, 12, 10))
    elif name == "page":
        _pen(painter, INK, 1.4)
        painter.drawRect(QRectF(6, 3, 12, 18))
        _pen(painter, "#9aa3ad", 1.0)
        for offset in range(4):
            painter.drawLine(QPointF(8, 7 + offset * 3.2), QPointF(16, 7 + offset * 3.2))
    elif name == "pdf":
        _pen(painter, "#c92a2a", 1.4)
        painter.drawRect(QRectF(5, 3, 14, 18))
        _glyph(painter, "PDF", "#c92a2a", 6, True, QRectF(5, 8, 14, 10))
    elif name == "print":
        _pen(painter, INK, 1.4)
        painter.drawRect(QRectF(4, 9, 16, 7))
        painter.drawRect(QRectF(7, 3, 10, 6))
        painter.drawRect(QRectF(7, 14, 10, 7))
    elif name == "save":
        _pen(painter, INK, 1.4)
        painter.drawRect(QRectF(4, 4, 16, 16))
        painter.drawRect(QRectF(8, 4, 8, 6))
        painter.drawRect(QRectF(7, 13, 10, 7))
    elif name == "open":
        _pen(painter, INK, 1.4)
        painter.drawPolygon(QPolygonF([QPointF(3, 18), QPointF(6, 9), QPointF(21, 9),
                                       QPointF(18, 18)]))
        painter.drawPolyline(QPolygonF([QPointF(3, 18), QPointF(3, 6), QPointF(9, 6),
                                        QPointF(11, 9)]))
    elif name == "new":
        _pen(painter, INK, 1.4)
        painter.drawPolygon(QPolygonF([QPointF(6, 3), QPointF(14, 3), QPointF(18, 7),
                                       QPointF(18, 21), QPointF(6, 21)]))
        painter.drawPolyline(QPolygonF([QPointF(14, 3), QPointF(14, 7), QPointF(18, 7)]))
    elif name == "undo":
        _pen(painter, INK, 1.7)
        painter.drawArc(QRectF(5, 6, 14, 12), 40 * 16, 220 * 16)
        painter.setBrush(QBrush(QColor(INK)))
        painter.drawPolygon(QPolygonF([QPointF(5, 6), QPointF(11, 7), QPointF(6, 12)]))
    elif name == "redo":
        _pen(painter, INK, 1.7)
        painter.drawArc(QRectF(5, 6, 14, 12), 280 * 16, 220 * 16)
        painter.setBrush(QBrush(QColor(INK)))
        painter.drawPolygon(QPolygonF([QPointF(19, 6), QPointF(13, 7), QPointF(18, 12)]))
    elif name == "zoom_in":
        _pen(painter, INK, 1.6)
        painter.drawEllipse(QRectF(4, 4, 12, 12))
        painter.drawLine(QPointF(14.5, 14.5), QPointF(20, 20))
        painter.drawLine(QPointF(7, 10), QPointF(13, 10))
        painter.drawLine(QPointF(10, 7), QPointF(10, 13))
    elif name == "zoom_out":
        _pen(painter, INK, 1.6)
        painter.drawEllipse(QRectF(4, 4, 12, 12))
        painter.drawLine(QPointF(14.5, 14.5), QPointF(20, 20))
        painter.drawLine(QPointF(7, 10), QPointF(13, 10))
    elif name == "fit":
        _pen(painter, INK, 1.5)
        painter.drawRect(QRectF(4, 5, 16, 14))
        painter.drawLine(QPointF(8, 9), QPointF(16, 9))
        painter.drawLine(QPointF(8, 15), QPointF(16, 15))
    elif name == "layers":
        _pen(painter, INK, 1.3)
        for offset in (0, 4, 8):
            painter.drawPolygon(QPolygonF([QPointF(12, 3 + offset), QPointF(20, 7 + offset),
                                           QPointF(12, 11 + offset), QPointF(4, 7 + offset)]))
    elif name == "variables":
        font = QFont("Georgia")
        font.setFamilies(["Cambria Math", "Georgia", "DejaVu Serif", "serif"])
        font.setPointSizeF(14)
        font.setItalic(True)
        painter.setFont(font)
        painter.setPen(QPen(QColor(ACCENT)))
        painter.drawText(QRectF(0, 0, 24, 24), Qt.AlignCenter, "x")
    elif name == "delete":
        _pen(painter, "#c92a2a", 1.5)
        painter.drawLine(QPointF(6, 6), QPointF(18, 18))
        painter.drawLine(QPointF(18, 6), QPointF(6, 18))
    elif name == "pin":
        # A drawing pin: pressed in, the tool stays chosen after each markup.
        _pen(painter, INK, 1.5)
        painter.setBrush(QBrush(QColor(INK)))
        painter.drawPolygon(QPolygonF([QPointF(9, 4), QPointF(15, 4), QPointF(14, 10),
                                       QPointF(17, 13), QPointF(7, 13), QPointF(10, 10)]))
        painter.drawLine(QPointF(12, 13), QPointF(12, 20))
    elif name == "verify":
        _pen(painter, ACCENT, 1.7)
        painter.drawPolyline(QPolygonF([QPointF(5, 12), QPointF(10, 17), QPointF(19, 6)]))
    elif name == "recalc":
        _pen(painter, ACCENT, 1.6)
        painter.drawArc(QRectF(5, 5, 14, 14), 30 * 16, 280 * 16)
        painter.setBrush(QBrush(QColor(ACCENT)))
        painter.drawPolygon(QPolygonF([QPointF(19, 4), QPointF(20, 11), QPointF(14, 9)]))
    else:
        _glyph(painter, name[:2].upper(), INK, 8)


@lru_cache(maxsize=256)
def icon(name: str, size: int = 24) -> QIcon:
    """Return a cached icon; drawn once per name and size."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    painter.scale(size / 24.0, size / 24.0)
    painter.setBrush(Qt.NoBrush)
    _draw(name, painter)
    painter.end()
    return QIcon(pixmap)


@lru_cache(maxsize=64)
def colour_icon(colour: str, size: int = 20) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(QPen(QColor(120, 128, 140), 1))
    painter.setBrush(QBrush(QColor(colour)))
    painter.drawRoundedRect(QRectF(2, 2, size - 4, size - 4), 3, 3)
    painter.end()
    return QIcon(pixmap)


@lru_cache(maxsize=8)
def app_icon(size: int = 256) -> QIcon:
    """The application icon: a sheet with a rule, a curve and a result."""
    icon_object = QIcon()
    for edge in (16, 24, 32, 48, 64, 128, size):
        pixmap = QPixmap(edge, edge)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.scale(edge / 64.0, edge / 64.0)

        body = QRectF(6, 4, 52, 56)
        painter.setPen(QPen(QColor("#2f3a4a"), 2.4))
        painter.setBrush(QBrush(QColor("#fdfefe")))
        painter.drawRoundedRect(body, 6, 6)

        painter.setPen(QPen(QColor("#1971c2"), 3.0, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(14, 24), QPointF(30, 24))     # fraction rule
        painter.setPen(QPen(QColor("#2f3a4a"), 2.6, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(16, 17), QPointF(28, 17))     # numerator
        painter.drawLine(QPointF(17, 32), QPointF(27, 32))     # denominator
        painter.setPen(QPen(QColor("#e8590c"), 3.0, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(36, 24), QPointF(50, 24))     # equals
        painter.drawLine(QPointF(36, 30), QPointF(50, 30))

        curve = QPainterPath(QPointF(13, 52))
        curve.cubicTo(QPointF(24, 38), QPointF(38, 38), QPointF(51, 50))
        painter.setPen(QPen(QColor("#2f9e44"), 3.0, Qt.SolidLine, Qt.RoundCap))
        painter.drawPath(curve)
        painter.end()
        icon_object.addPixmap(pixmap)
    return icon_object
