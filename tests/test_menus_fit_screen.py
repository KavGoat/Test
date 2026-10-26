"""A menu taller than the screen is held to the screen and scrolls, and stays
so while it is open (the user, 2026-10-26: "the right-click context menu on
workbook split into two columns … why?": no second column, as Windows' menus
scroll). Qt resizes an open menu to its full height whenever an entry of it
changes — Edit's Undo takes the name of the last change as the menu opens —
which put the lower entries, and the submenus beside them, off the bottom
of the screen (tests/test_every_command.py found it on the 800 px screen
here: nothing below could be reached)."""
from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


def pump(seconds=0.0):
    end = time.monotonic() + seconds
    QApplication.processEvents()
    while time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)


def wheel(menu, down: bool):
    centre = menu.rect().center()
    event = QWheelEvent(QPointF(centre), QPointF(menu.mapToGlobal(centre)), QPoint(0, 0),
                        QPoint(0, -120 if down else 120), Qt.NoButton, Qt.NoModifier,
                        Qt.NoScrollPhase, False)
    QApplication.sendEvent(menu, event)
    pump()


def scrolled_to(menu, action) -> bool:
    """Roll the wheel until *action* is in sight, clear of the scroll arrows
    (an entry at either end sits under no arrow)."""
    for _ in range(300):
        rect = menu.actionGeometry(action)
        if 12 <= rect.top() and rect.bottom() <= menu.height() - 12:
            return True
        before = (menu.geometry(), rect)   # (a roll can move the menu without scrolling it)
        wheel(menu, down=rect.top() > menu.height() // 2)
        if (menu.geometry(), menu.actionGeometry(action)) == before:
            rect = menu.actionGeometry(action)
            return 0 <= rect.top() and rect.bottom() <= menu.height()
    return False


def hovered(menu, action) -> bool:
    centre = menu.actionGeometry(action).center()
    for k in range(6, -1, -1):
        QTest.mouseMove(menu, QPoint(centre.x() - 4 * k, centre.y()))
    end = time.monotonic() + 1.5
    while menu.activeAction() is not action and time.monotonic() < end:
        pump(0.02)
    return menu.activeAction() is action


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.interactive_prompts = False
    pump()
    return window


def tall_menu(w, which):
    """Two of the tallest: the menu bar's Edit and an ordinary page's
    Thumbnails menu."""
    if which == "Edit":
        return next(a.menu() for a in w.menuBar().actions()
                    if a.text().replace("&", "") == "Edit")
    page = next(i for i, p in enumerate(w.document.pages) if p.sheet is None)
    return w.page_menu(page)


@pytest.mark.parametrize("which", ["Edit", "page"])
def test_a_tall_menu_stays_on_the_screen_while_open_and_every_entry_can_be_reached(w, which):
    menu = tall_menu(w, which)
    available = w.screen().availableGeometry()
    if menu.sizeHint().height() <= available.height():
        pytest.skip("the screen here is tall enough for this menu")
    first = next(a for a in menu.actions() if not a.isSeparator())
    was = first.text()
    menu.popup(w.mapToGlobal(QPoint(150, 2)))
    pump(0.1)
    try:
        assert menu.isVisible()
        assert menu.geometry().bottom() <= available.bottom(), "held to the screen as it opens"
        # an entry changes while it is open: Undo takes a name, a command is greyed
        first.setText(was + " ")
        pump(0.1)
        assert menu.geometry().bottom() <= available.bottom(), "and held to it still"
        entries = [a for a in menu.actions() if a.isVisible() and not a.isSeparator()]
        assert scrolled_to(menu, entries[-1]), "the last entry can be scrolled to"
        last = [a for a in entries if a.isEnabled()][-1]     # (a greyed one never lights up)
        assert scrolled_to(menu, last) and hovered(menu, last), "and rested on"
        # a submenu low down opens beside its entry, whole, on the screen
        parents = [a for a in entries if a.menu() is not None]
        if parents:
            parent = parents[-1]
            assert scrolled_to(menu, parent) and hovered(menu, parent)
            sub = parent.menu()
            end = time.monotonic() + 1.5
            while not sub.isVisible() and time.monotonic() < end:
                pump(0.02)
            assert sub.isVisible(), parent.text()
            assert sub.geometry().bottom() <= available.bottom()
            inside = [a for a in sub.actions() if a.isVisible() and not a.isSeparator()]
            assert sub.actionGeometry(inside[-1]).bottom() <= sub.height(), "every entry of it shown"
    finally:
        for popup in (QApplication.activePopupWidget(),):
            if popup is not None:
                popup.hide()
        menu.hide()
        first.setText(was)
        pump()
