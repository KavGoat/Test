"""Editing a markup's words where they are, rather than in a box somewhere else.

A dialog makes you read the text in one place and the drawing in another, and
gives back no sense of whether what you typed fits. This puts a real editor over
the markup, the size the markup is, at the zoom you are looking at.
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QKeyEvent
from PySide6.QtWidgets import QGraphicsProxyWidget, QPlainTextEdit

EDITOR_STYLE = """
QPlainTextEdit {
    background: #ffffff;
    border: 1px solid #1a73e8;
    color: #10233d;
    selection-background-color: #cddffb;
}
"""

MIN_POINT_SIZE = 6.0
DEFAULT_POINT_SIZE = 11.0


class _Editor(QPlainTextEdit):
    """The text box itself. Escape abandons, Ctrl+Enter keeps."""

    def __init__(self, text: str, commit: Callable[[], None],
                 cancel: Callable[[], None]):
        super().__init__(text)
        self._commit = commit
        self._cancel = cancel
        self.setStyleSheet(EDITOR_STYLE)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameStyle(0)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self._cancel()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and \
                event.modifiers() & Qt.ControlModifier:
            self._commit()      # Enter alone is a new line: this is a text box
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._commit()


class InlineText(QGraphicsProxyWidget):
    """An editor sitting on the page, over the markup it is editing."""

    def __init__(self, text: str, box: QRectF, point_size: float,
                 on_done: Callable[[Optional[str]], None]):
        super().__init__()
        self._on_done = on_done
        self._finished = False
        editor = _Editor(text, self._commit, self._cancel)
        font = editor.font()
        font.setPointSizeF(max(point_size, MIN_POINT_SIZE))
        editor.setFont(font)
        self.setWidget(editor)
        self.setGeometry(box)
        self.setZValue(60)
        editor.selectAll()

    def take_focus(self) -> None:
        self.setFocus(Qt.OtherFocusReason)
        self.widget().setFocus(Qt.OtherFocusReason)

    def _commit(self) -> None:
        self._finish(self.widget().toPlainText())

    def _cancel(self) -> None:
        self._finish(None)

    def _finish(self, text: Optional[str]) -> None:
        if self._finished:      # losing focus while closing must not fire twice
            return
        self._finished = True
        self._on_done(text)


def editor_colour() -> QColor:
    return QColor("#1a73e8")
