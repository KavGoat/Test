"""Small helpers every right-click menu is built with.

``tidy`` runs once a menu is built: no separator at the top or bottom of a
menu, never two in a row, and no submenu with nothing in it — whatever the
conditions that built it left out (QA round 4: the equation and thumbnail
menus had two separators in a row).

``proxy`` puts a window command on a menu under the name that menu uses
(Revu's "Set Scale…" for the window's "Page Scale…") with the key it really
answers to shown beside it, without a second binding of that key.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMenu, QWidgetAction

# Small words Title Case leaves in lower case (unless first).
_SMALL = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on", "or",
          "the", "to", "with"}


def title_case(text: str) -> str:
    """"Text box" → "Text Box"; words already capitalised are kept."""
    words = text.split(" ")
    out = []
    for i, word in enumerate(words):
        if word and word[0].islower() and (i == 0 or word not in _SMALL):
            word = word[0].upper() + word[1:]
        out.append(word)
    return " ".join(out)


def _content(action) -> bool:
    return action.isVisible() and not action.isSeparator()


def tidy(menu: QMenu) -> QMenu:
    """Strip leading, trailing and doubled separators and empty submenus,
    in *menu* and every submenu of it."""
    for action in list(menu.actions()):
        sub = action.menu()
        if sub is not None and not isinstance(action, QWidgetAction):
            tidy(sub)
            if not any(_content(a) for a in sub.actions()):
                menu.removeAction(action)
    previous_was_gap = True              # a separator at the top goes
    for action in list(menu.actions()):
        if not action.isVisible():
            continue
        if action.isSeparator():
            if previous_was_gap:
                menu.removeAction(action)
                continue
            previous_was_gap = True
        else:
            previous_was_gap = False
    visible = [a for a in menu.actions() if a.isVisible()]
    while visible and visible[-1].isSeparator():
        menu.removeAction(visible.pop())
    return menu


def proxy(menu: QMenu, action: QAction, text: Optional[str] = None,
          keys: Optional[QKeySequence] = None) -> QAction:
    """*action* on *menu* as *text*, showing *keys* (by default the keys
    *action* is bound to). The shown key is only live while the menu is."""
    entry = QAction(action.icon(), text or action.text(), menu)
    entry.setEnabled(action.isEnabled())
    entry.setToolTip(action.toolTip())
    entry.setStatusTip(action.statusTip())
    shown = keys if keys is not None else action.shortcut()
    if not shown.isEmpty():
        entry.setShortcut(shown)
        entry.setShortcutContext(Qt.WidgetShortcut)
    entry.triggered.connect(lambda _checked=False: action.trigger())
    menu.addAction(entry)
    return entry


def walk(menu: QMenu, path: tuple = ()):
    """(path, action) for every entry of *menu* and its submenus."""
    for action in menu.actions():
        yield path, action
        sub = action.menu()
        if sub is not None:
            yield from walk(sub, path + (action.text(),))
