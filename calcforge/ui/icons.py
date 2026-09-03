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
# The icons that carry a colour of their own — a red PDF, a yellow note, a pink
# count marker. They still have to be legible on a dark toolbar, so each one
# has a lighter twin rather than being drawn in one fixed colour.
DANGER = "#c92a2a"
NOTE = "#ffe066"
NOTE_EDGE = "#b8860b"
NOTE_RULE = "#8a6d0b"
MARKER = "#c2255c"
FAINT = "#9aa3ad"

_THEME_INK = {"light": "#2c3340", "dark": "#c7cedb"}
_THEME_ACCENT = {"light": "#1971c2", "dark": "#57a5ec"}
_THEME_WARM = {"light": "#e8590c", "dark": "#f0854a"}
_THEME_DANGER = {"light": "#c92a2a", "dark": "#ff8787"}
_THEME_NOTE = {"light": "#ffe066", "dark": "#ffd43b"}
_THEME_NOTE_EDGE = {"light": "#b8860b", "dark": "#e8b923"}
_THEME_NOTE_RULE = {"light": "#8a6d0b", "dark": "#8a6d0b"}
_THEME_MARKER = {"light": "#c2255c", "dark": "#f783ac"}
_THEME_FAINT = {"light": "#9aa3ad", "dark": "#79828f"}

_theme = "light"


def set_icon_theme(theme: str) -> None:
    """Re-tint every icon for *theme*, and forget the ones already drawn."""
    global INK, ACCENT, WARM, DANGER, NOTE, NOTE_EDGE, NOTE_RULE, MARKER, FAINT
    global _theme
    _theme = "dark" if theme == "dark" else "light"
    INK = _THEME_INK[_theme]
    ACCENT = _THEME_ACCENT[_theme]
    WARM = _THEME_WARM[_theme]
    DANGER = _THEME_DANGER[_theme]
    NOTE = _THEME_NOTE[_theme]
    NOTE_EDGE = _THEME_NOTE_EDGE[_theme]
    NOTE_RULE = _THEME_NOTE_RULE[_theme]
    MARKER = _THEME_MARKER[_theme]
    FAINT = _THEME_FAINT[_theme]
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


def _cloud(painter: QPainter, colour: str, rect: QRectF) -> None:
    """A revision cloud filling *rect* — scallops all the way round."""
    _pen(painter, colour, 1.3)
    radius = min(rect.width(), rect.height()) / 4.4
    centre = rect.center()
    count = 8
    for index in range(count):
        angle = 2 * math.pi * index / count
        cx = centre.x() + math.cos(angle) * (rect.width() / 2 - radius * 0.85)
        cy = centre.y() + math.sin(angle) * (rect.height() / 2 - radius * 0.85)
        box = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
        start = -math.degrees(angle) - 110
        painter.drawArc(box, int(start * 16), int(220 * 16))


def _ruler(painter: QPainter) -> None:
    """The ruler edge every measuring tool carries along its bottom."""
    _pen(painter, WARM, 1.2)
    painter.drawLine(QPointF(3, 20.5), QPointF(21, 20.5))
    for x in (4.5, 7.5, 10.5, 13.5, 16.5, 19.5):
        painter.drawLine(QPointF(x, 20.5), QPointF(x, 17.5))


def _draw(name: str, painter: QPainter) -> None:  # noqa: C901 - a flat icon table
    if name == "select":
        _pen(painter, INK, 1.5)
        painter.setBrush(QBrush(QColor(INK)))
        painter.drawPolygon(QPolygonF([QPointF(7, 4), QPointF(7, 18), QPointF(10.6, 14.6),
                                       QPointF(13, 19.5), QPointF(15, 18.6),
                                       QPointF(12.7, 13.8), QPointF(17, 13.2)]))
    elif name == "snapshot":
        # A marquee with a copy lifted out of it — the same ink as the rest of
        # the toolbar, so no button stands out in a colour of its own.
        _pen(painter, INK, 1.3, Qt.DashLine)
        painter.drawRect(QRectF(3.5, 4.5, 12, 11))
        _pen(painter, INK, 1.6)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(9.5, 9.5, 11, 10))
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
        # A pen nib, drawing: the same shape Bluebeam gives its Pen.
        _pen(painter, INK, 1.5)
        painter.drawPolyline(QPolygonF([QPointF(4, 20), QPointF(6, 14), QPointF(15.5, 4.5)]))
        painter.drawLine(QPointF(13.5, 3), QPointF(18, 7))
        painter.drawLine(QPointF(15.5, 4.5), QPointF(18, 7))
        painter.drawLine(QPointF(6, 14), QPointF(10, 18))
    elif name == "highlighter":
        # A marker with a broad chisel tip and a band of ink under it.
        _pen(painter, INK, 1.4)
        painter.drawPolyline(QPolygonF([QPointF(7, 13), QPointF(13.5, 4), QPointF(18, 7.5),
                                        QPointF(11.5, 16.5), QPointF(7, 13)]))
        painter.drawLine(QPointF(7, 13), QPointF(5, 16.5))
        painter.drawLine(QPointF(11.5, 16.5), QPointF(9, 19))
        _pen(painter, INK, 2.6)
        painter.drawLine(QPointF(4, 21), QPointF(20, 21))
    elif name == "eraser":
        _pen(painter, INK, 1.4)
        painter.drawPolygon(QPolygonF([QPointF(4, 15), QPointF(12, 5), QPointF(19, 10),
                                       QPointF(11, 20), QPointF(6, 20)]))
        painter.drawLine(QPointF(8.5, 11.5), QPointF(15.5, 16.5))
    elif name == "line":
        _pen(painter, INK, 1.6)
        painter.drawLine(QPointF(4, 19), QPointF(20, 5))
    elif name == "arrow":
        _pen(painter, INK, 1.6)
        _arrow(painter, QPointF(4, 19), QPointF(19, 5), INK)
    elif name == "arc":
        _pen(painter, INK, 1.6)
        path = QPainterPath(QPointF(5, 19))
        path.cubicTo(QPointF(5, 8), QPointF(13, 5), QPointF(19, 6))
        painter.drawPath(path)
    elif name == "polyline":
        _pen(painter, INK, 1.6)
        painter.drawPolyline(QPolygonF([QPointF(4, 17), QPointF(9, 8), QPointF(14, 14),
                                        QPointF(20, 5)]))
    elif name == "rect":
        _pen(painter, INK, 1.6)
        painter.drawRect(QRectF(4.5, 6.5, 15, 11))
    elif name == "ellipse":
        _pen(painter, INK, 1.6)
        painter.drawEllipse(QRectF(3.5, 6, 17, 12))
    elif name == "polygon":
        # An open-cornered polygon, the way Bluebeam draws its Polygon tool.
        _pen(painter, INK, 1.6)
        painter.drawPolygon(QPolygonF([QPointF(4, 6), QPointF(20, 6), QPointF(12, 13),
                                       QPointF(20, 19), QPointF(4, 19)]))
    elif name in ("cloud", "cloud_rect"):
        _cloud(painter, INK, QRectF(4, 5, 16, 14))
    elif name == "cloud_plus":
        # Cloud+ in Bluebeam: a cloud you draw a shape for, corner by corner.
        _cloud(painter, INK, QRectF(3.5, 4.5, 14, 12))
        _pen(painter, INK, 1.4)
        painter.drawLine(QPointF(18, 16), QPointF(18, 22))
        painter.drawLine(QPointF(15, 19), QPointF(21, 19))
    elif name == "highlight":
        # A block highlight over text, not a pen: two ruled lines behind it.
        _pen(painter, FAINT, 1.0)
        painter.drawLine(QPointF(4, 9), QPointF(20, 9))
        painter.drawLine(QPointF(4, 15), QPointF(20, 15))
        _pen(painter, INK, 1.4)
        painter.drawRect(QRectF(4, 7, 16, 10))
    elif name == "redact":
        _pen(painter, INK, 1.2)
        painter.setBrush(QBrush(QColor(INK)))
        painter.drawRect(QRectF(4, 8, 16, 8))
        painter.setBrush(Qt.NoBrush)
    elif name == "text":
        # Bluebeam's Text Box: a capital A in a box.
        _pen(painter, INK, 1.3)
        painter.drawRect(QRectF(3.5, 4.5, 17, 15))
        _glyph(painter, "A", INK, 11, True, QRectF(3.5, 4.5, 17, 15))
    elif name == "typewriter":
        _glyph(painter, "A", INK, 12, False, QRectF(3, 3, 18, 15))
        _pen(painter, INK, 1.3)
        painter.drawLine(QPointF(4, 20), QPointF(20, 20))
    elif name == "callout":
        _pen(painter, INK, 1.4)
        painter.drawRect(QRectF(8.5, 3.5, 12, 9))
        painter.drawPolyline(QPolygonF([QPointF(14.5, 12.5), QPointF(14.5, 16),
                                        QPointF(4.5, 20)]))
        painter.setBrush(QBrush(QColor(INK)))
        painter.drawPolygon(QPolygonF([QPointF(4, 20.5), QPointF(9, 17.5),
                                       QPointF(8.4, 20.5)]))
        painter.setBrush(Qt.NoBrush)
    elif name == "cloud_callout":
        _cloud(painter, INK, QRectF(8, 3, 13, 10))
        _pen(painter, INK, 1.4)
        painter.drawPolyline(QPolygonF([QPointF(14, 13), QPointF(14, 16.5),
                                        QPointF(4.5, 20)]))
        painter.setBrush(QBrush(QColor(INK)))
        painter.drawPolygon(QPolygonF([QPointF(4, 20.5), QPointF(9, 17.5),
                                       QPointF(8.4, 20.5)]))
        painter.setBrush(Qt.NoBrush)
    elif name == "note":
        _pen(painter, NOTE_EDGE, 1.2)
        painter.setBrush(QBrush(QColor(NOTE)))
        painter.drawRoundedRect(QRectF(5, 5, 14, 14), 2, 2)
        _pen(painter, NOTE_RULE, 1.0)
        for offset in range(3):
            painter.drawLine(QPointF(8, 9 + offset * 3), QPointF(16, 9 + offset * 3))
        painter.setBrush(Qt.NoBrush)
    elif name == "stamp":
        _pen(painter, WARM, 1.6)
        painter.drawRoundedRect(QRectF(3, 8, 18, 9), 2, 2)
        _glyph(painter, "OK", WARM, 6.5, True, QRectF(3, 8, 18, 9))
    elif name == "flag":
        _pen(painter, INK, 1.4)
        painter.drawLine(QPointF(6, 3), QPointF(6, 21))
        painter.setBrush(QBrush(QColor(INK)))
        painter.drawPolygon(QPolygonF([QPointF(6, 4), QPointF(19, 7.5), QPointF(6, 11)]))
        painter.setBrush(Qt.NoBrush)
    elif name == "image":
        _pen(painter, INK, 1.4)
        painter.drawRect(QRectF(4, 6, 16, 12))
        painter.setBrush(QBrush(QColor(INK)))
        painter.drawEllipse(QPointF(8.5, 10), 1.4, 1.4)
        painter.setBrush(Qt.NoBrush)
        painter.drawPolyline(QPolygonF([QPointF(5, 17), QPointF(10, 12), QPointF(13, 15),
                                        QPointF(16, 11), QPointF(19, 17)]))
    elif name == "math":
        # One line of working: a fraction and an equals sign.
        _pen(painter, INK, 1.5)
        painter.drawLine(QPointF(4, 12), QPointF(12, 12))
        _glyph(painter, "x", INK, 8, False, QRectF(3, 3, 10, 9))
        _glyph(painter, "y", INK, 8, False, QRectF(3, 12, 10, 9))
        _glyph(painter, "=", INK, 10, False, QRectF(12, 6, 11, 12))
    elif name == "mathblock":
        # A block of working: several lines of it, ruled off.
        _pen(painter, INK, 1.3)
        painter.drawRect(QRectF(3.5, 4.5, 17, 15))
        _pen(painter, INK, 1.2)
        for offset in range(3):
            y = 8.5 + offset * 3.6
            painter.drawLine(QPointF(6, y), QPointF(14, y))
            painter.drawLine(QPointF(16, y), QPointF(18, y))
    elif name == "plot":
        _pen(painter, INK, 1.2)
        painter.drawLine(QPointF(5, 4), QPointF(5, 19))
        painter.drawLine(QPointF(5, 19), QPointF(20, 19))
        _pen(painter, INK, 1.6)
        path = QPainterPath(QPointF(6, 16))
        path.cubicTo(QPointF(10, 4), QPointF(15, 4), QPointF(19, 13))
        painter.drawPath(path)
    elif name == "table":
        _pen(painter, INK, 1.3)
        painter.drawRect(QRectF(4, 6, 16, 12))
        painter.drawLine(QPointF(4, 10), QPointF(20, 10))
        painter.drawLine(QPointF(4, 14), QPointF(20, 14))
        painter.drawLine(QPointF(9.3, 6), QPointF(9.3, 18))
        painter.drawLine(QPointF(14.6, 6), QPointF(14.6, 18))
    elif name == "contents":
        _pen(painter, INK, 1.3)
        painter.drawRect(QRectF(4, 4, 16, 16))
        _pen(painter, INK, 1.1)
        for offset in range(4):
            y = 7.5 + offset * 3.3
            painter.drawLine(QPointF(6.5, y), QPointF(14, y))
            painter.drawLine(QPointF(16, y), QPointF(17.5, y))
    # -- measuring: every one of these carries the little ruler edge that
    #    Bluebeam puts on its measurement tools, so they read as a family.
    elif name == "measure_length":
        _ruler(painter)
        _pen(painter, INK, 1.5)
        _arrow(painter, QPointF(13, 9), QPointF(5, 9), INK)
        _arrow(painter, QPointF(11, 9), QPointF(19, 9), INK)
    elif name == "dimension":
        _pen(painter, INK, 1.4)
        painter.drawLine(QPointF(5, 4), QPointF(5, 20))
        painter.drawLine(QPointF(19, 4), QPointF(19, 20))
        _arrow(painter, QPointF(13, 12), QPointF(5, 12), INK)
        _arrow(painter, QPointF(11, 12), QPointF(19, 12), INK)
    elif name == "measure_polylength":
        _ruler(painter)
        _pen(painter, INK, 1.5)
        painter.drawPolyline(QPolygonF([QPointF(4, 14), QPointF(9, 5), QPointF(14, 12),
                                        QPointF(20, 4)]))
    elif name == "measure_area":
        _ruler(painter)
        _pen(painter, INK, 1.4)
        painter.setBrush(QBrush(QColor(INK).lighter(190)))
        painter.drawPolygon(QPolygonF([QPointF(4, 14), QPointF(8, 4), QPointF(19, 6),
                                       QPointF(17, 15)]))
        painter.setBrush(Qt.NoBrush)
    elif name == "measure_perimeter":
        _ruler(painter)
        _pen(painter, INK, 1.5, Qt.DashLine)
        painter.drawPolygon(QPolygonF([QPointF(4, 14), QPointF(8, 4), QPointF(19, 6),
                                       QPointF(17, 15)]))
        _pen(painter, INK, 1.5)
    elif name == "measure_volume":
        _ruler(painter)
        _pen(painter, INK, 1.4)
        painter.drawPolygon(QPolygonF([QPointF(4, 11), QPointF(11, 4), QPointF(20, 7),
                                       QPointF(13, 14)]))
        painter.drawLine(QPointF(4, 11), QPointF(4, 15))
        painter.drawLine(QPointF(13, 14), QPointF(13, 18))
        painter.drawLine(QPointF(20, 7), QPointF(20, 11))
        painter.drawPolyline(QPolygonF([QPointF(4, 15), QPointF(13, 18), QPointF(20, 11)]))
    elif name == "measure_angle":
        _ruler(painter)
        _pen(painter, INK, 1.5)
        painter.drawLine(QPointF(4, 15), QPointF(20, 15))
        painter.drawLine(QPointF(4, 15), QPointF(16, 4))
        painter.drawArc(QRectF(-1, 9, 12, 12), 0, 43 * 16)
    elif name == "measure_radius":
        _ruler(painter)
        _pen(painter, INK, 1.4)
        painter.drawEllipse(QRectF(4, 2, 15, 15))
        painter.setBrush(QBrush(QColor(INK)))
        painter.drawEllipse(QPointF(11.5, 9.5), 1.1, 1.1)
        painter.setBrush(Qt.NoBrush)
        _arrow(painter, QPointF(11.5, 9.5), QPointF(19, 9.5), INK)
    elif name == "measure_diameter":
        _ruler(painter)
        _pen(painter, INK, 1.4)
        painter.drawEllipse(QRectF(4, 2, 15, 15))
        _arrow(painter, QPointF(11.5, 9.5), QPointF(4.2, 9.5), INK)
        _arrow(painter, QPointF(11.5, 9.5), QPointF(18.8, 9.5), INK)
    elif name in ("cutout_polygon", "cutout_ellipse"):
        _ruler(painter)
        _pen(painter, INK, 1.4)
        painter.setBrush(QBrush(QColor(INK).lighter(190)))
        painter.drawPolygon(QPolygonF([QPointF(4, 14), QPointF(8, 4), QPointF(19, 6),
                                       QPointF(17, 15)]))
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        _pen(painter, INK, 1.1, Qt.DashLine)
        if name == "cutout_polygon":
            painter.drawPolygon(QPolygonF([QPointF(8, 11), QPointF(12, 7),
                                           QPointF(15, 12)]))
        else:
            painter.drawEllipse(QRectF(8, 7, 7, 5))
        painter.setBrush(Qt.NoBrush)
    elif name == "count":
        _pen(painter, MARKER, 1.5)
        for x in (5.5, 10, 14.5):
            painter.drawLine(QPointF(x, 5), QPointF(x, 15))
        painter.drawLine(QPointF(17, 4), QPointF(19.5, 16))
        _glyph(painter, "3", MARKER, 7, True, QRectF(12, 12, 11, 11))
    elif name == "calibrate":
        _pen(painter, WARM, 1.5)
        painter.drawLine(QPointF(4, 16), QPointF(20, 16))
        for x in (5, 10, 15, 19):
            painter.drawLine(QPointF(x, 16), QPointF(x, 11))
        _glyph(painter, "?", WARM, 9, True, QRectF(6, 2, 12, 10))
    elif name == "format_painter":
        # Bluebeam's paint brush: a handle, a ferrule and bristles, held at an
        # angle. The one icon everybody recognises for "take that look and put
        # it on this".
        _pen(painter, INK, 1.4)
        painter.setBrush(Qt.NoBrush)
        painter.drawPolygon(QPolygonF([QPointF(14.2, 2.6), QPointF(19.4, 7.8),
                                       QPointF(11.6, 15.6), QPointF(6.4, 10.4)]))
        painter.setBrush(QBrush(QColor(INK)))
        painter.drawPolygon(QPolygonF([QPointF(6.4, 10.4), QPointF(11.6, 15.6),
                                       QPointF(9.2, 18.0), QPointF(4.0, 12.8)]))
        # the bristles, spreading out below the ferrule
        _pen(painter, INK, 1.3)
        painter.setBrush(Qt.NoBrush)
        painter.drawPolyline(QPolygonF([QPointF(4.0, 12.8), QPointF(2.4, 17.4),
                                        QPointF(4.6, 20.6), QPointF(9.2, 18.0)]))
        painter.drawLine(QPointF(4.4, 15.4), QPointF(6.6, 17.6))
    # -- the panel rail: one icon per panel, none of them a tool's ---------
    elif name == "panel_pages":
        _pen(painter, INK, 1.3)
        painter.drawRect(QRectF(3.5, 4.5, 7, 9))
        painter.drawRect(QRectF(13.5, 4.5, 7, 9))
        painter.drawRect(QRectF(3.5, 16.5, 7, 4))
        painter.drawRect(QRectF(13.5, 16.5, 7, 4))
    elif name == "panel_bookmarks":
        _pen(painter, INK, 1.4)
        painter.drawPolyline(QPolygonF([QPointF(7, 3), QPointF(7, 20),
                                        QPointF(12, 15.5), QPointF(17, 20),
                                        QPointF(17, 3), QPointF(7, 3)]))
    elif name == "panel_toolsets":
        # A tool chest: a box with a handle.
        _pen(painter, INK, 1.3)
        painter.drawRect(QRectF(3.5, 8.5, 17, 11))
        painter.drawLine(QPointF(3.5, 12.5), QPointF(20.5, 12.5))
        painter.drawPolyline(QPolygonF([QPointF(9, 8.5), QPointF(9, 5.5),
                                        QPointF(15, 5.5), QPointF(15, 8.5)]))
    elif name == "panel_markups":
        _pen(painter, INK, 1.3)
        for offset in range(3):
            y = 6.5 + offset * 5
            painter.drawRect(QRectF(3.5, y - 1.5, 3, 3))
            painter.drawLine(QPointF(9, y), QPointF(20.5, y))
    elif name == "panel_properties":
        _pen(painter, INK, 1.3)
        painter.drawRect(QRectF(3.5, 4.5, 17, 15))
        painter.drawLine(QPointF(10, 4.5), QPointF(10, 19.5))
        for offset in range(3):
            y = 8 + offset * 4
            painter.drawLine(QPointF(12, y), QPointF(18.5, y))
    elif name == "panel_variables":
        _glyph(painter, "x", INK, 11, False, QRectF(2, 3, 10, 12))
        _glyph(painter, "y", INK, 11, False, QRectF(11, 8, 10, 12))
        _pen(painter, INK, 1.2)
        painter.drawLine(QPointF(3, 20), QPointF(20, 20))
    elif name == "panel_functions":
        _glyph(painter, "ƒ", INK, 15, False, QRectF(2, 1, 12, 20))
        _pen(painter, INK, 1.3)
        painter.drawArc(QRectF(11, 5, 5, 14), 260 * 16, 200 * 16)
        painter.drawArc(QRectF(16, 5, 5, 14), 80 * 16, 200 * 16)
    elif name == "panel_layers":
        _pen(painter, INK, 1.3)
        for offset in range(3):
            y = 7 + offset * 4.6
            painter.drawPolygon(QPolygonF([QPointF(12, y - 3), QPointF(20, y),
                                           QPointF(12, y + 3), QPointF(4, y)]))
    elif name == "panel_problems":
        _pen(painter, INK, 1.4)
        painter.drawPolygon(QPolygonF([QPointF(12, 3.5), QPointF(21, 19.5),
                                       QPointF(3, 19.5)]))
        painter.drawLine(QPointF(12, 9), QPointF(12, 14))
        painter.setBrush(QBrush(QColor(INK)))
        painter.drawEllipse(QPointF(12, 17), 0.9, 0.9)
        painter.setBrush(Qt.NoBrush)
    elif name == "page":
        _pen(painter, INK, 1.4)
        painter.drawRect(QRectF(6, 3, 12, 18))
        _pen(painter, FAINT, 1.0)
        for offset in range(4):
            painter.drawLine(QPointF(8, 7 + offset * 3.2), QPointF(16, 7 + offset * 3.2))
    elif name == "pdf":
        _pen(painter, DANGER, 1.4)
        painter.drawRect(QRectF(5, 3, 14, 18))
        _glyph(painter, "PDF", DANGER, 6, True, QRectF(5, 8, 14, 10))
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
    elif name in ("undo", "redo"):
        # An arrow that comes back on itself: a half-turn of a circle, with a
        # head on the end that actually lines up with where the curve is going.
        # The old pair had the head guessed at three fixed points, which is why
        # they looked broken at any size.
        back = name == "undo"
        _pen(painter, INK, 1.7)
        path = QPainterPath()
        if back:
            path.moveTo(19.5, 19)
            path.cubicTo(QPointF(19.5, 9), QPointF(14, 6), QPointF(7, 6))
        else:
            path.moveTo(4.5, 19)
            path.cubicTo(QPointF(4.5, 9), QPointF(10, 6), QPointF(17, 6))
        painter.drawPath(path)
        painter.setBrush(QBrush(QColor(INK)))
        painter.setPen(Qt.NoPen)
        tip = QPointF(6.5, 6) if back else QPointF(17.5, 6)
        wing = 4.6 if back else -4.6
        painter.drawPolygon(QPolygonF([tip,
                                       QPointF(tip.x() + wing, tip.y() - 3.4),
                                       QPointF(tip.x() + wing, tip.y() + 3.4)]))
        painter.setBrush(Qt.NoBrush)
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
        _pen(painter, DANGER, 1.5)
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
