"""Toolbar icons, painted rather than shipped as files."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

INK = QColor("#a9b1d6")
ACCENT = QColor("#f7768e")
BLUE = QColor("#7aa2f7")
GREEN = QColor("#9ece6a")
BROWN = QColor("#e0af68")
PURPLE = QColor("#bb9af7")
ORANGE = QColor("#ff9e64")


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
    painter.setBrush(QColor(255, 235, 59, 100))
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
    painter.setBrush(QColor(255, 240, 180, 80))
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
    painter.setPen(QPen(QColor("#565f89"), 1.4))
    painter.drawRect(QRectF(4, 4, 14, 14))
    painter.setPen(QPen(BLUE, 2.0))
    painter.setBrush(QColor(40, 52, 87, 160))
    painter.drawRect(QRectF(14, 14, 14, 14))
    painter.end()
    return QIcon(pixmap)


def order_back_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.setPen(QPen(BLUE, 2.0))
    painter.setBrush(QColor(40, 52, 87, 160))
    painter.drawRect(QRectF(4, 4, 14, 14))
    painter.setPen(QPen(QColor("#565f89"), 1.4))
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


def polyline_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.setPen(QPen(BLUE, 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.drawPolyline([QPointF(5, 26), QPointF(12, 8), QPointF(20, 22), QPointF(27, 6)])
    painter.end()
    return QIcon(pixmap)


def stamp_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.setPen(QPen(ACCENT, 2.0))
    painter.drawRect(QRectF(4, 8, 24, 14))
    font = painter.font()
    font.setPointSizeF(7)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(QRectF(4, 8, 24, 14), Qt.AlignCenter, "OK")
    painter.end()
    return QIcon(pixmap)


def eraser_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.setPen(QPen(INK, 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.drawPolygon([QPointF(8, 24), QPointF(4, 18), QPointF(20, 6),
                         QPointF(28, 6), QPointF(28, 12), QPointF(12, 24)])
    painter.drawLine(QPointF(14, 16), QPointF(22, 10))
    painter.end()
    return QIcon(pixmap)


def measure_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.setPen(QPen(GREEN, 2.4, Qt.SolidLine, Qt.RoundCap))
    painter.drawLine(QPointF(4, 24), QPointF(28, 8))
    painter.drawLine(QPointF(4, 20), QPointF(4, 28))
    painter.drawLine(QPointF(28, 4), QPointF(28, 12))
    painter.end()
    return QIcon(pixmap)


def lasso_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.setPen(QPen(INK, 2.0, Qt.DashLine, Qt.RoundCap, Qt.RoundJoin))
    painter.drawEllipse(QRectF(4, 6, 24, 16))
    painter.setPen(QPen(INK, 2.0, Qt.SolidLine, Qt.RoundCap))
    painter.drawLine(QPointF(20, 20), QPointF(16, 28))
    painter.end()
    return QIcon(pixmap)


def redaction_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(0, 0, 0))
    painter.drawRect(QRectF(4, 10, 24, 12))
    painter.end()
    return QIcon(pixmap)


def print_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.setPen(QPen(INK, 2.0))
    painter.drawRect(QRectF(3, 12, 26, 12))
    painter.drawRect(QRectF(8, 4, 16, 10))
    painter.drawRect(QRectF(8, 20, 16, 8))
    painter.end()
    return QIcon(pixmap)


def duplicate_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.setPen(QPen(INK, 1.8))
    painter.drawRect(QRectF(4, 8, 16, 20))
    painter.setPen(QPen(BLUE, 1.8))
    painter.drawRect(QRectF(12, 4, 16, 20))
    painter.end()
    return QIcon(pixmap)


def theme_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.setPen(QPen(INK, 2.0))
    painter.drawEllipse(QRectF(6, 6, 20, 20))
    painter.setBrush(INK)
    from PySide6.QtGui import QPainterPath
    path = QPainterPath()
    path.moveTo(16, 6)
    path.arcTo(QRectF(6, 6, 20, 20), 90, -180)
    path.closeSubpath()
    painter.drawPath(path)
    painter.end()
    return QIcon(pixmap)


def app_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor("#24283b"))
    painter.setPen(QPen(QColor("#7aa2f7"), 3.0))
    painter.drawRoundedRect(QRectF(12, 6, 40, 52), 4, 4)
    painter.setPen(QPen(QColor("#f7768e"), 4.0))
    painter.drawRect(QRectF(21, 24, 22, 16))
    painter.end()
    return QIcon(pixmap)
