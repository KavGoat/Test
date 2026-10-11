"""Typing a unit into a cell exactly as into an equation (the user's choice,
2026-10-11).

As SMath does while an equation is typed:

* after a number, SMath's black unit box shows where the unit goes;
* the unit part is drawn in SMath's unit blue;
* SMath's own autocomplete list opens under the unit being typed — the same
  entries, order, icons and descriptions (calc/ui/suggest.py), here only the
  units a cell can hold, and the units the document's equations define.

It works in the cell's text box and in the formula bar alike: in an entry
(5 kN, 2.5'kN/m) and in a formula after a number or SMath's apostrophe
(=5 kN*B2, =B2*'kip_s).
"""
from __future__ import annotations

import re
from typing import Optional

from PySide6.QtCore import QCoreApplication, QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QInputMethodEvent, QPainter, QTextCharFormat
from PySide6.QtWidgets import QLineEdit

UNIT_BLUE = QColor("#0000ff")              # WebSMath's unit colour (calc/ui/layout.py)

_NUMBER = r"[+-]?(?:\d[\d,]*\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"
_ENTRY = re.compile(rf"^(\s*{_NUMBER})(\s*)(.*?)\s*$", re.S)
_BARE = re.compile(rf"^\s*{_NUMBER}\s*$")
_UNIT_CHARS = r"[A-Za-zµμΩ°%'_][\wµμΩ°%']*"
# in a formula: a number then a unit, or SMath's apostrophe then a unit
_IN_FORMULA = re.compile(
    rf"(?:(?<![\w.$]){_NUMBER}\s*|')({_UNIT_CHARS}(?:\s*[*/·^]\s*(?:{_UNIT_CHARS}|-?[\d.]+))*)")


def _is_entry(text: str) -> bool:
    return not text.startswith("=") and not text.startswith("'")


def unit_spans(text: str) -> list:
    """(start, end) of each unit in *text*, to be drawn in unit blue."""
    if _is_entry(text):
        m = _ENTRY.match(text)
        if m is None or not m.group(3) or not re.match(r"['A-Za-zµμΩ°%]", m.group(3)):
            return []
        return [(m.start(3), m.end(3))]
    if not text.startswith("="):
        return []
    from ..sheet.values import is_unit_text
    from .formulahelp import in_string
    out = []
    for m in _IN_FORMULA.finditer(text):
        if in_string(text, m.start(1)):
            continue
        start = m.start(1) - (1 if text[m.start(1) - 1] == "'" else 0)
        # the unit goes on through *, / and ^ only while what follows is a
        # unit too: 5 kN*m is a unit, 5 kN*B2 is a unit times a cell
        end = m.start(1)
        for piece in re.finditer(r"\s*[*/·^]?\s*(?:[^\s*/·^]+)", m.group(1)):
            word = piece.group(0).strip().lstrip("*/·^").strip()
            if end > m.start(1) and not (is_unit_text(word, custom=True)
                                         or re.fullmatch(r"-?[\d.]+", word)):
                break
            end = m.start(1) + piece.end()
        out.append((start, end))
    return out


def box_at(text: str) -> Optional[int]:
    """After a number alone, where SMath's black unit box goes (its index)."""
    if _is_entry(text) and _BARE.match(text):
        return len(text.rstrip())
    return None


def unit_word(text: str, caret: int) -> Optional[tuple]:
    """(start, word) of the unit being typed at *caret*, or None."""
    before = text[:caret]
    m = re.search(r"[A-Za-zµμΩ°%_][\wµμΩ°%]*$", before)
    if m is None:
        return None
    after = text[caret:caret + 1]
    if after and (after.isalnum() or after in "_"):
        return None
    start = m.start()
    for a, b in unit_spans(text):
        if a <= start < b or (a == start and b >= caret):
            return start, m.group(0)
    return None


class UnitText(QLineEdit):
    """A text box drawing units as SMath does: blue, with the black unit box
    after a number alone (the cell's text box and the formula bar)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._colouring = False
        self.on_white = False          # the cell's own box: SMath's black and blue
        self.textChanged.connect(lambda _t: self.colour_units())

    def _dark(self) -> bool:
        return not self.on_white and self.palette().base().color().lightness() < 128

    def unit_colour(self) -> QColor:
        """SMath's unit blue; a lighter blue on a dark theme's box."""
        return QColor("#7fb2ff") if self._dark() else UNIT_BLUE

    def colour_units(self) -> None:
        """The units in blue (QLineEdit's own text formats, set as an input
        method sets them: they stay with the text, under the selection)."""
        if self._colouring:
            return
        self._colouring = True
        try:
            caret = self.cursorPosition()
            fmt = QTextCharFormat()
            fmt.setForeground(self.unit_colour())
            attrs = [QInputMethodEvent.Attribute(QInputMethodEvent.TextFormat, a - caret, b - a, fmt)
                     for a, b in unit_spans(self.text())]
            QCoreApplication.sendEvent(self, QInputMethodEvent("", attrs))
        finally:
            self._colouring = False

    def x_of(self, index: int) -> float:
        """Where character *index* starts, in this box's pixels."""
        fm = QFontMetricsF(self.font())
        text = self.text()
        caret = self.cursorPosition()
        return self.cursorRect().center().x() - fm.horizontalAdvance(text[:caret]) + \
            fm.horizontalAdvance(text[:index])

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        at = box_at(self.text())
        if at is None:
            return
        # SMath's empty unit box: its "H" glyph box (5 x 7 px at 10 pt, 3 px
        # left bearing), centred on the middle of the line's = sign
        fm = QFontMetricsF(self.font())
        px = fm.height() / 1.15
        w, h = px * 0.376, px * 0.526
        left = self.x_of(at) + fm.horizontalAdvance(" ") * 0.5 + px * 0.225
        baseline = self.cursorRect().center().y() + (fm.ascent() - fm.descent()) / 2
        middle = baseline - fm.xHeight() * 0.5
        painter = QPainter(self)
        colour = self.palette().text().color() if self._dark() else QColor("#000000")
        painter.fillRect(QRectF(left, middle - h / 2, w, h), colour)
        painter.end()


class UnitList:
    """SMath's autocomplete list for the unit being typed in a cell."""

    def __init__(self, tables):
        from ..calc.ui.suggest import SuggestionList
        self.tables = tables
        self.list = SuggestionList(tables.view)
        self.list.hide()
        self.list.itemClicked.connect(lambda _i: self.choose())
        self.widget = None
        self.start = 0
        self._taken = None             # (text, caret) just after an entry was taken

    def _custom(self) -> dict:
        """The units the document's equations define: name -> description."""
        window = getattr(self.tables.view, "window", None)
        document = getattr(window, "document", None)
        if document is None:
            return {}
        from ..calc.docsheet import sheet_for
        from ..sheet.docbook import book_for
        from ..sheet.values import UNITS
        book = book_for(document)
        out = {}
        for name in sheet_for(document).worksheet.index.vars:
            if name not in UNITS and book._custom_unit(name) is not None:
                out[name] = f"<strong>{name}</strong> - unit defined on this worksheet"
        return out

    def entries(self, word: str) -> list:
        from ..calc.ui.suggest import SMATH_LABEL, Suggestion, suggestion_entries
        from ..sheet.values import is_unit_text
        custom = self._custom()
        back = {v: k for k, v in SMATH_LABEL.items()}
        out = []
        for e in suggestion_entries(word, set(custom)):
            if e.kind == "unit":
                name = back.get(e.name[1:], e.name[1:])
                if is_unit_text(name):
                    out.append(e)
            elif e.origin == 3 and e.text in custom:
                out.append(Suggestion(e.text, e.text, "unit", 3, 0, custom[e.text]))
        return out

    def update(self, widget) -> bool:
        """After a key or a caret move: the list for the unit being typed,
        if one is; True when it is showing."""
        from ..calc.ui.suggest import selected_index
        self.widget = widget
        text, caret = widget.text(), widget.cursorPosition()
        if (text, caret) == self._taken:
            self.hide()                # an entry was just taken: closed until more is typed
            return False
        self._taken = None
        got = unit_word(text, caret) if widget.isVisible() else None
        found = self.entries(got[1]) if got is not None else []
        if not found:
            self.hide()
            return False
        self.start, word = got
        s = self.list
        s.word = word
        s.fill(found, selected_index(found, word))
        rows = min(s.count(), 8)
        scrolls = s.count() > rows
        s.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn if scrolls else Qt.ScrollBarAlwaysOff)
        row = max(s.sizeHintForRow(0), s.fontMetrics().height() + 2)
        bar = s.verticalScrollBar().sizeHint().width() if scrolls else 0
        wide = s.sizeHintForColumn(0) + s.iconSize().width() + bar + 2 * s.frameWidth() + 10
        s.setMaximumHeight(16777215)
        s.setFixedSize(max(90, wide), row * rows + 2 * s.frameWidth() + 2)
        x = widget.x_of(self.start) if isinstance(widget, UnitText) else widget.cursorRect().left()
        s.move(widget.mapToGlobal(QPoint(int(x) - 2, widget.height() + 1)))
        s.show()
        s.raise_()
        s.show_tooltip()
        return True

    def key(self, event) -> bool:
        """SMath's keys on the open list: Esc closes it, Tab takes the entry
        picked, Enter too once the list has been moved through, Up/Down move."""
        s = self.list
        if not s.isVisible():
            return False
        key = event.key()
        if key == Qt.Key_Escape:
            self.hide()
            return True
        if key == Qt.Key_Tab or (key in (Qt.Key_Return, Qt.Key_Enter) and s.activated):
            if s.currentRow() >= 0:
                self.choose()
                return True
            return False
        if key in (Qt.Key_Down, Qt.Key_Up):
            row = s.currentRow()
            if row < 0:
                row = 0 if key == Qt.Key_Down else s.count() - 1
            else:
                row = max(0, min(s.count() - 1, row + (1 if key == Qt.Key_Down else -1)))
            s.activated = True
            s.setCurrentRow(row)
            return True
        return False

    def choose(self) -> None:
        from ..calc.ui.suggest import SMATH_LABEL
        it = self.list.currentItem()
        widget = self.widget
        if it is None or widget is None:
            return
        e = it.data(Qt.UserRole)
        if e.origin == 3:
            name = e.text
        else:
            back = {v: k for k, v in SMATH_LABEL.items()}
            name = back.get(e.name[1:], e.name[1:])
        text, caret = widget.text(), widget.cursorPosition()
        start = self.start
        if e.origin == 3 and _is_entry(text) and text[start - 1:start] != "'":
            name = "'" + name                     # a custom unit is written SMath's way
        new = text[:start] + name + text[caret:]
        self.hide()
        self._taken = (new, start + len(name))
        self.tables._formula_from_help(widget, new, start + len(name))

    def hide(self) -> None:
        self.list.hide()
        self.list.tooltip.hide()

    def visible(self) -> bool:
        return self.list.isVisible()
