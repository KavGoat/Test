"""Small helpers every right-click menu is built with.

``tidy`` runs once a menu is built: no separator at the top or bottom of a
menu, never two in a row, and no submenu with nothing in it — whatever the
conditions that built it left out (QA round 4: the equation and thumbnail
menus had two separators in a row).

``proxy`` puts a window command on a menu under the name that menu uses
(Revu's "Set Scale…" for the window's "Page Scale…") with the key it really
answers to shown beside it, without a second binding of that key.

``keep_menus_on_screen`` holds a menu taller than the screen to the screen
while it is open, so that it scrolls (as Windows' menus do) rather than
running off the bottom.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMenu, QStyle, QWidgetAction

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


class _MenusOnScreen(QObject):
    """A menu taller than the screen opens held to the screen and scrolls
    (the style's menu-scrollable, theme.py, rather than Qt's second column)
    — and stays so. Qt resizes an open menu to its full height whenever one
    of its entries changes (QMenu::actionEvent; Edit's Undo takes the name of
    the last change as the menu shows, a command is greyed), which put the
    lower entries, and the submenus beside them, off the bottom of the
    screen (2026-10-26). A menu that opened short enough and grew past the
    screen is held too, though Qt gives it no scroll arrows then: nothing
    is lost that could have been reached."""

    def eventFilter(self, watched, event) -> bool:
        if event.type() not in (QEvent.Resize, QEvent.Move) or not isinstance(watched, QMenu) \
                or watched.windowType() != Qt.Popup or not watched.isVisible():
            return False                     # (moved: a menu bar's is put 2 px down once shown)
        frame = watched.style().pixelMetric(QStyle.PM_MenuDesktopFrameWidth, None, watched)
        room = watched.screen().availableGeometry().bottom() - 2 * frame - watched.y()
        if watched.height() > room > 0:
            watched.resize(watched.width(), room)      # (as QMenu sized it when it opened)
        return False


def keep_menus_on_screen(application) -> None:
    """Once per application: every menu of it held to the screen."""
    if getattr(application, "_menus_on_screen", None) is None:
        application._menus_on_screen = _MenusOnScreen(application)
        application.installEventFilter(application._menus_on_screen)


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
    # the same command as *action*, for Keyboard Shortcuts (bindable.py)
    command = action.property("cf_command")
    if command:
        entry.setProperty("cf_command", command)
    menu.addAction(entry)
    return entry


def walk(menu: QMenu, path: tuple = ()):
    """(path, action) for every entry of *menu* and its submenus."""
    for action in menu.actions():
        yield path, action
        sub = action.menu()
        if sub is not None:
            yield from walk(sub, path + (action.text(),))
