"""A cell's drop-down list, as Excel's (Data Validation ▸ List).

It was a menu, with a menu's margins, icon column and hover (the user,
2026-10-24: "drop down in sheet does not look like in excel"). Excel's is a
plain list box under the cell: as wide as the cell or its widest choice,
eight rows and then a scroll bar, the cell's own value picked out, in the
sheet's font; a click or Enter puts the choice in, Esc puts it away, a
letter goes to the next choice that starts with it.
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QFont, QFontMetrics, QKeyEvent
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem

ROWS = 8                 # Excel shows eight, then scrolls


class ListPopup(QListWidget):
    """The list, popped up under a cell; *on_pick(text)* when one is chosen."""

    def __init__(self, parent, choices: list, current: str, font: QFont,
                 on_pick: Callable[[str], None]):
        super().__init__(parent)
        self.setObjectName("cellList")
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.on_pick = on_pick
        self.picked: Optional[str] = None
        self.setFont(font)
        self.setUniformItemSizes(True)
        self.setMouseTracking(True)              # the row under the pointer is picked out
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setStyleSheet(
            "QListWidget#cellList{background:#ffffff;color:#000000;border:1px solid #7a7a7a;"
            "outline:0;padding:0;}"
            "QListWidget#cellList::item{padding:0 3px;border:0;}"
            "QListWidget#cellList::item:selected{background:#0078d7;color:#ffffff;}")
        for text in choices:
            QListWidgetItem(text, self)
        match = next((i for i, t in enumerate(choices) if t == current), -1)
        self.setCurrentRow(match if match >= 0 else 0)
        self.itemClicked.connect(lambda item: self._pick(item.text()))
        self.itemEntered.connect(lambda item: self.setCurrentItem(item))

    # -- what it shows ----------------------------------------------------------------------
    def row_height(self) -> int:
        return QFontMetrics(self.font()).height() + 2

    def fit(self, cell_width: int) -> None:
        """As wide as the cell or its widest choice; up to ROWS rows high."""
        metrics = QFontMetrics(self.font())
        widest = max([metrics.horizontalAdvance(self.item(i).text())
                      for i in range(self.count())] + [0]) + 10
        rows = min(ROWS, max(1, self.count()))
        bar = self.verticalScrollBar().sizeHint().width() if self.count() > ROWS else 0
        self.setFixedSize(max(cell_width, widest + bar), rows * self.row_height() + 2)
        for i in range(self.count()):
            self.item(i).setSizeHint(QSize(0, self.row_height()))

    def show_at(self, below_left: QPoint, cell_width: int) -> None:
        """Under the cell, its left edge on the cell's (above it when the
        screen ends first)."""
        self.fit(cell_width)
        screen = self.screen().availableGeometry() if self.screen() is not None else None
        at = QPoint(below_left)
        if screen is not None and at.y() + self.height() > screen.bottom():
            at.setY(max(screen.top(), at.y() - self.height() - self.row_height()))
        if screen is not None and at.x() + self.width() > screen.right():
            at.setX(max(screen.left(), screen.right() - self.width()))
        self.move(at)
        self.show()
        self.setFocus(Qt.PopupFocusReason)
        self.scrollToItem(self.currentItem(), QAbstractItemView.PositionAtCenter)

    def choices(self) -> list:
        return [self.item(i).text() for i in range(self.count())]

    # -- choosing ---------------------------------------------------------------------------
    def pick(self, text: str) -> None:
        """Choose *text* (as a click on it does)."""
        self._pick(text)

    def _pick(self, text: str) -> None:
        self.picked = text
        self.close()
        self.on_pick(text)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
            item = self.currentItem()
            if item is not None:
                self._pick(item.text())
            else:
                self.close()
            return
        if key == Qt.Key_Escape:
            self.close()
            return
        text = event.text()
        if text and text.isprintable() and not event.modifiers() & (Qt.ControlModifier |
                                                                    Qt.AltModifier):
            # the next choice that starts with it, as Excel's list goes
            start = self.currentRow()
            n = self.count()
            for step in range(1, n + 1):
                row = (start + step) % n
                if self.item(row).text().lower().startswith(text.lower()):
                    self.setCurrentRow(row)
                    return
            return
        super().keyPressEvent(event)
