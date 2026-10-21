"""The canvas drawn with the graphics card, repainting only what changed.

A canvas drawn with OpenGL (Preferences ▸ Draw with the graphics card, on by
default) was drawn whole every time anything on it changed: Qt hands a
texture-backed widget a paint of all of itself, so the leader of a call-out
following the pointer, a key typed into a text box or a markup picked out
had the page, its drawing and every markup on screen drawn again — on the
user's machine, the lag of placing a call-out (2026-10-21).

Here the surface keeps what it drew (its frame buffer is preserved between
paints) and remembers what it has been asked to draw again since: every
update asked of it, and every change the scene reports. The next paint draws
only that, clipped to it, and what was drawn before stays. Anything it cannot
account for — a scroll, a zoom, a resize, a paint nobody asked it for, or a
change over most of the canvas — is drawn whole, as before.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QRect, Qt
from PySide6.QtGui import QPaintEvent, QRegion, QTransform
from PySide6.QtOpenGLWidgets import QOpenGLWidget

#: a change over more of the canvas than this is drawn whole: as quick, and
#: there is nothing to be careful about
MOST_OF_IT = 0.6
#: and so are more pieces of change than this in one frame
MOST_PIECES = 200


def _area(region: QRegion) -> int:
    return sum(rect.width() * rect.height() for rect in region)


class CardSurface(QOpenGLWidget):
    """The canvas's OpenGL surface, which keeps what it drew."""

    def __init__(self) -> None:
        super().__init__()
        # what was drawn stays in the frame buffer between paints...
        self.setUpdateBehavior(QOpenGLWidget.PartialUpdate)
        # ...and nothing wipes it first: the canvas paints every pixel of
        # what it repaints itself (the desk, the pages)
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        #: what has been asked to be drawn again since the last paint (in the
        #: surface's own pixels); None: all of it
        self._asked: Optional[QRegion] = None
        #: what the last paint was drawn for: (transform, size, pixel ratio,
        #: scene) — any of them different, and all of it is drawn
        self._drawn_for = None

    # -- what is asked of it -----------------------------------------------------
    def update(self, *args) -> None:                   # noqa: D102 (Qt's)
        self.ask(args)
        super().update(*args)

    def repaint(self, *args) -> None:                  # noqa: D102 (Qt's)
        self.ask(args)
        super().repaint(*args)

    def ask(self, args) -> None:
        """Note an update(...) or repaint(...) with these arguments."""
        if not args:
            self.ask_all()
            return
        if len(args) == 4:
            self.ask_for(QRegion(QRect(*(int(value) for value in args))))
            return
        what = args[0]
        if isinstance(what, QRegion):
            self.ask_for(what)
        elif isinstance(what, QRect):
            self.ask_for(QRegion(what))
        else:
            try:
                self.ask_for(QRegion(what.toAlignedRect()))
            except AttributeError:
                self.ask_all()

    def ask_for(self, region: QRegion) -> None:
        if self._asked is not None:
            if self._asked.rectCount() > MOST_PIECES:
                self._asked = None
            else:
                self._asked = self._asked.united(region)

    def ask_all(self) -> None:
        self._asked = None

    # -- the widget's own reasons to draw it all ----------------------------------
    def resizeEvent(self, event) -> None:              # noqa: D102 (Qt's)
        self.ask_all()
        super().resizeEvent(event)

    def showEvent(self, event) -> None:                # noqa: D102 (Qt's)
        self.ask_all()
        super().showEvent(event)

    def changeEvent(self, event) -> None:              # noqa: D102 (Qt's)
        if event.type() in (QEvent.PaletteChange, QEvent.StyleChange,
                            QEvent.FontChange, QEvent.EnabledChange):
            self.ask_all()
        super().changeEvent(event)

    # -- the paint ---------------------------------------------------------------
    def to_draw(self, transform: QTransform, scene, whole: bool = False) -> Optional[QRegion]:
        """What this paint has to draw — a region of the surface, or None
        for all of it — and forget it, as it is about to be drawn."""
        asked, self._asked = self._asked, QRegion()
        state = (QTransform(transform), self.size(), self.devicePixelRatioF(), id(scene))
        before, self._drawn_for = self._drawn_for, state
        if whole or asked is None or asked.isEmpty() or before != state:
            return None
        inside = asked.intersected(QRegion(self.rect()))
        if inside.isEmpty():
            return None
        if _area(inside) > MOST_OF_IT * self.width() * self.height():
            return None
        return inside

    def paint_only(self, region: QRegion, paint) -> None:
        """Run *paint(event)* for *region* alone, clipped to it.

        A texture-backed widget is not clipped to what is repainted, as a
        plain one is: whatever crosses into the region would be drawn whole,
        over what is round it. So the paint engine is told the clip itself
        — in device pixels, which on a scaled screen are not the widget's."""
        engine = self.paintEngine()
        ratio = self.devicePixelRatioF()
        if engine is None:
            paint(QPaintEvent(QRegion(self.rect())))
            return
        engine.setSystemClip(QTransform.fromScale(ratio, ratio).map(region))
        try:
            paint(QPaintEvent(region))
        finally:
            engine.setSystemClip(QRegion())
