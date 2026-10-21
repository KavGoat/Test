"""Revu's select pointers: the arrow with a small sign at its lower right.

The user's photos of Revu 21 (2026-10-20): over a selected markup the
ordinary arrow carries a small four-way move sign; with Shift over a
side of a selected shape, a small thin "+". By the same pattern a "−" over a
point a Shift-click takes out, a small arc where an Alt-click rounds a corner
or bends a side, and a small boxed "+" where a Ctrl-drag copies. The sign says
what a click (or, for move and copy, a drag) does from there; nothing is drawn
on the canvas.

The arrow is the system's own white one outlined in black, so the pointer
keeps its look as it gains a sign; the sign is black with a white outline,
so it reads on a dark drawing as well as on paper. Each is drawn at the
screen's own pixel ratio (100 %, 125 %, 150 %, 200 %…) so it is crisp there
rather than scaled up from a small picture.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPainterPath, QPen, QPixmap

#: what each sign means
MOVE, ADD, REMOVE, CURVE, COPY = "move", "add", "remove", "curve", "copy"
BADGES = (MOVE, ADD, REMOVE, CURVE, COPY)

#: the cursor's size and its hot spot (the arrow's tip), in logical pixels
SIZE = 32
HOT_SPOT = (1, 1)

_INK = QColor("#000000")
_HALO = QColor("#ffffff")
_MADE: dict = {}


def arrow_path() -> QPainterPath:
    """The ordinary select arrow, tip at the hot spot, in logical pixels."""
    path = QPainterPath()
    x, y = HOT_SPOT
    # on whole pixels, as the system's arrow: its outline one crisp pixel
    for px, py in ((0, 0), (0, 16), (4, 12), (7, 19), (9, 18), (6, 11), (11, 11)):
        if px == 0 and py == 0:
            path.moveTo(x + px, y + py)
        else:
            path.lineTo(x + px, y + py)
    path.closeSubpath()
    return path


def badge_path(badge: str) -> QPainterPath:
    """The sign at the arrow's lower right, as strokes."""
    cx, cy = 20.5, 21.5             # its centre, clear of the arrow's tail
    path = QPainterPath()
    if badge == MOVE:
        # four small arrows out from the middle: the shafts here, the heads
        # (filled) in move_heads()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            path.moveTo(cx - dx * 0.0, cy - dy * 0.0)
            path.lineTo(cx + dx * 4.0, cy + dy * 4.0)
    elif badge == ADD:
        arm = 3.5                   # about a third of the arrow's height
        path.moveTo(cx - arm, cy)
        path.lineTo(cx + arm, cy)
        path.moveTo(cx, cy - arm)
        path.lineTo(cx, cy + arm)
    elif badge == REMOVE:
        arm = 3.5
        path.moveTo(cx - arm, cy)
        path.lineTo(cx + arm, cy)
    elif badge == CURVE:
        # a shallow arc between two small points
        path.moveTo(cx - 4.5, cy + 2.5)
        path.quadTo(cx, cy - 5.0, cx + 4.5, cy + 2.5)
    elif badge == COPY:
        box = QRectF(cx - 4.5, cy - 4.5, 9, 9)
        path.addRect(box)
        path.moveTo(cx - 2.2, cy)
        path.lineTo(cx + 2.2, cy)
        path.moveTo(cx, cy - 2.2)
        path.lineTo(cx, cy + 2.2)
    return path


def move_heads() -> QPainterPath:
    """The move sign's four arrowheads, as filled triangles."""
    cx, cy = 20.5, 21.5
    heads = QPainterPath()
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        tip = QPointF(cx + dx * 6.6, cy + dy * 6.6)
        back = QPointF(cx + dx * 3.6, cy + dy * 3.6)
        heads.moveTo(tip)
        heads.lineTo(back.x() + dy * 2.6, back.y() + dx * 2.6)
        heads.lineTo(back.x() - dy * 2.6, back.y() - dx * 2.6)
        heads.closeSubpath()
    return heads


def badge_pixmap(badge: str, ratio: float = 1.0) -> QPixmap:
    """The arrow and its sign, drawn for a screen of pixel *ratio*."""
    ratio = max(float(ratio), 1.0)
    pixmap = QPixmap(round(SIZE * ratio), round(SIZE * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    # the arrow as the system's own: white, outlined in black — the pointer
    # is that arrow everywhere else, and turning black as it went over a
    # markup was jarring (the user, 2026-10-20)
    arrow = arrow_path()
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, False)
    painter.setPen(QPen(_INK, 1.0, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin))
    painter.setBrush(_HALO)
    painter.drawPath(arrow)
    painter.restore()
    sign = badge_path(badge)
    heads = move_heads() if badge == MOVE else QPainterPath()
    painter.setBrush(Qt.NoBrush if badge != COPY else _HALO)
    halo = QPen(_HALO, 3.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(halo)
    painter.drawPath(sign)
    painter.setBrush(_HALO)
    painter.setPen(QPen(_HALO, 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.drawPath(heads)
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(_INK, 1.4, Qt.SolidLine, Qt.FlatCap if badge in (ADD, REMOVE)
                        else Qt.RoundCap, Qt.MiterJoin))
    painter.drawPath(sign)
    painter.setPen(Qt.NoPen)
    painter.setBrush(_INK)
    painter.drawPath(heads)
    if badge == CURVE:
        painter.setBrush(_INK)
        painter.setPen(QPen(_HALO, 1.0))
        for x in (16.0, 25.0):
            painter.drawEllipse(QPointF(x, 24.0), 1.6, 1.6)
    painter.end()
    return pixmap


def screen_ratio() -> float:
    """The main screen's pixel ratio, for a cursor drawn crisp on it."""
    return _ratio()


def _ratio() -> float:
    screen = QGuiApplication.primaryScreen()
    return screen.devicePixelRatio() if screen is not None else 1.0


def revu_cursor(badge: str, ratio: float = None) -> QCursor:
    """The select arrow with *badge* (MOVE, ADD, REMOVE, CURVE or COPY),
    made once for each screen pixel ratio."""
    ratio = _ratio() if ratio is None else max(float(ratio), 1.0)
    key = (badge, round(ratio, 3))
    if key not in _MADE:
        _MADE[key] = QCursor(badge_pixmap(badge, ratio), *HOT_SPOT)
    return _MADE[key]


def is_revu_cursor(cursor, badge: str) -> bool:
    """Whether *cursor* is the arrow with *badge*, at any pixel ratio."""
    if cursor is None or cursor.shape() != Qt.BitmapCursor:
        return False
    found = cursor.pixmap().cacheKey()
    return any(made.pixmap().cacheKey() == found
               for (name, _r), made in _MADE.items() if name == badge)


def move_cursor(ratio: float = None) -> QCursor:
    return revu_cursor(MOVE, ratio)


def copy_cursor(ratio: float = None) -> QCursor:
    return revu_cursor(COPY, ratio)
