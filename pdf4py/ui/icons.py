"""Toolbar icons, painted rather than shipped as files."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

INK = QColor("#2f3640")
ACCENT = QColor("#d62828")


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
