"""Revu's rulers and Full-Screen Crosshair (View menu; the user's choice,
2026-10-15).

Rulers lie along the top and left edges of the drawing. Measured from the
top-left corner of the page in view, in inches, centimetres, millimetres,
points or picas (right-click a ruler to choose), they show where the page
lies, what is selected and where the pointer is, and they follow the zoom.

The Full-Screen Crosshair is two lines across the whole drawing that meet at
the pointer, in the snap colour.
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QMenu, QWidget

#: How thick a ruler is, in screen pixels.
THICK = 20

#: Points in one of each unit, and how a ruler names it.
UNITS = {"in": (72.0, "Inches"), "cm": (72.0 / 2.54, "Centimeters"),
         "mm": (72.0 / 25.4, "Millimeters"), "pt": (1.0, "Points"),
         "pica": (12.0, "Picas")}

#: The crosshair's colour: the snap marker's.
CROSSHAIR = "#1971c2"


def _theme() -> dict:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    dark = app is not None and app.palette().window().color().lightness() < 128
    if dark:
        return {"bg": "#232427", "ink": "#c7cbd1", "page": "#3a3d42", "edge": "#45474b",
                "selected": "#2f5d8a"}
    return {"bg": "#f3f4f6", "ink": "#3b3f45", "page": "#ffffff", "edge": "#c3c7cc",
            "selected": "#bcd7f5"}


def _step(pixels_per_unit: float) -> tuple:
    """A labelled step in units, at least ~60 px apart, of 1, 2 or 5 × 10ⁿ,
    and how many small ticks it is cut into."""
    if pixels_per_unit <= 0:
        return 1.0, 1
    want = 60.0 / pixels_per_unit
    power = 10 ** math.floor(math.log10(want))
    for factor, ticks in ((1, 10), (2, 4), (5, 5), (10, 10)):
        if factor * power >= want:
            return factor * power, ticks
    return 10 * power, 10


def _label(value: float) -> str:
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    return f"{value:g}"


class Ruler(QWidget):
    def __init__(self, view, rulers, across: bool):
        super().__init__(view)
        self.view = view
        self.rulers = rulers
        self.across = across                 # True: along the top
        self.setObjectName("rulerTop" if across else "rulerLeft")
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)
        self.setToolTip("Right-click to choose the ruler's units")

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        for key, (_points, name) in UNITS.items():
            action = menu.addAction(name, lambda k=key: self.rulers.set_unit(k))
            action.setCheckable(True)
            action.setChecked(key == self.rulers.unit)
        menu.exec(event.globalPos())

    # -- where things are, in this ruler's pixels ----------------------------------------------
    def _along(self, scene: QPointF) -> float:
        at = self.view.mapFromScene(scene)
        return float(at.x() if self.across else at.y())

    def paintEvent(self, _event) -> None:
        t = _theme()
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(t["bg"]))
        page = self.rulers.page_rect()
        length = self.width() if self.across else self.height()
        if page is not None:
            start = self._along(page.topLeft())
            end = self._along(page.bottomRight())
            band = QRectF(start, 0, end - start, THICK) if self.across \
                else QRectF(0, start, THICK, end - start)
            painter.fillRect(band, QColor(t["page"]))
            for rect in self.rulers.selected_rects():
                a, b = self._along(rect.topLeft()), self._along(rect.bottomRight())
                mark = QRectF(a, 0, b - a, THICK) if self.across else QRectF(0, a, THICK, b - a)
                painter.fillRect(mark, QColor(t["selected"]))
            origin = start
            zoom = max(self.view.zoom(), 1e-6)
            points, _name = UNITS[self.rulers.unit]
            per_unit = points * zoom                       # pixels in one unit
            step, ticks = _step(per_unit)
            first = math.floor((0 - origin) / (per_unit * step)) - 1
            last = math.ceil((length - origin) / (per_unit * step)) + 1
            painter.setPen(QPen(QColor(t["ink"]), 1))
            font = QFont(self.font())
            font.setPointSizeF(7.0)
            painter.setFont(font)
            for n in range(first, last + 1):
                for k in range(ticks):
                    value = (n + k / ticks) * step
                    at = origin + value * per_unit
                    if at < -1 or at > length + 1:
                        continue
                    size = THICK - 2 if k == 0 else (THICK // 3 if ticks % 2 or k != ticks // 2
                                                    else THICK // 2)
                    x = int(round(at)) + 0.5
                    if self.across:
                        painter.drawLine(QPointF(x, THICK - size), QPointF(x, THICK))
                    else:
                        painter.drawLine(QPointF(THICK - size, x), QPointF(THICK, x))
                    if k == 0:
                        text = _label(value)
                        if self.across:
                            painter.drawText(QRect(int(at) + 3, 1, 60, 10),
                                             Qt.AlignLeft | Qt.AlignTop, text)
                        else:
                            painter.save()
                            painter.translate(1, int(at) + 3)
                            painter.rotate(90)
                            painter.drawText(QRect(0, -10, 60, 10),
                                             Qt.AlignLeft | Qt.AlignBottom, text)
                            painter.restore()
        pointer = self.rulers.pointer
        if pointer is not None:
            at = self._along(pointer)
            painter.setPen(QPen(QColor("#f08c00"), 2))
            if self.across:
                painter.drawLine(QPointF(at, 0), QPointF(at, THICK))
            else:
                painter.drawLine(QPointF(0, at), QPointF(THICK, at))
        painter.setPen(QPen(QColor(t["edge"]), 1))
        if self.across:
            painter.drawLine(0, THICK - 1, self.width(), THICK - 1)
        else:
            painter.drawLine(THICK - 1, 0, THICK - 1, self.height())
        painter.end()


class Rulers:
    """The two rulers of one view, and the corner where they meet."""

    def __init__(self, view):
        self.view = view
        self.on = False
        self.unit = self._kept_unit()
        self.pointer: Optional[QPointF] = None
        self.top = Ruler(view, self, True)
        self.left = Ruler(view, self, False)
        self.corner = QWidget(view)
        self.corner.setObjectName("rulerCorner")
        self.corner.setAutoFillBackground(True)
        for widget in (self.top, self.left, self.corner):
            widget.hide()
        view.horizontalScrollBar().valueChanged.connect(lambda _v: self.refresh())
        view.verticalScrollBar().valueChanged.connect(lambda _v: self.refresh())
        view.zoomChanged.connect(lambda _z: self.refresh())
        view.cursorMoved.connect(self.follow)

    @staticmethod
    def _kept_unit() -> str:
        from ..settings import app_settings
        unit = str(app_settings().value("view/ruler_unit", "cm") or "cm")
        return unit if unit in UNITS else "cm"

    def set_unit(self, unit: str) -> None:
        from ..settings import app_settings
        if unit in UNITS:
            self.unit = unit
            app_settings().setValue("view/ruler_unit", unit)
            self.refresh()

    def show(self, on: bool) -> None:
        self.on = bool(on)
        margin = THICK if self.on else 0
        self.view.setViewportMargins(margin, margin, 0, 0)
        for widget in (self.top, self.left, self.corner):
            widget.setVisible(self.on)
        self.place()

    def place(self) -> None:
        if not self.on:
            return
        area = self.view.viewport().geometry()
        self.top.setGeometry(area.left(), area.top() - THICK, area.width(), THICK)
        self.left.setGeometry(area.left() - THICK, area.top(), THICK, area.height())
        self.corner.setGeometry(area.left() - THICK, area.top() - THICK, THICK, THICK)
        self.corner.setStyleSheet(f"background: {_theme()['bg']};")
        for widget in (self.top, self.left, self.corner):
            widget.raise_()
        self.refresh()

    def refresh(self) -> None:
        if self.on:
            self.top.update()
            self.left.update()

    def follow(self, scene_pos: QPointF) -> None:
        self.pointer = QPointF(scene_pos)
        self.refresh()

    # -- what the rulers measure from ----------------------------------------------------------
    def page_rect(self) -> Optional[QRectF]:
        scene = self.view.scene()
        frames = getattr(scene, "frames", None)
        if not frames:
            return None
        index = getattr(self.view.window, "current_index", 0)
        index = max(0, min(index, len(frames) - 1))
        frame = frames[index]
        return frame.mapRectToScene(frame.page_rect())

    def selected_rects(self) -> list:
        scene = self.view.scene()
        if scene is None:
            return []
        from ..items.base import MarkupItem, covered_rect
        out = []
        for item in scene.selectedItems():
            if isinstance(item, MarkupItem) and item.parentItem() is not None:
                out.append(item.parentItem().mapRectToScene(covered_rect(item)))
        return out


class Crosshair:
    """Two lines across the drawing meeting at the pointer."""

    def __init__(self, view):
        self.view = view
        self.on = False
        self.at: Optional[QPointF] = None        # in the viewport's pixels
        view.cursorMoved.connect(self.follow)

    def show(self, on: bool) -> None:
        self.on = bool(on)
        self._dirty()
        if not self.on:
            self.at = None

    def _strips(self) -> list:
        if self.at is None:
            return []
        area = self.view.viewport().rect()
        x, y = int(self.at.x()), int(self.at.y())
        return [QRect(x - 2, area.top(), 5, area.height()), QRect(area.left(), y - 2, area.width(), 5)]

    def _dirty(self) -> None:
        for strip in self._strips():
            self.view.viewport().update(strip)

    def follow(self, scene_pos: QPointF) -> None:
        if not self.on:
            return
        self._dirty()
        self.at = QPointF(self.view.mapFromScene(scene_pos))
        self._dirty()

    def paint(self, painter: QPainter) -> None:
        """Called from the view's foreground, in scene coordinates."""
        if not self.on or self.at is None:
            return
        painter.save()
        painter.resetTransform()
        pen = QPen(QColor(CROSSHAIR), 1)
        painter.setPen(pen)
        area = self.view.viewport().rect()
        x, y = int(self.at.x()) + 0.5, int(self.at.y()) + 0.5
        painter.drawLine(QPointF(x, area.top()), QPointF(x, area.bottom()))
        painter.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
        painter.restore()
