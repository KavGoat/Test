"""SMath's unit box, for cells (the user's choice, 2026-10-11).

In an equation, the result's unit is typed into the small black box after
it (WebSMath draws it); a cell gets the same: after the value in the formula
bar, empty it is SMath's black placeholder, and a unit typed into it — one of
CalcForge's, or a custom unit the document's equations define (kip_s :=
5'kN) — shows the selected cells' quantities in that unit. Blank: as typed.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, QStringListModel, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QCompleter, QLineEdit


class UnitBox(QLineEdit):
    def __init__(self, window=None):
        super().__init__()
        self.window = window
        self.setObjectName("unitBox")
        self.setFixedWidth(84)
        self.setToolTip("Unit (SMath's unit box): the selected cells' quantities are shown "
                        "in it — kN, kN/m, MPa, or a custom unit the equations define. "
                        "Blank: as typed")
        self.setAccessibleName("Unit")
        self._model = QStringListModel(self)
        completer = QCompleter(self._model, self)
        completer.setCaseSensitivity(Qt.CaseSensitive)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.setCompleter(completer)

    def focusInEvent(self, event) -> None:
        self._model.setStringList(unit_names(self.window))
        super().focusInEvent(event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.text() or self.hasFocus():
            return
        # empty: SMath's placeholder, a small black box where the unit goes
        painter = QPainter(self)
        h = max(6.0, self.height() * 0.42)
        box = QRectF(8, (self.height() - h) / 2, h * 0.62, h)
        # black on a light theme, as SMath's; the text colour on a dark one
        colour = self.palette().text().color() if self.isEnabled() else QColor("#9a9a9a")
        painter.fillRect(box, colour)
        painter.end()


def unit_names(window=None) -> list:
    """The units offered while typing: CalcForge's, then the document's own."""
    from ..sheet.values import UNITS

    names = sorted(UNITS, key=str.lower)
    document = getattr(window, "document", None)
    if document is None:
        return names
    from ..calc.docsheet import sheet_for
    from ..sheet.docbook import book_for
    book = book_for(document)
    custom = []
    for name in sheet_for(document).worksheet.index.vars:
        if name not in UNITS and book._custom_unit(name) is not None:
            custom.append(name)
    return sorted(custom, key=str.lower) + names
