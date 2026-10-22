"""SMath's unit box, for cells (the user's choice, 2026-10-11).

In an equation, the result's unit is typed into the small black box after
it (WebSMath draws it); a cell gets the same: after the value in the formula
bar, empty it is SMath's black placeholder, and a unit typed into it — one of
CalcForge's, or a custom unit the document's equations define (kip_s :=
5'kN) — shows the selected cells' quantities in that unit. Blank: as typed.
As SMath's, the placeholder stays while the unit is empty or unfinished
(kN/), nothing is said while it is typed, and a finished unit that is
refused is drawn red, with why (cellunits.UnitSlot).
"""
from __future__ import annotations

from PySide6.QtCore import QStringListModel, Qt
from PySide6.QtWidgets import QCompleter, QLineEdit

from .cellunits import UnitSlot


class UnitBox(UnitSlot, QLineEdit):
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
        self._init_slot()

    def focusInEvent(self, event) -> None:
        self._model.setStringList(unit_names(self.window))
        super().focusInEvent(event)



class UnitField(UnitSlot, QLineEdit):
    """A unit typed into a dialog (Format Cells' "Show quantities in"), as
    into SMath's unit box: the black placeholder while empty or unfinished,
    and red, with why, only once finished (flag() is given the reason)."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._init_slot()


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
