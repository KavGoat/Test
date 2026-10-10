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

    # -- what to offer ------------------------------------------------------------------------
    def _candidates(self, word: str) -> list[tuple[str, str]]:
        up = word.upper()
        out = [(name, FUNCTION) for name in sorted(FUNCTIONS) if name.startswith(up)]
        item = self.tables.item
        if item is not None and item.sheet is not None:
            wb = item.sheet.workbook
            names = sorted({dn.name for dn in wb.names.values()}, key=str.lower)
            out += [(n, NAME) for n in names if n.upper().startswith(up)]
            out += [(s.name, TABLE) for s in wb.sheets
                    if getattr(s, "kind", "") == "table" and s.name.upper().startswith(up)]
        return out

    def update(self, widget) -> None:
        """After a key or a caret move in ``widget`` (a QLineEdit)."""
        self.widget = widget
        text, caret = widget.text(), widget.cursorPosition()
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
        self.list.clear()
        for name, kind in found:
            entry = QListWidgetItem(name)
            entry.setData(Qt.UserRole, kind)
            if kind == FUNCTION:
                entry.setToolTip(f"{name}({', '.join(arguments(name))})")
            else:
                entry.setToolTip("a defined name" if kind == NAME else "a table")
            self.list.addItem(entry)
        self.list.setCurrentRow(0)
        rows = min(10, len(found))
        height = self.list.sizeHintForRow(0) * rows + 4
        width = max(160, self.list.sizeHintForColumn(0) + 30)
        self.list.resize(width, height)
        below = widget.mapToGlobal(QPoint(widget.cursorRect().left(), widget.height()))
        if self.tip.isVisible():
            below += QPoint(0, self.tip.height() + 2)
        self.list.move(below)
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
            self.tip.setText(f"{name}()")
            self.tip.adjustSize()
            self.tip.move(widget.mapToGlobal(QPoint(0, widget.height() + 1)))
            self.tip.show()
            return
        if args[-1] == "…" and len(args) >= 3:
            # number1, [number2], …: past the second, still the repeating one
            index = min(index, len(args) - 2)
        else:
            index = min(index, len(args) - 1)
        parts = [f"<b>{html.escape(a)}</b>" if i == index else html.escape(a) for i, a in enumerate(args)]
        self.tip.setText(f"{name}({', '.join(parts)})")
        self.tip.adjustSize()
        self.tip.move(widget.mapToGlobal(QPoint(0, widget.height() + 1)))
        self.tip.show()
        self.tip.raise_()

    # -- keys ----------------------------------------------------------------------------------
    def key(self, event) -> bool:
        """Up, Down, Tab and Escape while the list is open; True when used."""
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

    def visible(self) -> bool:
        return self.list.isVisible()
