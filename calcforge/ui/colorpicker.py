"""The colour picker, as Bluebeam Revu's (the user's request, 2026-10-14).

One picker for every colour in the application — line and fill, text,
cells, rules, equations, Color Processing — laid out as Revu 21's (taken
from its user manual's own pictures): the 48 Windows basic colours in an
8 × 6 grid whose last row is black, four greys, white, **No Color** (white
with a red slash, where a colour can be none) and the **eyedropper**; under
them eight slots for the colours picked from the screen or made with **More
Colors** (▾, which opens a colour editor inside the picker), the most recent
first, kept between sessions.

The popup draws its own background in the theme's colours, so it never
shows the window behind it or a white box on a dark theme.

The eyedropper picks any colour on the screen: the screen under the
pointer is shown still, with a magnified loupe and the colour's value; a
click takes the colour, Esc or a right-click leaves it.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEventLoop, QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QColor, QCursor, QGuiApplication, QIcon, QPainter, QPainterPath,
                           QPen, QPixmap)
from PySide6.QtWidgets import (QApplication, QFrame, QGridLayout, QHBoxLayout,
                               QToolButton, QVBoxLayout, QWidget)

# Revu's palette: the Windows basic colours, its own greys in the last row
GRID = (
    ("#FF8080", "#FFFF80", "#80FF80", "#00FF80", "#80FFFF", "#0080FF", "#FF80C0", "#FF80FF"),
    ("#FF0000", "#FFFF00", "#80FF00", "#00FF40", "#00FFFF", "#0080C0", "#8080C0", "#FF00FF"),
    ("#804040", "#FF8040", "#00FF00", "#008080", "#004080", "#8080FF", "#800040", "#FF0080"),
    ("#800000", "#FF8000", "#008000", "#008040", "#0000FF", "#0000A0", "#800080", "#8000FF"),
    ("#400000", "#804000", "#004000", "#004040", "#000080", "#000040", "#400040", "#400080"),
    ("#000000", "#333333", "#666666", "#999999", "#CCCCCC", "#FFFFFF"),
)
SLOTS = 8
SWATCH = 20

#: Tests answer the picker without showing it: a colour, "" for No Color,
#: None for cancelled. Consumed by the next call.
ANSWERS: list = []


def _dark() -> bool:
    app = QApplication.instance()
    return app is not None and app.palette().window().color().lightness() < 128


def _theme() -> dict:
    if _dark():
        return {"bg": "#2b2d30", "edge": "#45474b", "slot": "#2d2e31", "slot_edge": "#3c3d40",
                "hover": "#ffffff", "ink": "#d9dbde"}
    return {"bg": "#f6f6f7", "edge": "#b9bcc1", "slot": "#ebecee", "slot_edge": "#cfd2d6",
            "hover": "#1e5bbf", "ink": "#2b2d30"}


def custom_colours() -> list:
    """The colours picked from the screen or made with More Colors, newest first."""
    from ..app import app_settings
    value = app_settings().value("colours/custom", []) or []
    if isinstance(value, str):
        value = [value]
    return [str(v) for v in value if str(v).startswith("#")][:SLOTS]


def remember(colour: str) -> None:
    from ..app import app_settings
    kept = [c for c in custom_colours() if c.lower() != colour.lower()]
    app_settings().setValue("colours/custom", ([colour] + kept)[:SLOTS])


def swatch_icon(colour: str, size: int = 16) -> QIcon:
    """A square of *colour*; "" draws Revu's No Color (white, a red slash)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(colour) if colour else QColor("#ffffff"))
    painter = QPainter(pixmap)
    if not colour:
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor("#e03030"), max(1.5, size / 10)))
        painter.drawLine(QPointF(2, size - 2), QPointF(size - 2, 2))
    painter.setPen(QPen(QColor(0, 0, 0, 90), 1))
    painter.drawRect(0, 0, size - 1, size - 1)
    painter.end()
    return QIcon(pixmap)


def eyedropper_icon(colour: str = "#d9dbde", size: int = 18) -> QIcon:
    """A pipette, drawn: its bulb at the top right, its tip at the bottom left."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    s = size / 18.0
    painter.scale(s, s)
    ink = QColor(colour)
    painter.setPen(QPen(ink, 1.3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(Qt.NoBrush)
    tube = QPainterPath()
    tube.moveTo(2.5, 15.5)
    tube.lineTo(3.0, 13.0)
    tube.lineTo(10.0, 6.0)
    tube.lineTo(12.0, 8.0)
    tube.lineTo(5.0, 15.0)
    tube.closeSubpath()
    painter.drawPath(tube)
    painter.setBrush(ink)
    painter.drawRoundedRect(QRectF(10.6, 2.2, 5.0, 5.0), 2.0, 2.0)
    painter.drawLine(QPointF(9.0, 5.0), QPointF(13.0, 9.0))
    painter.end()
    return QIcon(pixmap)


class ColourPopup(QFrame):
    """Revu's colour picker, popped up under the control it belongs to."""

    picked = Signal(str)          # "#rrggbb", or "" for No Color
    closed = Signal()             # gone, picked or not (a click elsewhere closes a popup)

    def __init__(self, current: Optional[str], allow_none: bool, parent=None):
        super().__init__(parent, Qt.Popup)
        self.setObjectName("colourPopup")
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.current = (current or "").upper()
        self.allow_none = allow_none
        self.result: Optional[str] = None
        t = _theme()
        self.setStyleSheet(
            f"QFrame#colourPopup {{ background: {t['bg']}; border: 1px solid {t['edge']}; }}"
            f"QToolButton {{ background: transparent; border: 1px solid {t['slot_edge']}; "
            f"padding: 0px; margin: 0px; }}"
            f"QToolButton:hover {{ border: 1px solid {t['hover']}; }}"
            f"QToolButton:checked {{ border: 2px solid {t['hover']}; }}"
            f"QToolButton#slot {{ background: {t['slot']}; }}"
            f"QToolButton#plain {{ border: none; }}"
            f"QToolButton#plain:hover {{ border: 1px solid {t['hover']}; }}")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 4)
        outer.setSpacing(6)
        grid = QGridLayout()
        grid.setSpacing(3)
        self.buttons: dict = {}
        for r, row in enumerate(GRID):
            for c, colour in enumerate(row):
                grid.addWidget(self._swatch(colour), r, c)
        last = len(GRID) - 1
        none = self._swatch("", tip="No Color")
        none.setEnabled(self.allow_none)
        grid.addWidget(none, last, 6)
        dropper = QToolButton()
        dropper.setObjectName("plain")
        dropper.setIcon(eyedropper_icon(t["ink"]))
        dropper.setIconSize(QSize(SWATCH - 2, SWATCH - 2))
        dropper.setFixedSize(SWATCH + 2, SWATCH + 2)
        dropper.setToolTip("Eyedropper: pick a colour from anywhere on the screen")
        dropper.clicked.connect(self._eyedropper)
        self.dropper = dropper
        grid.addWidget(dropper, last, 7)
        outer.addLayout(grid)
        slots = QHBoxLayout()
        slots.setSpacing(3)
        kept = custom_colours()
        self.slots = []
        for k in range(SLOTS):
            colour = kept[k] if k < len(kept) else None
            if colour:
                button = self._swatch(colour.upper(), tip=f"{colour} (custom)")
            else:
                button = QToolButton()
                button.setObjectName("slot")
                button.setFixedSize(SWATCH + 2, SWATCH + 2)
                button.setEnabled(False)
                button.setToolTip("A custom colour goes here: pick one with the eyedropper "
                                  "or More Colors")
            self.slots.append(button)
            slots.addWidget(button)
        outer.addLayout(slots)
        more = QToolButton()
        more.setObjectName("plain")
        more.setArrowType(Qt.DownArrow)
        more.setToolTip("More Colors…")
        more.setFixedSize(22, 14)
        more.setStyleSheet("QToolButton { border: none; }")
        more.clicked.connect(self._more)
        self.more = more
        self.editor = None
        outer.addWidget(more, 0, Qt.AlignHCenter)

    def _swatch(self, colour: str, tip: str = "") -> QToolButton:
        button = QToolButton()
        button.setIcon(swatch_icon(colour, SWATCH - 4))
        button.setIconSize(QSize(SWATCH - 4, SWATCH - 4))
        button.setFixedSize(SWATCH + 2, SWATCH + 2)
        button.setToolTip(tip or colour)
        button.setCheckable(True)
        button.setChecked(colour.upper() == self.current and (bool(colour) or self.allow_none))
        button.clicked.connect(lambda _c=False, value=colour: self._take(value))
        self.buttons.setdefault(colour.upper(), button)
        return button

    def _take(self, colour: str) -> None:
        self.result = colour.lower() if colour else ""
        self.picked.emit(self.result)
        self.close()

    def _eyedropper(self) -> None:
        self._step_out()
        got = pick_from_screen()
        if got is None:
            self.close()
            return
        remember(got)
        self._take(got)

    def _more(self) -> None:
        """▾: More Colors opens below, in the picker (▴ closes it)."""
        if self.editor is None:
            self.editor = MoreColors(self.current or "#000000", _theme()["ink"])
            self.editor.added.connect(self._made)
            self.layout().insertWidget(self.layout().count() - 1, self.editor)
            self.editor.show()
        else:
            self.editor.setHidden(not self.editor.isHidden())
        shown = not self.editor.isHidden()
        self.more.setArrowType(Qt.UpArrow if shown else Qt.DownArrow)
        self.more.setToolTip("Fewer colours" if shown else "More Colors…")
        self.adjustSize()

    def _made(self, colour: str) -> None:
        remember(colour)
        self._take(colour)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        super().closeEvent(event)
        if not getattr(self, "_stepping_out", False):
            self.closed.emit()

    def _step_out(self) -> None:
        """Hidden for the eyedropper or More Colors, without counting as closed."""
        self._stepping_out = True
        self.hide()
        self._stepping_out = False

    def place(self, anchor) -> None:
        """Under *anchor* (a widget, or a global QPoint), kept on its screen."""
        self.adjustSize()
        if isinstance(anchor, QWidget):
            at = anchor.mapToGlobal(QPoint(0, anchor.height()))
            screen = anchor.screen()
        else:
            at = QPoint(anchor) if anchor is not None else QCursor.pos()
            screen = QGuiApplication.screenAt(at) or QGuiApplication.primaryScreen()
        room = screen.availableGeometry() if screen is not None else QRect(0, 0, 4000, 4000)
        x = max(room.left(), min(at.x(), room.right() - self.width()))
        y = at.y()
        if y + self.height() > room.bottom():
            y = max(room.top(), at.y() - self.height() - (anchor.height() if isinstance(anchor, QWidget) else 0))
        self.move(x, y)


def choose(anchor=None, current: Optional[str] = None, allow_none: bool = False,
           parent=None) -> Optional[str]:
    """Show the picker under *anchor* and wait: "#rrggbb", "" for No Color,
    or None when it was left without a choice (Esc, or a click elsewhere)."""
    if ANSWERS:
        return ANSWERS.pop(0)
    popup = ColourPopup(current, allow_none,
                        parent or (anchor if isinstance(anchor, QWidget) else None))
    popup.place(anchor)
    loop = QEventLoop()
    popup.closed.connect(loop.quit)
    popup.show()
    popup.setFocus()
    loop.exec()
    result = popup.result
    popup.deleteLater()
    return result


class _Spectrum(QWidget):
    """Saturation across, brightness down, for one hue: click or drag to pick."""

    changed = Signal(QColor)

    def __init__(self, colour: QColor):
        super().__init__()
        self.setFixedSize(168, 120)
        self.setCursor(Qt.CrossCursor)
        self.hue = max(0, colour.hsvHue())
        self.sat, self.val = colour.hsvSaturation(), colour.value()
        self._cache = None

    def set_hue(self, hue: int) -> None:
        self.hue = hue
        self._cache = None
        self.update()
        self.changed.emit(self.colour())

    def set_colour(self, colour: QColor) -> None:
        if colour.hsvHue() >= 0:
            self.hue = colour.hsvHue()
        self.sat, self.val = colour.hsvSaturation(), colour.value()
        self._cache = None
        self.update()

    def colour(self) -> QColor:
        return QColor.fromHsv(self.hue, self.sat, self.val)

    def paintEvent(self, _event) -> None:
        from PySide6.QtGui import QImage
        if self._cache is None:
            w, h = self.width(), self.height()
            image = QImage(w, h, QImage.Format_RGB32)
            for y in range(h):
                v = 255 - int(255 * y / (h - 1))
                for x in range(w):
                    image.setPixelColor(x, y, QColor.fromHsv(self.hue, int(255 * x / (w - 1)), v))
            self._cache = image
        painter = QPainter(self)
        painter.drawImage(0, 0, self._cache)
        x = self.sat * (self.width() - 1) / 255.0
        y = (255 - self.val) * (self.height() - 1) / 255.0
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor("#ffffff" if self.val < 140 else "#000000"), 1.5))
        painter.drawEllipse(QPointF(x, y), 4, 4)
        painter.end()

    def _at(self, point) -> None:
        self.sat = max(0, min(255, int(point.x() * 255 / (self.width() - 1))))
        self.val = max(0, min(255, 255 - int(point.y() * 255 / (self.height() - 1))))
        self.update()
        self.changed.emit(self.colour())

    def mousePressEvent(self, event) -> None:
        self._at(event.position())

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.LeftButton:
            self._at(event.position())


class _HueStrip(QWidget):
    changed = Signal(int)

    def __init__(self, hue: int):
        super().__init__()
        self.setFixedSize(14, 120)
        self.setCursor(Qt.PointingHandCursor)
        self.hue = max(0, hue)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        h = self.height()
        for y in range(h):
            painter.setPen(QColor.fromHsv(int(359 * y / (h - 1)), 255, 255))
            painter.drawLine(0, y, self.width(), y)
        y = self.hue * (h - 1) / 359.0
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawRect(QRectF(0.5, y - 2, self.width() - 1, 4))
        painter.end()

    def _at(self, y: float) -> None:
        self.hue = max(0, min(359, int(y * 359 / (self.height() - 1))))
        self.update()
        self.changed.emit(self.hue)

    def mousePressEvent(self, event) -> None:
        self._at(event.position().y())

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.LeftButton:
            self._at(event.position().y())


class MoreColors(QWidget):
    """Revu's More Colors, opened in the picker by its ▾: a colour made by
    hue, saturation and brightness or typed as #RRGGBB, then Add."""

    added = Signal(str)

    def __init__(self, current: str, ink: str):
        from PySide6.QtWidgets import QLineEdit, QPushButton, QSpinBox
        super().__init__()
        colour = QColor(current or "#000000")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(4)
        self.spectrum = _Spectrum(colour)
        self.hues = _HueStrip(colour.hsvHue())
        top.addWidget(self.spectrum)
        top.addWidget(self.hues)
        layout.addLayout(top)
        row = QHBoxLayout()
        row.setSpacing(4)
        self.sample = QLabelSwatch()
        row.addWidget(self.sample)
        self.hex = QLineEdit()
        self.hex.setMaxLength(7)
        self.hex.setFixedWidth(70)
        self.hex.setStyleSheet("QLineEdit { padding: 1px 3px; }")
        self.hex.setToolTip("The colour as #RRGGBB")
        row.addWidget(self.hex)
        self.rgb = []
        for tip in ("Red", "Green", "Blue"):
            box = QSpinBox()
            box.setRange(0, 255)
            box.setToolTip(tip)
            box.setButtonSymbols(QSpinBox.NoButtons)
            box.setFixedWidth(40)
            box.setAlignment(Qt.AlignRight)
            box.setStyleSheet("QSpinBox { padding: 1px 3px; }")
            self.rgb.append(box)
            row.addWidget(box)
        layout.addLayout(row)
        self.add = QPushButton("Add")
        self.add.setToolTip("Use this colour, and keep it in the custom colours")
        self.add.clicked.connect(lambda: self.added.emit(self.spectrum.colour().name()))
        layout.addWidget(self.add, 0, Qt.AlignRight)
        self.spectrum.changed.connect(self._show)
        self.hues.changed.connect(self.spectrum.set_hue)
        self.hex.editingFinished.connect(self._typed_hex)
        for box in self.rgb:
            box.valueChanged.connect(self._typed_rgb)
        self._show(colour)

    def _show(self, colour: QColor) -> None:
        self._showing = True
        self.sample.set(colour.name())
        self.hex.setText(colour.name().upper())
        for box, value in zip(self.rgb, (colour.red(), colour.green(), colour.blue())):
            box.setValue(value)
        self._showing = False

    def _typed_hex(self) -> None:
        colour = QColor(self.hex.text().strip())
        if colour.isValid():
            self._set(colour)

    def _typed_rgb(self, _v=None) -> None:
        if getattr(self, "_showing", False):
            return
        self._set(QColor(*(box.value() for box in self.rgb)))

    def _set(self, colour: QColor) -> None:
        self.spectrum.set_colour(colour)
        if colour.hsvHue() >= 0:
            self.hues.hue = colour.hsvHue()
            self.hues.update()
        self._show(colour)


class QLabelSwatch(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(22, 22)
        self.colour = QColor("#000000")

    def set(self, colour: str) -> None:
        self.colour = QColor(colour)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.colour)
        painter.setPen(QColor(0, 0, 0, 90))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.end()


class _Dropper(QWidget):
    """The screen, held still, with a loupe; a click takes its colour."""

    def __init__(self, shot: QPixmap, geometry: QRect):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        # Above everything, a modal dialog included: Color Processing is one,
        # and under it the screen held still took no clicks, so its loop
        # never ended and the application hung (the user, 2026-10-14).
        self.setWindowModality(Qt.ApplicationModal)
        self.shot = shot.toImage()
        self.pixmap = shot
        self.ratio = shot.devicePixelRatio() or 1.0
        self.setGeometry(geometry)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)
        self.result: Optional[str] = None
        self.at = self.mapFromGlobal(QCursor.pos())
        self.loop = QEventLoop()

    def colour_at(self, point: QPoint) -> QColor:
        x = int(point.x() * self.ratio)
        y = int(point.y() * self.ratio)
        x = max(0, min(self.shot.width() - 1, x))
        y = max(0, min(self.shot.height() - 1, y))
        return self.shot.pixelColor(x, y)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.pixmap)
        at = self.at
        colour = self.colour_at(at)
        # the loupe: 11 x 11 pixels at 10 x, beside the pointer
        size = 110
        box = QRect(at.x() + 18, at.y() + 18, size, size)
        if box.right() > self.width():
            box.moveRight(at.x() - 18)
        if box.bottom() > self.height() - 26:
            box.moveBottom(at.y() - 18)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        src = QRectF((at.x() - 5) * self.ratio, (at.y() - 5) * self.ratio, 11 * self.ratio, 11 * self.ratio)
        painter.drawPixmap(QRectF(box), self.pixmap, src)
        painter.setPen(QPen(QColor("#000000"), 1))
        painter.drawRect(box)
        cell = size / 11.0
        painter.setPen(QPen(QColor("#ffffff"), 1))
        painter.drawRect(QRectF(box.left() + 5 * cell, box.top() + 5 * cell, cell, cell))
        label = QRect(box.left(), box.bottom() + 2, size, 20)
        painter.fillRect(label, QColor("#2b2d30"))
        painter.fillRect(QRect(label.left() + 3, label.top() + 3, 14, 14), colour)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(label.adjusted(22, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, colour.name().upper())
        painter.end()

    def mouseMoveEvent(self, event) -> None:
        self.at = event.position().toPoint()
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.result = self.colour_at(event.position().toPoint()).name()
        self.close()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.result = self.colour_at(self.at).name()
            self.close()

    def closeEvent(self, event) -> None:
        super().closeEvent(event)
        self.loop.quit()


def pick_from_screen() -> Optional[str]:
    """The eyedropper: a colour from anywhere on the screen, or None."""
    if ANSWERS:
        return ANSWERS.pop(0)
    screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
    if screen is None:
        return None
    shot = screen.grabWindow(0)
    if shot.isNull() or _blank(shot):
        # Some systems will not hand over the screen (Wayland, a locked-down
        # desktop): the application's own windows, where they are, then —
        # every colour in the drawing at least.
        shot = _our_windows(screen)
        if shot is None:
            return None
    dropper = _Dropper(shot, screen.geometry())
    dropper.show()
    dropper.raise_()
    dropper.activateWindow()
    dropper.grabKeyboard()
    dropper.grabMouse()
    try:
        dropper.loop.exec()
    finally:
        dropper.releaseMouse()
        dropper.releaseKeyboard()
    result = dropper.result
    dropper.deleteLater()
    return result


def _blank(shot: QPixmap) -> bool:
    """A grab the system refused comes back one flat colour."""
    image = shot.toImage().scaled(16, 16)
    first = image.pixel(0, 0)
    return all(image.pixel(x, y) == first for x in range(16) for y in range(16))


def _our_windows(screen) -> Optional[QPixmap]:
    """The screen as far as this application can see it: its own visible
    windows drawn where they stand, on black."""
    from PySide6.QtWidgets import QApplication
    area = screen.geometry()
    canvas = QPixmap(area.size())
    canvas.fill(Qt.black)
    painter = QPainter(canvas)
    drawn = False
    for window in QApplication.topLevelWidgets():
        if not window.isVisible() or isinstance(window, _Dropper):
            continue
        frame = window.frameGeometry()
        if not frame.intersects(area):
            continue
        picture = window.grab()
        if picture.isNull():
            continue
        top_left = window.mapToGlobal(QPoint(0, 0)) - area.topLeft()
        painter.drawPixmap(top_left, picture)
        drawn = True
    painter.end()
    return canvas if drawn else None


class FoundPopup(QFrame):
    """Revu's Source Color list in Modify Colors: only the colours the page
    (or snapshot) sets, eight to a row, and the eyedropper to take one from
    the drawing itself."""

    closed = Signal()

    def __init__(self, colours: list, current: Optional[str], parent=None):
        super().__init__(parent, Qt.Popup)
        self.setObjectName("colourPopup")
        self.result: Optional[str] = None
        t = _theme()
        self.setStyleSheet(
            f"QFrame#colourPopup {{ background: {t['bg']}; border: 1px solid {t['edge']}; }}"
            f"QToolButton {{ background: transparent; border: 1px solid {t['slot_edge']}; }}"
            f"QToolButton:hover {{ border: 1px solid {t['hover']}; }}"
            f"QToolButton:checked {{ border: 2px solid {t['hover']}; }}"
            f"QToolButton#plain {{ border: none; }}")
        grid = QGridLayout(self)
        grid.setContentsMargins(6, 6, 6, 6)
        grid.setSpacing(3)
        self.buttons = {}
        entries = list(colours) + ["dropper"]
        for k, colour in enumerate(entries):
            button = QToolButton()
            button.setFixedSize(SWATCH + 2, SWATCH + 2)
            if colour == "dropper":
                button.setObjectName("plain")
                button.setIcon(eyedropper_icon(t["ink"]))
                button.setIconSize(QSize(SWATCH - 2, SWATCH - 2))
                button.setToolTip("Eyedropper: take the colour from the drawing")
                button.clicked.connect(self._eyedropper)
                self.dropper = button
            else:
                button.setIcon(swatch_icon(colour, SWATCH - 4))
                button.setIconSize(QSize(SWATCH - 4, SWATCH - 4))
                button.setToolTip(colour.upper())
                button.setCheckable(True)
                button.setChecked((current or "").lower() == colour.lower())
                button.clicked.connect(lambda _c=False, value=colour: self._take(value))
                self.buttons[colour.lower()] = button
            grid.addWidget(button, k // 8, k % 8)

    def _take(self, colour: str) -> None:
        self.result = colour.lower()
        self.close()

    def _eyedropper(self) -> None:
        self._stepping_out = True
        self.hide()
        self._stepping_out = False
        got = pick_from_screen()
        if got is not None:
            self.result = got
        self.close()

    def closeEvent(self, event) -> None:
        super().closeEvent(event)
        if not getattr(self, "_stepping_out", False):
            self.closed.emit()


def choose_found(anchor, colours: list, current: Optional[str] = None) -> Optional[str]:
    """One of *colours* (or a colour taken with the eyedropper), or None."""
    if ANSWERS:
        return ANSWERS.pop(0)
    popup = FoundPopup(colours, current, anchor if isinstance(anchor, QWidget) else None)
    ColourPopup.place(popup, anchor)
    loop = QEventLoop()
    popup.closed.connect(loop.quit)
    popup.show()
    loop.exec()
    result = popup.result
    popup.deleteLater()
    return result
