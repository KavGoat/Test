"""Toolbar icons, painted rather than shipped as files."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

INK = QColor("#2f3640")
ACCENT = QColor("#d62828")
BLUE = QColor("#1a73e8")
GREEN = QColor("#1a8c3a")
BROWN = QColor("#8b4513")
PURPLE = QColor("#7a4fd6")
ORANGE = QColor("#e08000")


def _canvas() -> tuple[QPixmap, QPainter]:
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(INK, 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    return pixmap, painter


def _sheet(painter: QPainter, rect: QRectF = QRectF(7, 4, 18, 24)) -> None:
    painter.drawRect(rect)


def open_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.drawPolyline([QPointF(4, 26), QPointF(4, 8), QPointF(13, 8),
                          QPointF(16, 12), QPointF(26, 12)])
    painter.drawPolyline([QPointF(4, 26), QPointF(9, 16), QPointF(30, 16),
                          QPointF(25, 26), QPointF(4, 26)])
    painter.end()
    return QIcon(pixmap)


def save_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.drawRect(QRectF(5, 5, 22, 22))
    painter.drawRect(QRectF(10, 5, 12, 8))
    painter.drawRect(QRectF(10, 18, 12, 9))
    painter.end()
    return QIcon(pixmap)


def add_page_icon() -> QIcon:
    pixmap, painter = _canvas()
    _sheet(painter, QRectF(5, 4, 15, 20))
    painter.setPen(QPen(ACCENT, 2.4, Qt.SolidLine, Qt.RoundCap))
    painter.drawLine(QPointF(23, 21), QPointF(23, 29))
    painter.drawLine(QPointF(19, 25), QPointF(27, 25))
    painter.end()
    return QIcon(pixmap)


def delete_page_icon() -> QIcon:
    pixmap, painter = _canvas()
    _sheet(painter, QRectF(5, 4, 15, 20))
    painter.setPen(QPen(ACCENT, 2.4, Qt.SolidLine, Qt.RoundCap))
    painter.drawLine(QPointF(19, 25), QPointF(27, 25))
    painter.end()
    return QIcon(pixmap)


def select_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.setBrush(INK)
    painter.drawPolygon([QPointF(9, 5), QPointF(9, 24), QPointF(14, 19),
                         QPointF(18, 27), QPointF(21, 25), QPointF(17, 18),
                         QPointF(24, 17)])
    painter.end()
    return QIcon(pixmap)


def rectangle_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.setPen(QPen(ACCENT, 2.4))
    painter.drawRect(QRectF(5, 8, 22, 16))
    painter.end()
    return QIcon(pixmap)


def line_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.setPen(QPen(BLUE, 2.4, Qt.SolidLine, Qt.RoundCap))
    painter.drawLine(QPointF(6, 26), QPointF(26, 6))
    painter.end()
    return QIcon(pixmap)


def arrow_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.setPen(QPen(BLUE, 2.4, Qt.SolidLine, Qt.RoundCap))
    painter.drawLine(QPointF(6, 26), QPointF(26, 6))
    painter.drawLine(QPointF(26, 6), QPointF(19, 8))
    painter.drawLine(QPointF(26, 6), QPointF(24, 13))
    painter.end()
    return QIcon(pixmap)


def ellipse_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.setPen(QPen(GREEN, 2.4))
    painter.drawEllipse(QRectF(4, 7, 24, 18))
    painter.end()
    return QIcon(pixmap)


def polygon_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.setPen(QPen(BROWN, 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.drawPolygon([QPointF(16, 4), QPointF(28, 14), QPointF(24, 28),
                         QPointF(8, 28), QPointF(4, 14)])
    painter.end()
    return QIcon(pixmap)


def cloud_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.setPen(QPen(ACCENT, 2.0))
    painter.drawArc(QRectF(3, 10, 12, 14), 90 * 16, 180 * 16)
    painter.drawArc(QRectF(9, 6, 14, 12), 30 * 16, 180 * 16)
    painter.drawArc(QRectF(17, 10, 12, 14), -90 * 16, 180 * 16)
    painter.drawArc(QRectF(8, 16, 16, 12), 210 * 16, 180 * 16)
    painter.end()
    return QIcon(pixmap)


def ink_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.setPen(QPen(PURPLE, 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.drawPolyline([QPointF(5, 24), QPointF(10, 12), QPointF(16, 20),
                          QPointF(22, 8), QPointF(28, 16)])
    painter.end()
    return QIcon(pixmap)


def highlight_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(255, 235, 59, 160))
    painter.drawRect(QRectF(4, 10, 24, 12))
    painter.setPen(QPen(INK, 1.2))
    painter.drawLine(QPointF(6, 16), QPointF(26, 16))
    painter.end()
    return QIcon(pixmap)


def text_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.setPen(QPen(INK, 2.0))
    painter.drawRect(QRectF(4, 6, 24, 20))
    font = painter.font()
    font.setPointSizeF(12)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(QRectF(4, 6, 24, 20), Qt.AlignCenter, "T")
    painter.end()
    return QIcon(pixmap)


def note_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.setPen(QPen(ORANGE, 2.0))
    painter.setBrush(QColor(255, 240, 180))
    painter.drawRect(QRectF(6, 6, 20, 20))
    painter.setPen(QPen(INK, 1.2))
    painter.drawLine(QPointF(10, 13), QPointF(22, 13))
    painter.drawLine(QPointF(10, 17), QPointF(22, 17))
    painter.drawLine(QPointF(10, 21), QPointF(18, 21))
    painter.end()
    return QIcon(pixmap)


def rotate_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.setPen(QPen(INK, 2.0, Qt.SolidLine, Qt.RoundCap))
    painter.drawArc(QRectF(6, 6, 20, 20), 45 * 16, 270 * 16)
    painter.drawLine(QPointF(22, 5), QPointF(26, 9))
    painter.drawLine(QPointF(22, 5), QPointF(18, 9))
    painter.end()
    return QIcon(pixmap)


def order_front_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.setPen(QPen(QColor("#aaa"), 1.4))
    painter.drawRect(QRectF(4, 4, 14, 14))
    painter.setPen(QPen(BLUE, 2.0))
    painter.setBrush(QColor(220, 233, 251))
    painter.drawRect(QRectF(14, 14, 14, 14))
    painter.end()
    return QIcon(pixmap)


def order_back_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.setPen(QPen(BLUE, 2.0))
    painter.setBrush(QColor(220, 233, 251))
    painter.drawRect(QRectF(4, 4, 14, 14))
    painter.setPen(QPen(QColor("#aaa"), 1.4))
    painter.drawRect(QRectF(14, 14, 14, 14))
    painter.end()
    return QIcon(pixmap)


def zoom_icon(plus: bool) -> QIcon:
    pixmap, painter = _canvas()
    painter.drawEllipse(QRectF(5, 5, 17, 17))
    painter.drawLine(QPointF(21, 21), QPointF(28, 28))
    painter.drawLine(QPointF(9, 13.5), QPointF(18, 13.5))
    if plus:
        painter.drawLine(QPointF(13.5, 9), QPointF(13.5, 18))
    painter.end()
    return QIcon(pixmap)


def fit_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.drawRect(QRectF(6, 6, 20, 20))
    painter.drawLine(QPointF(11, 11), QPointF(21, 21))
    painter.drawPolyline([QPointF(11, 16), QPointF(11, 11), QPointF(16, 11)])
    painter.drawPolyline([QPointF(21, 16), QPointF(21, 21), QPointF(16, 21)])
    painter.end()
    return QIcon(pixmap)


def app_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor("#ffffff"))
    painter.setPen(QPen(INK, 3.0))
    painter.drawRect(QRectF(12, 6, 40, 52))
    painter.setPen(QPen(ACCENT, 4.0))
    painter.drawRect(QRectF(21, 24, 22, 16))
    painter.end()
    return QIcon(pixmap)
