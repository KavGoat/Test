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
from PySide6.QtGui import (QColor, QFont, QFontInfo, QFontMetricsF, QInputMethodEvent,
                           QPainter, QTextCharFormat)
from PySide6.QtWidgets import QLineEdit

UNIT_BLUE = QColor("#0000ff")              # WebSMath's unit colour (calc/ui/layout.py)

_NUMBER = r"[+-]?(?:\d[\d,]*\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"
_ENTRY = re.compile(rf"^(\s*{_NUMBER})(\s*)(.*?)\s*$", re.S)
_BARE = re.compile(rf"^\s*{_NUMBER}\s*$")
_UNIT_CHARS = r"[A-Za-zµμΩ°%'_][\wµμΩ°%']*"
# in a formula: a number then a unit, or SMath's apostrophe then a unit
_IN_FORMULA = re.compile(
    rf"(?:(?<![\w.$]){_NUMBER}\s*|')({_UNIT_CHARS}(?:\s*[*/·^]\s*(?:{_UNIT_CHARS}|-?[\d.]+))*)")


def output_unit_refusal(text: str, value) -> Optional[str]:
    """Why *text* can't be the unit a cell holding *value* is shown in, or
    None when it can — said as SMath says it of the unit typed into an
    equation's unit box. Any unit expression is taken: of the value's
    dimension it converts, of another SMath fills in the units still needed
    before it (sheet/numfmt.in_unit_box; the user, 2026-10-21: "it should
    handle it like SMath"). Refused, as SMath refuses them: a name that is
    no unit ("frobs - not defined."), a unit written wrongly ("Syntax is
    incorrect.") and a temperature with an offset (°C) on a quantity of
    another kind ("Units don't match.")."""
    from ..calc.engine.errors import MESSAGES
    from ..sheet.values import _UNIT_TOKEN, Qty, UNITS, UnitTextError, unit_parts
    try:
        _f, dims, offset = unit_parts(text)
    except UnitTextError:
        for m in _UNIT_TOKEN.finditer(text):
            name = (m.group(5) or "").lstrip("'")
            if not name or name in UNITS:
                continue
            try:
                unit_parts(name)
                continue                  # one of the document's own units
            except UnitTextError:
                pass
            why = MESSAGES["not_defined"].format(name)
            # Nm: two units written together; say how to write their product
            for k in range(1, len(name)):
                a, b = name[:k], name[k:]
                if a in UNITS and b in UNITS:
                    return f"{why} For {a} times {b} write {a}*{b} (shown {a}·{b})"
            return why
        return MESSAGES["syntax"]
    if isinstance(value, Qty) and offset and tuple(dims) != tuple(value.dims):
        return MESSAGES["units_mismatch"]
    return None


def say_refusal(view, why: str, box=None) -> None:
    """An output unit refused: why, on the status bar — and under the box it
    was typed in, where the eye is (QA saw a refusal go by unsaid)."""
    view.statusMessage.emit(why)
    if box is not None:
        from PySide6.QtWidgets import QToolTip
        QToolTip.showText(box.mapToGlobal(QPoint(0, box.height())), why, view)


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


_UNFINISHED = "*/^·('"            # a unit ending in one of these waits for more


def box_at(text: str) -> Optional[int]:
    """Where SMath's black unit box goes (its index), or None: after a number
    alone, and where a unit is still to come — after SMath's apostrophe
    (5', =B2*5') or a unit's *, /, ^ (5 kN/), as SMath shows it."""
    end = len(text.rstrip())
    if _is_entry(text):
        if _BARE.match(text):
            return end
        m = _ENTRY.match(text)
        if m is not None and m.group(3) and m.group(3)[-1] in _UNFINISHED and \
                re.match(r"['A-Za-zµμΩ°%]", m.group(3)):
            return end
        return None
    if text.startswith("=") and end and text[end - 1] == "'":
        from .formulahelp import in_string
        before = text[:end - 1].rstrip()
        if before and (before[-1].isdigit() or before[-1] in ").*/") and \
                not in_string(text, end - 1):
            return end
    return None


def unit_slot(text: str) -> Optional[int]:
    """In a box holding only a unit (the unit boxes, Format Cells' field):
    where SMath's black placeholder goes while the unit is empty or still
    unfinished (kN/, kN*, m^), or None once it reads as complete."""
    end = len(text.rstrip())
    if not text.strip():
        return 0
    if text[end - 1] in _UNFINISHED:
        return end
    return None


# A unit as SMath's unit box shows it while it is typed (the user,
# 2026-10-21: "it looks like N^2, not how it should be"): powers raised
# (N², m⁻¹) and products with a dot (kN·m), as the cell and the equations
# draw them; division with the solidus a single line has. What is stored
# stays plain (plain_unit): N^2, kN*m.
_TO_SUPERSCRIPT = str.maketrans("0123456789-−", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁻")
_FROM_SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")
# a whole power: ^2, ^-1, ^(-1) — not one with a point (^0.5 stays as typed)
_POWER = re.compile(r"\^\s*(?:\(\s*([-−]?)\s*(\d+)\s*\)|([-−]?)\s*(\d+)(?![\d.]))")
_RAISED = re.compile(r"[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+(?:\.\d*)?")


def pretty_unit(text: str) -> str:
    """*text* as SMath's unit box shows it: kN*m^-1 is kN·m⁻¹."""
    def raised(m):
        sign, digits = (m.group(1), m.group(2)) if m.group(2) else (m.group(3), m.group(4))
        return (sign + digits).translate(_TO_SUPERSCRIPT)
    return _POWER.sub(raised, text).replace("*", "·")


def plain_unit(text: str) -> str:
    """A unit as shown in a unit box, written plainly: kN·m⁻¹ is kN*m^-1."""
    text = _RAISED.sub(lambda m: "^" + m.group(0).translate(_FROM_SUPERSCRIPT), text)
    return text.replace("·", "*").replace("⋅", "*")


def unit_placeholder(font: QFont, colour: Optional[QColor] = None):
    """SMath's empty slot as the equations draw it (calc/ui/layout.py,
    Layout.placeholder): the "H" of SMath's equation font at *font*'s size,
    centred on the middle of the = sign; an LRect, painted at a baseline."""
    from ..calc.ui.layout import LRect, _equals_middle, _smath_equations_family
    f = QFont(_smath_equations_family())
    if font.pointSizeF() > 0:
        f.setPointSizeF(font.pointSizeF())
    else:
        f.setPixelSize(max(1, font.pixelSize()))
    m = QFontMetricsF(f)
    r = m.tightBoundingRect("H")
    bottom = _equals_middle(font) - r.height() / 2
    return LRect(w=m.horizontalAdvance("H") - 2, asc=bottom + r.height(), desc=max(0.6, -bottom),
                 color=colour, box=(r.left(), r.width(), r.height(), bottom))


def x_of(box: QLineEdit, index: int) -> float:
    """Where character *index* of a text box starts, in its pixels."""
    fm = QFontMetricsF(box.font())
    text = box.text()
    caret = box.cursorPosition()
    return box.cursorRect().center().x() - fm.horizontalAdvance(text[:caret]) + \
        fm.horizontalAdvance(text[:index])


def paint_slot(box: QLineEdit, index: int, colour: QColor) -> QRectF:
    """SMath's black placeholder in text box *box* at character *index*;
    where it was drawn."""
    fm = QFontMetricsF(box.font())
    text = box.text()
    left = x_of(box, index) + 1.0
    if index and (text[index - 1].isdigit() or text[index - 1] == "."):
        left += fm.horizontalAdvance(" ") * 0.5          # 5 ■, as SMath spaces it
    baseline = box.cursorRect().center().y() + (fm.ascent() - fm.descent()) / 2
    slot = unit_placeholder(box.font(), colour)
    painter = QPainter(box)
    slot.paint(painter, left, baseline)
    painter.end()
    lft, w, h, bottom = slot.box
    return QRectF(left + lft, baseline - bottom - h, w, h)


def _error_red() -> str:
    from ..calc.ui.layout import ERROR_RED
    return ERROR_RED.name()


class UnitSlot:
    """What SMath's unit boxes share (the unit box after a cell's result,
    the formula bar's, and Format Cells' "Show quantities in"): empty or
    unfinished, SMath's black placeholder shows where the unit goes, and
    nothing is said while it is typed; a finished unit SMath would refuse
    (output_unit_refusal) is drawn in SMath's error red, with why in its
    tip, until it is typed into again (the user, 2026-10-19: "does not have
    the filler unit like smath — currently says wrong unit"). As it is
    typed, it is written as SMath's box writes it: N^2 is N² (pretty_unit).

    For QLineEdit subclasses: call _init_slot() from __init__ (after any
    style sheet of its own), and paint_unit_slot() at the end of
    paintEvent."""

    _why = None                    # why the finished unit was refused
    _tip = ""                      # the tip it had before
    _own_sheet = ""                # its own style sheet, under the red

    def _init_slot(self) -> None:
        self._own_sheet = self.styleSheet()
        # typed into again, or given another cell's unit: no longer refused
        self.textChanged.connect(lambda _t: self.unflag())
        # shown as SMath's unit box shows it, as it is typed: N^2 is N²
        self.textEdited.connect(self._typed)
        if self.text():
            self.setText(pretty_unit(self.text()))

    def _typed(self, text: str) -> None:
        new = pretty_unit(plain_unit(text))
        if new == text:
            return
        caret = len(pretty_unit(plain_unit(text[:self.cursorPosition()])))
        self.setText(new)
        self.setCursorPosition(min(caret, len(new)))

    def unit_text(self) -> str:
        """The unit typed, written plainly (kN*m^-1), as it is stored."""
        return plain_unit(self.text()).strip()

    def set_unit_text(self, text: Optional[str]) -> None:
        """Show unit *text* (as stored, kN*m^-1) as SMath's box does."""
        self.setText(pretty_unit(text or ""))

    def flag(self, why: str) -> None:
        """The unit as finished is refused: red, and why in its tip."""
        if self._why is None:
            self._tip = self.toolTip()
        self._why = why
        self.setStyleSheet(self._own_sheet + "QLineEdit { color: %s; }" % _error_red())
        self.setToolTip(why)

    def unflag(self) -> None:
        if self._why is None:
            return
        self._why = None
        self.setStyleSheet(self._own_sheet)
        self.setToolTip(self._tip)

    def flagged(self) -> Optional[str]:
        return self._why

    def slot_colour(self) -> QColor:
        """SMath's black; a dark theme's text colour on a dark box."""
        if not self.isEnabled():
            return QColor("#9a9a9a")
        if self.palette().base().color().lightness() >= 128 or "background: white" in self._own_sheet:
            return QColor("#000000")
        return self.palette().text().color()

    def paint_unit_slot(self) -> Optional[QRectF]:
        """SMath's placeholder, if the unit is empty or unfinished."""
        at = unit_slot(self.text())
        if at is None:
            return None
        return paint_slot(self, at, self.slot_colour())


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
        return x_of(self, index)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        at = box_at(self.text())
        if at is None:
            return
        # SMath's empty unit box, drawn as the equations draw theirs
        colour = self.palette().text().color() if self._dark() else QColor("#000000")
        paint_slot(self, at, colour)


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
        refill = word != s.word or found != s.entries()
        s.word = word
        if refill:
            # filled and sized again only when what it lists changes
            s.fill(found, selected_index(found, word))
            rows = min(s.count(), 8)
            scrolls = s.count() > rows
            s.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn if scrolls else Qt.ScrollBarAlwaysOff)
            row = max(s.sizeHintForRow(0), s.fontMetrics().height() + 2)
            bar = s.verticalScrollBar().sizeHint().width() if scrolls else 0
            wide = s.sizeHintForColumn(0) + s.iconSize().width() + bar + 2 * s.frameWidth() + 10
            s.setMaximumHeight(16777215)
            size = (max(90, wide), row * rows + 2 * s.frameWidth() + 2)
            if s.size().toTuple() != size:
                s.setFixedSize(*size)
        x = widget.x_of(self.start) if isinstance(widget, UnitText) else widget.cursorRect().left()
        at = widget.mapToGlobal(QPoint(int(x) - 2, widget.height() + 1))
        # a window of its own: moved, shown and raised only when it must be
        # (each is a call to the window system, slow on Windows)
        moved = s.pos() != at
        if moved:
            s.move(at)
        shown = not s.isVisible()
        if shown:
            s.show()
            s.raise_()
        if refill or moved or shown:
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


class ResultUnit(UnitSlot, QLineEdit):
    """SMath's unit box on a selected cell's result, typed into (the user's
    choice, 2026-10-11): click the black box after a quantity — or its unit,
    once one is set — and type the unit to show it in, with SMath's list of
    units as in an equation's result box. Enter (or leaving it) sets it, Esc
    leaves it as it was, blank goes back to the unit as typed. Empty or
    unfinished, SMath's black placeholder shows in it; a unit refused at
    Enter stays in it in red, with why, to be put right (UnitSlot)."""

    def __init__(self, tables):
        from ..calc.ui.suggest import SuggestionList
        super().__init__(tables.view.viewport())
        self.tables = tables
        self.setObjectName("resultUnit")
        self.setFrame(False)
        self.setStyleSheet(self._SHEET)
        self.ensurePolished()
        self._base_px = QFontInfo(self.font()).pixelSize()   # the window's text box size
        self._init_slot()
        self.textChanged.connect(lambda _t: self._fit())
        self.list = SuggestionList(tables.view)
        self.list.hide()
        self.list.itemClicked.connect(lambda _i: self._take())
        self.textEdited.connect(lambda _t: self._offer())
        self.cell = None
        self._done = True
        self.hide()

    _SHEET = ("QLineEdit { background: white; color: #0000ff; "
              "border: 1px solid #217346; padding: 0px 1px; }")

    def open(self, item, cell, rect) -> None:
        """Over *rect* (of *item*), for cell *cell*."""
        self.cell = (item.uid, cell)
        st = item.sheet.workbook.style_of(item.sheet, *cell)
        view = self.tables.view
        box = view.mapFromScene(item.mapToScene(rect)).boundingRect()
        # the cell's own size at the zoom it is seen at, as the cell's text
        # box has it, so N² and m⁻¹ read as they are typed (the window's
        # style sheet sets every text box's size: this one's follows the zoom)
        scale = abs(view.transform().m11()) + abs(view.transform().m12())
        size = max(self._base_px, int(round((st.size or 11.0) * scale)))
        self.unflag()
        self._own_sheet = self._SHEET + "QLineEdit { font-size: %dpx; }" % size
        self.setStyleSheet(self._own_sheet)
        font = self.font()
        font.setPixelSize(size)
        self.setFont(font)
        self._least = max(48, 4 * size)
        self.setGeometry(box.left() - 1, box.center().y() - self.sizeHint().height() // 2,
                         self._width(pretty_unit(st.unit or "")), self.sizeHint().height())
        self.set_unit_text(st.unit)
        self._done = False
        self.show()
        self.raise_()
        self.setFocus()
        self.selectAll()

    _least = 48

    def _width(self, text: str) -> int:
        return max(self._least, int(self.fontMetrics().horizontalAdvance(text + "WW")))

    def _fit(self) -> None:
        """Wide enough for what is typed, as SMath's box grows with it."""
        if self.isVisible() and self._width(self.text()) != self.width():
            self.resize(self._width(self.text()), self.height())

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        self.paint_unit_slot()

    def _offer(self) -> None:
        from ..calc.ui.suggest import selected_index, unit_box_entries
        word = self.text()[:self.cursorPosition()]
        m = re.search(r"[A-Za-zµμΩ°%_][\wµμΩ°%]*$", word)
        if m is None:
            self.list.hide()
            self.list.tooltip.hide()
            return
        from ..sheet.values import is_unit_text
        found = [e for e in unit_box_entries(m.group(0)) if is_unit_text(e.text)]
        custom = UnitList(self.tables)._custom()
        from ..calc.ui.suggest import Suggestion
        found = [Suggestion(n, n, "unit", 3, 0, d) for n, d in sorted(custom.items())
                 if n.lower().startswith(m.group(0).lower())] + found
        if not found:
            self.list.hide()
            self.list.tooltip.hide()
            return
        self._start = m.start()
        s = self.list
        s.fill(found, selected_index(found, m.group(0)))
        rows = min(s.count(), 8)
        row = max(s.sizeHintForRow(0), s.fontMetrics().height() + 2)
        s.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn if s.count() > rows else Qt.ScrollBarAlwaysOff)
        s.setFixedSize(max(90, s.sizeHintForColumn(0) + 40), row * rows + 4)
        s.move(self.mapToGlobal(QPoint(0, self.height() + 1)))
        s.show()
        s.raise_()
        s.show_tooltip()

    def _take(self) -> None:
        it = self.list.currentItem()
        if it is None:
            return
        e = it.data(Qt.UserRole)
        text, caret = self.text(), self.cursorPosition()
        self.setText(text[:self._start] + e.text + text[caret:])
        self.setCursorPosition(self._start + len(e.text))
        self.list.hide()
        self.list.tooltip.hide()

    def keyPressEvent(self, event) -> None:
        s = self.list
        key = event.key()
        if s.isVisible():
            if key in (Qt.Key_Down, Qt.Key_Up):
                row = s.currentRow()
                row = (0 if key == Qt.Key_Down else s.count() - 1) if row < 0 else \
                    max(0, min(s.count() - 1, row + (1 if key == Qt.Key_Down else -1)))
                s.activated = True
                s.setCurrentRow(row)
                return
            if key == Qt.Key_Tab or (key in (Qt.Key_Return, Qt.Key_Enter) and s.activated):
                self._take()
                return
            if key == Qt.Key_Escape:
                s.hide()
                s.tooltip.hide()
                return
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self.finish(True, leaving=False)
            return
        if key == Qt.Key_Escape:
            self.finish(False)
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        if event.reason() not in (Qt.PopupFocusReason, Qt.ActiveWindowFocusReason):
            self.finish(True)

    def _refusal(self, text: str) -> Optional[str]:
        """Why the finished unit *text* can't be the cell's, or None."""
        item = self.tables.item
        if not text or self.cell is None or item is None or item.uid != self.cell[0]:
            return None
        return output_unit_refusal(text, item.sheet.workbook.value(item.sheet, *self.cell[1]))

    def finish(self, keep: bool, leaving: bool = True) -> None:
        """Enter (*leaving* False), leaving the box, or Esc (*keep* False)."""
        if self._done:
            return
        if keep and not leaving:
            why = self._refusal(self.unit_text())
            if why is not None:
                # as SMath: the unit stays, in red, until it is put right
                # (or Esc), and why is said
                self.list.hide()
                self.list.tooltip.hide()
                self.flag(why)
                say_refusal(self.tables.view, why, self)
                return
        self._done = True
        self.list.hide()
        self.list.tooltip.hide()
        text = self.unit_text()
        self.hide()
        tables = self.tables
        tables.view.setFocus()
        if not keep or self.cell is None:
            return
        uid, cell = self.cell
        item = tables.item
        if item is None or item.uid != uid:
            return
        st = item.sheet.workbook.style_of(item.sheet, *cell)
        if text:
            # what SMath refuses is refused, and why is said; a unit of
            # another kind is taken, as SMath takes it (2026-10-21)
            why = output_unit_refusal(text, item.sheet.workbook.value(item.sheet, *cell))
            if why is not None:
                say_refusal(tables.view, why, self)
                return
        if (st.unit or "") == text:
            return
        tables.select(cell)
        tables.format(unit=text or None)
