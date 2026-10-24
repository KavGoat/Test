"""Excel's Formula AutoComplete and argument tips, for a table's cells and
its formula bar.

Typing a formula, the functions, defined names and tables that start with
the word being typed are listed under it; Up and Down choose, Tab puts the
chosen one in (a function with its opening bracket), Escape closes the list
and Enter still enters the cell, as in Excel. Inside a function's brackets
a tip shows its arguments with the one being typed in bold — taken from the
function's own parameters, the optional ones in [brackets].
"""
from __future__ import annotations

import functools
import html
import inspect
import re
from typing import Optional

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem

from ..sheet.functions import FUNCTIONS

_WORD = re.compile(r"[A-Za-z_\\][A-Za-z0-9_.]*$")
FUNCTION, NAME, TABLE = "function", "name", "table"


def arguments(name: str) -> list[str]:
    """The arguments of an Excel function as Excel lists them:
    PMT -> rate, nper, pv, [fv], [kind]; SUM -> number1, [number2], …"""
    return list(_arguments(name))


@functools.lru_cache(maxsize=None)
def _arguments(name: str) -> tuple:
    # Worked out once a function: the list under "=S" asks for some fifty of
    # them at each key, and reading each one's signature was most of a key's
    # time (2026-10-19)
    return tuple(_read_arguments(name))


def _read_arguments(name: str) -> list[str]:
    from .excelargs import ARGS, WORDS
    if name in ARGS:
        return [a.strip() for a in ARGS[name].split(",")] if ARGS[name] else []
    spec = FUNCTIONS.get(name)
    if spec is None or spec.lazy:
        return ["…"]
    try:
        params = list(inspect.signature(spec.fn).parameters.values())
    except (TypeError, ValueError):
        return ["…"]
    out = []
    for i, p in enumerate(params):
        word = WORDS.get(p.name, p.name.lower().strip("_"))
        if p.kind is inspect.Parameter.VAR_POSITIONAL:
            word = word.rstrip("s") if word.endswith("s") and word != "known_x's" else word
            out += [f"{word}1" if i < spec.least else f"[{word}1]", f"[{word}2]", "…"]
            break
        optional = p.default is not inspect.Parameter.empty or i >= spec.least
        out.append(f"[{word}]" if optional else word)
    return out


def call_at(text: str, caret: int) -> Optional[tuple[str, int]]:
    """(function, argument index) the caret is inside, or None."""
    stack: list = []
    in_string = False
    i = 0
    before = text[:caret]
    while i < len(before):
        ch = before[i]
        if ch == '"':
            in_string = not in_string
        elif in_string:
            pass
        elif ch == "(":
            m = _WORD.search(before[:i])
            stack.append([m.group(0).upper() if m else "", 0])
        elif ch == "{":
            stack.append(["{", 0])
        elif ch in ")}" and stack:
            stack.pop()
        elif ch == "," and stack:
            stack[-1][1] += 1
        i += 1
    for name, index in reversed(stack):
        if name and name != "{":
            return name, index
        if name == "{":
            continue
        return None
    return None


def in_string(text: str, caret: int) -> bool:
    return text[:caret].count('"') % 2 == 1


class FormulaHelp:
    """The list and the tip, shared by the cell's text box and the formula bar."""

    def __init__(self, tables):
        self.tables = tables
        parent = tables.view
        self.list = QListWidget(parent)
        self.list.setWindowFlags(Qt.ToolTip)
        self.list.setFocusPolicy(Qt.NoFocus)
        self.list.setUniformItemSizes(True)
        self.list.setStyleSheet(
            "QListWidget{background:#fff;color:#000;border:1px solid #8a8a8a;outline:0;}"
            "QListWidget::item{padding:1px 4px;}"
            "QListWidget::item:selected{background:#cfe3f8;color:#000;}")
        self.list.itemClicked.connect(lambda _i: self.choose())
        self.tip = QLabel(parent)
        self.tip.setWindowFlags(Qt.ToolTip)
        self.tip.setTextFormat(Qt.RichText)
        self.tip.setStyleSheet("QLabel{background:#fffff0;color:#000;border:1px solid #8a8a8a;"
                               "padding:1px 4px;}")
        self.widget = None
        self.word_start = 0
        # what the last update was asked and left showing: a key in the cell
        # asks three times (the text changed, then the caret moved in the
        # cell and in the formula bar), and only the first has work to do
        self._settled = None
        self._found = None
        # a unit being typed: SMath's own list instead (ui/cellunits.py)
        from .cellunits import UnitList
        self.units = UnitList(tables)

    # -- what to offer ------------------------------------------------------------------------
    def _candidates(self, word: str) -> list[tuple[str, str]]:
        up = word.upper()
        out = [(name, FUNCTION) for name in sorted(FUNCTIONS) if name.startswith(up)]
        item = self.tables.item
        if item is not None and item.sheet is not None:
            wb = item.sheet.workbook
            sheet = item.sheet
            # the Excel names this sheet reads bare; a CalcForge variable
            # (a Variable box's) as it is read, CALC(name) (the user, 2026-10-24)
            names = sorted({dn.name for dn in wb.names.values() if not dn.variable
                            and wb.find_excel_name(dn.name, sheet) is dn}, key=str.lower)
            out += [(n, NAME) for n in names if n.upper().startswith(up)]
            variables = sorted({dn.name for dn in wb.names.values() if dn.variable},
                               key=str.lower)
            out += [(f"CALC({n})", NAME) for n in variables if n.upper().startswith(up)]
            out += [(s.name, TABLE) for s in wb.sheets
                    if getattr(s, "kind", "") == "table" and s.name.upper().startswith(up)]
        return out

    def _state(self, widget) -> tuple:
        """Everything an update reads, and what is showing."""
        item = self.tables.item
        return (id(widget), widget.text(), widget.cursorPosition(), widget.isVisible(),
                id(item), widget.mapToGlobal(QPoint(0, 0)).toTuple(),
                self.list.isVisible(), self.tip.isVisible(), self.units.visible())

    def update(self, widget) -> None:
        """After a key or a caret move in ``widget`` (a QLineEdit)."""
        state = self._state(widget)
        if state == self._settled and widget is self.widget:
            return                     # asked again with nothing changed
        self._update(widget)
        self._settled = self._state(widget)

    def _update(self, widget) -> None:
        self.widget = widget
        text, caret = widget.text(), widget.cursorPosition()
        if self.units.update(widget):
            self.list.hide()
            return
        if not text.startswith("=") or not widget.isVisible() or in_string(text, caret):
            self.hide()
            return
        self._update_tip(widget, text, caret)
        m = _WORD.search(text[1:caret])
        after = text[caret:caret + 1]
        if m is None or (after and (after.isalnum() or after in "_.")) or m.group(0)[0].isdigit():
            self.list.hide()
            return
        word = m.group(0)
        found = self._candidates(word)
        if not found or (len(found) == 1 and found[0][0].upper() == word.upper()
                         and found[0][1] != FUNCTION):
            self.list.hide()
            return
        self.word_start = caret - len(word)
        if found != self._found or self.list.count() != len(found):
            # filled again only when what it lists changes
            self._found = found
            self.list.clear()
            for name, kind in found:
                entry = QListWidgetItem(name)
                entry.setData(Qt.UserRole, kind)
                if kind == FUNCTION:
                    entry.setToolTip(f"{name}({', '.join(arguments(name))})")
                else:
                    entry.setToolTip("a defined name" if kind == NAME else "a table")
                self.list.addItem(entry)
            rows = min(10, len(found))
            height = self.list.sizeHintForRow(0) * rows + 4
            width = max(160, self.list.sizeHintForColumn(0) + 30)
            if self.list.size().toTuple() != (width, height):
                self.list.resize(width, height)
        self.list.setCurrentRow(0)
        below = widget.mapToGlobal(QPoint(widget.cursorRect().left(), widget.height()))
        if self.tip.isVisible():
            below += QPoint(0, self.tip.height() + 2)
        # A window of its own: moved, shown and raised only when it must be
        # (each is a call to the window system, slow on Windows)
        if self.list.pos() != below:
            self.list.move(below)
        if not self.list.isVisible():
            self.list.show()
            self.list.raise_()

    def _update_tip(self, widget, text: str, caret: int) -> None:
        got = call_at(text[1:], caret - 1)
        if got is None or got[0] not in FUNCTIONS:
            self.tip.hide()
            return
        name, index = got
        args = arguments(name)
        if not args:
            self._show_tip(widget, f"{name}()", raise_it=False)
            return
        if args[-1] == "…" and len(args) >= 3:
            # number1, [number2], …: past the second, still the repeating one
            index = min(index, len(args) - 2)
        else:
            index = min(index, len(args) - 1)
        parts = [f"<b>{html.escape(a)}</b>" if i == index else html.escape(a) for i, a in enumerate(args)]
        self._show_tip(widget, f"{name}({', '.join(parts)})")

    def _show_tip(self, widget, text: str, raise_it: bool = True) -> None:
        """The tip with *text*, under *widget*: its words, size and place set
        only when they change, as each is a call to the window system."""
        tip = self.tip
        if tip.text() != text:
            tip.setText(text)
            tip.adjustSize()
        at = widget.mapToGlobal(QPoint(0, widget.height() + 1))
        if tip.pos() != at:
            tip.move(at)
        if not tip.isVisible():
            tip.show()
            if raise_it:
                tip.raise_()

    # -- keys ----------------------------------------------------------------------------------
    def key(self, event) -> bool:
        """Up, Down, Tab and Escape while the list is open; True when used."""
        if self.units.key(event):
            return True
        if not self.list.isVisible():
            return False
        key = event.key()
        if key in (Qt.Key_Up, Qt.Key_Down):
            row = self.list.currentRow() + (1 if key == Qt.Key_Down else -1)
            self.list.setCurrentRow(max(0, min(self.list.count() - 1, row)))
            return True
        if key == Qt.Key_Tab:
            self.choose()
            return True
        if key == Qt.Key_Escape:
            self.list.hide()
            self._settled = None
            return True
        return False

    def choose(self) -> None:
        entry = self.list.currentItem()
        widget = self.widget
        if entry is None or widget is None:
            return
        name = entry.text()
        insert = name + "(" if entry.data(Qt.UserRole) == FUNCTION else name
        text, caret = widget.text(), widget.cursorPosition()
        new = text[:self.word_start] + insert + text[caret:]
        self.list.hide()
        self.tables._formula_from_help(widget, new, self.word_start + len(insert))

    def hide(self) -> None:
        self.list.hide()
        self.tip.hide()
        self.units.hide()
        self._settled = None

    def visible(self) -> bool:
        return self.list.isVisible() or self.units.visible()
