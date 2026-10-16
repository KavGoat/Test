"""A variable's name typed and drawn as SMath does it (the user, 2026-10-16:
"The measurement's and the cell's Variable boxes should look and type as
SMath does (a "." makes a subscript, and so on); no units there").

The box is a QLineEdit to everything around it — text(), setText(),
returnPressed, editingFinished — so the menus and panels that hold one keep
working as they did. Inside, the typing goes to the equation editor's own
MathEditor, key by key, and the name is drawn by the equation's own
RegionItem: "L.beam" is typed L . b e a m and shows L with "beam" as its
subscript, in SMath's maths font, as the name of an equation does. What the
calculations read is the same "L.beam" an equation would define.

Only a name can be typed: letters (Greek too, from the Greek-letter keys as
in an equation, or typed or pasted), digits after the first letter, one "."
for the subscript and "_". No units, operators or spaces.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import QApplication, QLineEdit

from ..calc.editor import MathEditor
from ..calc.engine.model import GREEK
from ..calc.ui.layout import Style
from ..calc.ui.region_item import RegionItem
from ..calc.worksheet import Region

#: Characters a name may hold, besides letters and digits ("." makes the
#: subscript, as in SMath).
NAME_EXTRAS = "._"
#: the field is the paper an equation is written on, in either theme
PAPER = QColor("#ffffff")
EDGE = QColor("#a9abad")
FOCUS = QColor("#0083db")
HINT = QColor("#8a8c8e")
MARGIN = 3.0
PAD_X_EMPTY = 4.0       # where an empty name's square sits (the region's own pad)

_NO_SHEET = SimpleNamespace(index=SimpleNamespace(vars={}, funcs=()))


def name_char_ok(name: str, at: int, ch: str) -> bool:
    """Whether *ch* may go into *name* at position *at* — a name's letters,
    never a unit, an operator or a space."""
    if not ch or len(ch) != 1 or ch.isspace() or ch in "'\"":
        return False
    if ch == ".":
        return at > 0 and "." not in name
    if ch.isdigit():
        return at > 0
    return ch.isalpha() or ch in GREEK or ch == "_"


class SMathNameEdit(QLineEdit):
    """A variable's name, typed and drawn as in an SMath equation."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._region = Region(0.0, 0.0, editor=MathEditor())
        self._item = RegionItem(self._region, _NO_SHEET, Style(10.0))
        self.setAttribute(Qt.WA_InputMethodEnabled, False)
        self.setText(text)

    # -- the name ----------------------------------------------------------
    def setText(self, text: str) -> None:            # noqa: N802 - Qt's name
        """Put *text* in, as if each of its letters had been typed."""
        text = text or ""
        super().setText(text)
        editor = MathEditor()
        for at, ch in enumerate(text):
            if name_char_ok(text[:at], at, ch):
                editor.key(ch)
        self._region.editor = editor
        self._relayout()

    def name(self) -> str:
        """What the calculations read: the letters as typed, "L.beam"."""
        return "".join(item for item in self._region.editor.root.items
                       if isinstance(item, str))

    def _changed(self) -> None:
        name = self.name()
        if name != super().text():
            QLineEdit.setText(self, name)
            self.setModified(True)
            self.textEdited.emit(name)
        self._relayout()

    def _relayout(self) -> None:
        self._item.focused = self.hasFocus()
        self._item.relayout()
        self.updateGeometry()
        self.update()

    # -- keys --------------------------------------------------------------
    NAMED = {Qt.Key_Backspace: "BACK", Qt.Key_Delete: "DELETE", Qt.Key_Left: "LEFT",
             Qt.Key_Right: "RIGHT", Qt.Key_Home: "HOME", Qt.Key_End: "END"}

    def keyPressEvent(self, event) -> None:              # noqa: N802 - Qt's name
        key, mods = event.key(), event.modifiers()
        if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape, Qt.Key_Tab, Qt.Key_Backtab):
            super().keyPressEvent(event)                 # Enter names it, as before
            return
        editor = self._region.editor
        if mods & Qt.ControlModifier and key == Qt.Key_V:
            self._type(QApplication.clipboard().text().strip())
            return
        if mods & Qt.ControlModifier and key in (Qt.Key_Z, Qt.Key_Y):
            (editor.redo if key == Qt.Key_Y or mods & Qt.ShiftModifier else editor.undo)()
            self._changed()
            return
        named = self.NAMED.get(key)
        if named is not None:
            if named in ("BACK", "DELETE") and not editor.root.items:
                return
            editor.key(("SHIFT+" + named) if mods & Qt.ShiftModifier
                       and named in ("LEFT", "RIGHT", "HOME", "END") else named)
            self._changed()
            return
        symbol = self._greek_key(event)
        if symbol:
            self._type(symbol)
            return
        text = event.text()
        if text and not mods & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier):
            self._type(text)
            return
        event.accept()                                   # nothing else is a name

    def _type(self, text: str) -> None:
        editor = self._region.editor
        for ch in text:
            name = self.name()
            if name_char_ok(name, editor.pos if editor.row is editor.root else len(name), ch):
                editor.key(ch)
        self._changed()

    def _greek_key(self, event) -> str:
        """A Greek letter's key (Ctrl+Alt+F for φ, …): the letter, as an
        equation takes it — from the shortcut manager, so a key rebound
        there is rebound here too."""
        window = self._main_window()
        shortcuts = getattr(window, "shortcuts", None)
        if shortcuts is None:
            return ""
        from .shortcuts import EQUATION, TYPING
        binding = shortcuts.binding_for(QKeySequence(event.keyCombination()),
                                        scopes=(EQUATION, TYPING))
        if binding is None or binding.kind != "symbol":
            return ""
        from .calcedit import CalcEditing
        letter = getattr(CalcEditing, "SYMBOL_MEANINGS", {}).get(binding.payload, binding.payload)
        return letter if len(letter) == 1 and (letter in GREEK or letter == "μ") else ""

    def _main_window(self):
        widget = self
        while widget is not None:
            if hasattr(widget, "shortcuts"):
                return widget
            widget = widget.parentWidget()
        for top in QApplication.topLevelWidgets():
            if hasattr(top, "shortcuts") and top.isVisible():
                return top
        return None

    def insert(self, text: str) -> None:
        """Pasted or dropped words: their name letters, typed."""
        self._type(text)

    # -- the mouse ---------------------------------------------------------
    def mousePressEvent(self, event) -> None:            # noqa: N802 - Qt's name
        self.setFocus(Qt.MouseFocusReason)
        self._item.place_cursor(self._to_name(QPointF(event.position())))
        self._relayout()
        event.accept()

    def mouseMoveEvent(self, event) -> None:             # noqa: N802
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:      # noqa: N802
        event.accept()

    def focusInEvent(self, event) -> None:               # noqa: N802
        super().focusInEvent(event)
        self._relayout()

    def focusOutEvent(self, event) -> None:              # noqa: N802
        super().focusOutEvent(event)
        self._relayout()

    # -- drawing -----------------------------------------------------------
    # The name is the equation's own drawing of it, scaled so that its base
    # letters are the size of the words round the box (the menu's "Variable")
    # — an equation's 10 pt on the page is drawn smaller than a menu's text —
    # and set in the middle of the box, its subscript below the base line
    # with room under it (the user's review, 2026-10-16: "L" was jammed at
    # the top and looked no bigger than "beam").
    PAD = 5.0           # clear space round the ink, top and bottom

    def _scale(self) -> float:
        from PySide6.QtGui import QFontMetricsF
        words = QFontMetricsF(self.font()).capHeight()
        maths = QFontMetricsF(self._item.style.font(italic=True)).capHeight()
        return words / maths if maths > 0 and words > 0 else 1.0

    def ink_rect(self) -> QRectF:
        """Where the name's glyphs are, in the equation's own coordinates."""
        from PySide6.QtGui import QFontMetricsF
        from ..calc.ui.layout import LRect, LText
        found = QRectF()

        def walk(node, ox, oy):
            x, y = ox + node.x, oy + node.y
            if isinstance(node, LText) and node.text.strip():
                tight = QFontMetricsF(node.font).tightBoundingRect(node.text)
                rect = tight.translated(x, y)
            elif isinstance(node, LRect):
                rect = QRectF(x, y - node.asc, node.w, node.asc + node.desc)
            else:
                rect = None
            if rect is not None:
                nonlocal found
                found = rect if found.isNull() else found.united(rect)
            for child in node.children:
                walk(child, x, y)
        lay = self._item._layout
        if lay is not None:
            walk(lay, 0.0, 0.0)
        if found.isNull():
            base = self._item._baseline
            found = QRectF(PAD_X_EMPTY, base - 9.0, 8.0, 11.0)
        return found

    def _origin(self) -> QPointF:
        """Where the equation's origin goes, in the box, before scaling."""
        ink, scale = self.ink_rect(), self._scale()
        top = (self.height() - ink.height() * scale) / 2 - ink.top() * scale
        return QPointF(MARGIN + 3 - ink.left() * scale, top)

    def _to_name(self, point: QPointF) -> QPointF:
        scale = self._scale()
        return (point - self._origin()) / scale

    def sizeHint(self) -> QSize:                         # noqa: N802
        ink, scale = self.ink_rect(), self._scale()
        usual = super().sizeHint().height()
        return QSize(int(max(110.0, ink.right() * scale + 2 * MARGIN + 12)),
                     int(max(usual, ink.height() * scale + 2 * self.PAD) + 0.999))

    def minimumSizeHint(self) -> QSize:                  # noqa: N802
        return QSize(60, self.sizeHint().height())

    def paintEvent(self, _event) -> None:                # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        whole = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.fillRect(whole, PAPER)
        painter.setPen(QPen(FOCUS if self.hasFocus() else EDGE, 1))
        painter.drawRoundedRect(whole, 2, 2)
        if not self.name() and not self.hasFocus() and self.placeholderText():
            painter.setPen(HINT)
            painter.drawText(whole.adjusted(6, 0, -4, 0), Qt.AlignVCenter | Qt.AlignLeft,
                             self.placeholderText())
            return
        painter.save()
        painter.setClipRect(whole.adjusted(1, 1, -1, -1))
        painter.translate(self._origin())
        scale = self._scale()
        painter.scale(scale, scale)
        # the equation's own drawing of the name, and its cursor — without
        # the frame an equation being edited has on the page
        layout = self._item._layout
        if layout is not None:
            layout.paint(painter, layout.x, layout.y)
        if self.hasFocus():
            self._item._paint_cursor(painter)
        painter.restore()


def name_edit(text: str = "", parent=None) -> Optional[SMathNameEdit]:
    return SMathNameEdit(text, parent)
