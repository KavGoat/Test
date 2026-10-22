"""A cell's unit typed as into SMath's unit placeholder (the user, 2026-10-22:
"Make superscripts exactly like SMath, where the entry black box is
superscripted").

The cell's black unit box, the formula bar's unit box and Format Cells'
"Show quantities in" stay QLineEdits to everything round them — text(),
setText(), textEdited, returnPressed, editingFinished — holding the unit as
it is stored (N^2, kN/m^2). Inside, the keys go to the equation editor's own
MathEditor with its cursor in the unit placeholder after a result, exactly as
when a unit is typed into an equation's box: ^ opens a raised exponent and
the digits go up there, → (or the next operator's place) comes back down,
/ makes a fraction of the unit before it, Backspace and the arrows move
through them as SMath's do. It is drawn by the equation's own RegionItem
(calc/ui/region_item.py and layout.py, used as they are), so the units are
SMath's blue with their powers raised and their fractions stacked, and an
empty or unfinished place shows SMath's black square.

As the unit list puts a unit into an equation's box ('kN), a word typed here
is marked as a unit, so it is drawn as one.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QApplication

from ..calc.editor import MathEditor
from ..calc.engine.model import GREEK, Frac, Paren, Pow, Row
from ..calc.ui.layout import Style
from ..calc.ui.region_item import RegionItem
from ..calc.worksheet import Region

PAPER = QColor("#ffffff")              # the paper an equation is written on, in either theme
EDGE = QColor("#a9abad")
FOCUS = QColor("#0083db")
SELECTED = QColor(0, 120, 200, 77)     # SMath's selection (region_item.SELECTION)
MARGIN = 2.0

_NO_SHEET = SimpleNamespace(index=SimpleNamespace(vars={}, funcs=()))
_WORD = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_'°%µμΩ." + GREEK)
_SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")


# -- the unit as stored and as the editor holds it --------------------------------------------
def row_unit_text(row: Row) -> str:
    """The unit in an editor's row, written as a cell stores it: 'kN with
    Pow(2) is kN^2, Frac('kN, 'm^2) is kN/m^2, a denominator of more than one
    unit in brackets (s^2/(kg*m)). What is no unit stays in, to be refused."""
    out = []
    for item in row.items:
        if isinstance(item, str):
            if item != "'":
                out.append(item)
        elif isinstance(item, Pow):
            power = row_unit_text(item.rows[0])
            out.append("^" + (power if not power or _is_number(power) else f"({power})"))
        elif isinstance(item, Frac):
            out.append(_wrapped(row_unit_text(item.rows[0])) + "/" +
                       _wrapped(row_unit_text(item.rows[1])))
        elif isinstance(item, Paren):
            out.append("(" + row_unit_text(item.rows[0]) + ")")
        else:
            out.append("?")                       # a structure no unit has
    return "".join(out)


def _is_number(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


def _wrapped(text: str) -> str:
    if not any(c in text for c in "*/ ·") or _one_bracket(text):
        return text
    return f"({text})"


def _one_bracket(text: str) -> bool:
    """Whether *text* is one bracket from its start to its end: (kg*m)."""
    if not (text.startswith("(") and text.endswith(")")):
        return False
    depth = 0
    for k, c in enumerate(text):
        depth += c == "("
        depth -= c == ")"
        if depth == 0 and k < len(text) - 1:
            return False
    return True


def unit_row(text: str) -> Optional[Row]:
    """The editor's row for a stored unit (kN/m^2: a fraction of 'kN over
    'm with a raised 2), as if it had been typed; None if *text* can't be
    read as one."""
    from ..sheet.values import _UNIT_TOKEN
    tokens, pos, text = [], 0, (text or "").strip()
    while pos < len(text):
        m = _UNIT_TOKEN.match(text, pos)
        if not m or m.end() == pos:
            return None
        pos = m.end()
        if m.group(1):
            tokens.append(("(", None))
        elif m.group(2):
            tokens.append((")", None))
        elif m.group(3):
            tokens.append(("/" if m.group(3) == "/" else "*", None))
        elif m.group(4):
            tokens.append(("^", m.group(4).translate(_SUPERSCRIPT).lstrip("^").replace(" ", "")))
        else:
            tokens.append(("u", m.group(5).lstrip("'")))
        if pos < len(text) and text[pos] in "  " and tokens[-1][0] in ("u", ")", "^"):
            rest = text[pos:].lstrip()
            if rest and rest[0] not in "*·⋅/^)⁰¹²³⁴⁵⁶⁷⁸⁹⁻":
                tokens.append(("*", None))
    at = [0]

    def peek():
        return tokens[at[0]][0] if at[0] < len(tokens) else None

    def factor():
        kind, value = tokens[at[0]] if at[0] < len(tokens) else (None, None)
        at[0] += 1
        if kind == "(":
            inner = product()
            if peek() != ")":
                raise ValueError(text)
            at[0] += 1
            items = [Paren(Row(inner))]
        elif kind == "u":
            items = ["'"] + list(value)
        else:
            raise ValueError(text)
        if peek() == "^":
            items.append(Pow(Row(list(tokens[at[0]][1]))))
            at[0] += 1
        return items

    def product():
        items = factor()
        while peek() in ("*", "/"):
            op = tokens[at[0]][0]
            at[0] += 1
            right = factor()
            if op == "*":
                items = items + ["*"] + right
            else:
                # the fraction's bar groups what is over and under it, as
                # SMath draws (kg·m) under s²: no bracket of its own
                items = [Frac(Row(_unbracketed(items)), Row(_unbracketed(right)))]
        return items

    if not tokens:
        return Row()
    try:
        items = product()
    except (ValueError, IndexError):
        return None
    if at[0] != len(tokens):
        return None
    return Row(items)


def _unbracketed(items: list) -> list:
    if len(items) == 1 and isinstance(items[0], Paren):
        return list(items[0].rows[0].items)
    return items


def _painted(box, colour: QColor) -> None:
    """All of a drawing in *colour*: a refused unit in SMath's error red,
    its unit blue too."""
    if hasattr(box, "color"):
        box.color = colour
    for child in getattr(box, "children", ()) or ():
        _painted(child, colour)


class _UnitPlaceholder:
    """The editor as the drawing sees it: only its unit placeholder's row, as
    though it were the whole equation (RegionItem draws an editor's root)."""

    evaluate = False
    kind = "math"
    plot_input = False

    def __init__(self, editor: MathEditor):
        self._editor = editor

    @property
    def root(self) -> Row:
        return self._editor.unit

    def __getattr__(self, name):
        return getattr(self._editor, name)


def _unit_editor() -> MathEditor:
    """An editor with its cursor in the unit placeholder after a result, as
    an equation's is when its unit box is typed into."""
    editor = MathEditor(Row(list("x=")))
    editor.evaluate = True
    editor.set_cursor(editor.unit, 0)
    return editor


class SMathUnitEditing:
    """SMath's unit placeholder in a QLineEdit (see the module's words).
    Call _init_unit_editing() from __init__."""

    # (↑ and ↓ go to the equation above or below in an equation; here there
    # is none, so they do nothing, as there)
    NAMED = {Qt.Key_Backspace: "BACK", Qt.Key_Delete: "DELETE", Qt.Key_Left: "LEFT",
             Qt.Key_Right: "RIGHT", Qt.Key_Home: "HOME", Qt.Key_End: "END"}
    PASSED = (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape, Qt.Key_Tab, Qt.Key_Backtab)

    _syncing = False
    _all = False                       # everything selected: the next key replaces it
    _red = None                        # the colour it is drawn in when refused

    def _init_unit_editing(self) -> None:
        self._editor = _unit_editor()
        self._region = Region(0.0, 0.0, editor=_UnitPlaceholder(self._editor))
        self._item = RegionItem(self._region, _NO_SHEET, Style(10.0))
        self.setAttribute(Qt.WA_InputMethodEnabled, False)
        self.textChanged.connect(self._from_text)
        self._from_text(self.text())

    # -- the unit ------------------------------------------------------------------------
    @property
    def unit_editor(self) -> MathEditor:
        return self._editor

    def _from_text(self, text: str) -> None:
        """Given a unit from outside (setText, a unit taken from the list):
        the editor holds it, with the cursor at its end."""
        if self._syncing:
            return
        editor = _unit_editor()
        row = unit_row(text)
        if row is None:
            self._editor = editor
            self._type_keys(text)
        else:
            editor.unit = row
            MathEditor._fix_parents(row)
            editor.set_cursor(row, len(row))
            self._editor = editor
        self._region.editor = _UnitPlaceholder(self._editor)
        self._all = False
        self._relayout()

    def _changed(self) -> None:
        """Typed into: the stored form follows, as if typed into the line."""
        text = row_unit_text(self._editor.unit)
        if text != self.text():
            self._syncing = True
            try:
                self.setText(text)
            finally:
                self._syncing = False
            self.setModified(True)
            self.textEdited.emit(text)
        self._relayout()

    def selectAll(self) -> None:                         # noqa: N802 - Qt's name
        """Everything selected, as when the box opens: the next key replaces it."""
        super().selectAll()
        self._all = bool(self._editor.unit.items)
        self.update()

    def _clear(self) -> None:
        editor = _unit_editor()
        self._editor = editor
        self._region.editor = _UnitPlaceholder(editor)
        self._all = False

    # -- keys ----------------------------------------------------------------------------
    def keyPressEvent(self, event) -> None:              # noqa: N802 - Qt's name
        key, mods = event.key(), event.modifiers()
        if key in self.PASSED:
            super().keyPressEvent(event)
            return
        if mods & Qt.ControlModifier and key == Qt.Key_A:
            self.selectAll()
            return
        if mods & Qt.ControlModifier and key == Qt.Key_V:
            if self._all:
                self._clear()
            self._type_keys(QApplication.clipboard().text().strip())
            self._changed()
            return
        if mods & Qt.ControlModifier and key in (Qt.Key_Z, Qt.Key_Y):
            (self._editor.redo if key == Qt.Key_Y or mods & Qt.ShiftModifier
             else self._editor.undo)()
            self._keep_in_unit()
            self._changed()
            return
        named = self.NAMED.get(key)
        if named is not None:
            if self._all:
                if named in ("BACK", "DELETE"):
                    self._clear()
                    self._changed()
                    return
                self._all = False
            if named in ("HOME", "END"):
                # the unit is all there is: its start and its end
                unit = self._editor.unit
                self._editor.selection = None
                self._editor.set_cursor(unit, 0 if named == "HOME" else len(unit))
                self._relayout()
                return
            shifted = mods & Qt.ShiftModifier and named in ("LEFT", "RIGHT")
            self._key("SHIFT+" + named if shifted else named)
            self._changed()
            return
        text = event.text()
        if text and text.isprintable() and not mods & (Qt.ControlModifier | Qt.AltModifier |
                                                       Qt.MetaModifier):
            if self._all:
                self._clear()
            self._type_keys(text)
            self._changed()
            return
        event.accept()

    def _type_keys(self, text: str) -> None:
        for ch in text:
            if ch in "·⋅×":
                ch = "*"
            raised = ch.translate(_SUPERSCRIPT) if ch in "⁰¹²³⁴⁵⁶⁷⁸⁹⁻" else None
            if raised is not None:
                # N² typed or pasted: N, then 2 in an exponent
                if not isinstance(self._editor.row.parent, Pow):
                    self._key("^")
                self._key(raised)
                continue
            if ch not in "'" and ch in _WORD and not ch.isdigit() and ch != "." and \
                    not self._in_word():
                self._key("'")             # a unit, as the unit list puts one in ('kN)
            self._key(ch)

    def _in_word(self) -> bool:
        editor = self._editor
        row, pos = editor.row, editor.pos
        before = row.items[pos - 1] if pos > 0 else None
        return isinstance(before, str) and before in _WORD

    def _key(self, k: str) -> None:
        self._editor.key(k)
        self._keep_in_unit()

    def _keep_in_unit(self) -> None:
        """The unit placeholder is all there is: the cursor never leaves it
        for the expression an equation would have before it."""
        editor = self._editor
        if not editor.in_unit:
            editor.selection = None
            editor.node = None
            editor.set_cursor(editor.unit, 0)

    # -- the mouse -----------------------------------------------------------------------
    def mousePressEvent(self, event) -> None:            # noqa: N802 - Qt's name
        self.setFocus(Qt.MouseFocusReason)
        self._all = False
        scale, origin = self._placement()
        self._item.place_cursor((QPointF(event.position()) - origin) / scale)
        self._keep_in_unit()
        self._relayout()
        event.accept()

    def mouseMoveEvent(self, event) -> None:             # noqa: N802
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:      # noqa: N802
        self.selectAll()
        event.accept()

    def focusInEvent(self, event) -> None:               # noqa: N802
        super().focusInEvent(event)
        self._relayout()

    def focusOutEvent(self, event) -> None:              # noqa: N802
        super().focusOutEvent(event)
        self._relayout()

    # -- drawing -------------------------------------------------------------------------
    def _relayout(self) -> None:
        self._item.focused = self.hasFocus()
        self._item.relayout()
        if self._red is not None and self._item._layout is not None:
            _painted(self._item._layout, self._red)
        self.update()

    def ink_rect(self) -> QRectF:
        """Where the unit's drawing is, in the equation's own coordinates."""
        lay = self._item._layout
        if lay is None:
            return QRectF(0, 0, 10, 12)
        return QRectF(lay.x, lay.y - lay.asc, lay.w, lay.asc + lay.desc)

    def _placement(self) -> tuple:
        """(scale, origin): the equation's drawing sized to the box's text and
        set in the middle of its height."""
        words = QFontMetricsF(self.font()).capHeight()
        maths = QFontMetricsF(self._item.style.font(italic=True)).capHeight()
        scale = words / maths if maths > 0 and words > 0 else 1.0
        ink = self.ink_rect()
        room = self.height() - 2 * MARGIN
        if ink.height() * scale > room > 0:
            scale = room / ink.height()          # a fraction kept inside the box
        top = (self.height() - ink.height() * scale) / 2 - ink.top() * scale
        return scale, QPointF(MARGIN + 2 - ink.left() * scale, top)

    def drawn_width(self) -> float:
        scale, _origin = self._placement()
        return self.ink_rect().right() * scale + 2 * MARGIN + 8

    def paper(self) -> QColor:
        return PAPER

    def paintEvent(self, _event) -> None:                # noqa: N802 - Qt's name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        whole = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.fillRect(whole, self.paper())
        painter.setPen(QPen(FOCUS if self.hasFocus() else EDGE, 1))
        painter.drawRect(whole)
        painter.save()
        painter.setClipRect(whole.adjusted(1, 1, -1, -1))
        scale, origin = self._placement()
        painter.translate(origin)
        painter.scale(scale, scale)
        layout = self._item._layout
        if layout is not None:
            if self._all:
                ink = self.ink_rect()
                painter.fillRect(ink, SELECTED)
            layout.paint(painter, layout.x, layout.y)
        if self.hasFocus() and self.isEnabled() and not self._all:
            self._item._paint_selection(painter)
            self._item._paint_cursor(painter)
        painter.restore()
