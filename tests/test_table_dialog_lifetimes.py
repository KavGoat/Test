"""A table's dialogs go when they are answered, and leave the application's
list of windows sound (exercise runs, 2026-10-17).

QDialog.exec() hands a dialog's ownership to Python (PySide 6.11) while Qt
still counts it its parent's child. Python then freed it whenever the garbage
collector next noticed it — once in the middle of PySide turning
QApplication.topLevelWidgets() into Python objects, which left a freed window
in the list and crashed the worker after Custom Sort… and the Conditional
Formatting Rules Manager. Each dialog here is opened the way a person opens
it: a right-click on a cell, the submenu, the item, then its own Cancel or OK
button.
"""
from __future__ import annotations

import gc

import pytest
import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QMenu

from tests.test_tables import cell_scene, make_table


def right_click(view, x, y):
    """A right-click where a person makes it: on the canvas's viewport, the
    press and then the context-menu event Qt sends after it."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QContextMenuEvent
    local = view.mapFromScene(QPointF(x, y))
    QTest.mousePress(view.viewport(), Qt.RightButton, Qt.NoModifier, local)
    QTest.mouseRelease(view.viewport(), Qt.RightButton, Qt.NoModifier, local)
    QApplication.sendEvent(view.viewport(), QContextMenuEvent(
        QContextMenuEvent.Mouse, local, view.viewport().mapToGlobal(local)))


def settle():
    for _ in range(3):
        QApplication.instance().processEvents()


@pytest.fixture
def w(window):
    window.interactive_prompts = True          # the real dialogs, run modally
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    settle()
    return window


def drive_menu_then_dialog(path, button):
    """Once the right-click menu is up: hover down *path*, click its last
    entry, then press *button* on the dialog that opens."""
    state = {"step": 0, "menu": None, "done": False, "dialog": None, "ticks": 0, "seen": []}

    def give_up():
        for _ in range(4):
            popup = QApplication.activePopupWidget()
            if popup is not None:
                popup.close()
        modal = QApplication.activeModalWidget()
        if isinstance(modal, QDialog):
            modal.reject()

    def tick():
        if state["done"]:
            return
        state["ticks"] += 1
        if state["ticks"] > 150:            # a step that never came: say which
            state["seen"].append((state["step"], type(QApplication.activePopupWidget()).__name__,
                                  type(QApplication.activeModalWidget()).__name__))
            give_up()
            return
        step = state["step"]
        if step < len(path):
            menu = state["menu"] or QApplication.activePopupWidget()
            if not isinstance(menu, QMenu) or not menu.isVisible():
                QTimer.singleShot(30, tick)
                return
            entry = next(a for a in menu.actions() if a.text().replace("&&", "&") == path[step])
            where = menu.actionGeometry(entry).center()
            QTest.mouseMove(menu, where)
            state["step"] += 1
            # the next look is booked first: the click below runs the dialog
            # there and then, modally, and returns only once it is answered
            QTimer.singleShot(60, tick)
            if entry.menu() is not None:
                state["menu"] = entry.menu()
            else:
                QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier, where)
            return
        dialog = QApplication.activeModalWidget()
        if not isinstance(dialog, QDialog):
            QTimer.singleShot(30, tick)
            return
        state["dialog"] = type(dialog).__name__
        QTest.mouseClick(dialog.findChild(QDialogButtonBox).button(button), Qt.LeftButton)
        state["done"] = True

    QTimer.singleShot(0, tick)
    return state


def walk_windows():
    """Every top-level widget, turned into Python and touched, with the
    collector run first so nothing it would free is left for later."""
    gc.collect()
    found = []
    for top in QApplication.topLevelWidgets():
        found.append((type(top).__name__, top.isVisible(),
                      top.parent() is not None and shiboken6.ownedByPython(top),
                      shiboken6.getCppPointer(top)[0]))
    return found


DIALOGS = [
    (("Data", "Custom Sort…"), QDialogButtonBox.Cancel),
    (("Data", "Remove Duplicates…"), QDialogButtonBox.Cancel),
    (("Data", "Data Validation…"), QDialogButtonBox.Cancel),
    (("Conditional Formatting", "Manage Rules…"), QDialogButtonBox.Cancel),
    (("Conditional Formatting", "Manage Rules…"), QDialogButtonBox.Ok),
]


def test_table_dialogs_leave_no_window_behind(w):
    table = make_table(w)
    spot = cell_scene(table, "A1")
    walk_windows()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    before = {t[3] for t in walk_windows()}
    for round_ in range(2):
        for path, button in DIALOGS:
            state = drive_menu_then_dialog(path, button)
            right_click(w.view, spot.x(), spot.y())     # modal: returns once answered
            settle()
            assert state["done"], (path, state)
            # no window both parented by Qt and owned by Python: the collector
            # would free it under Qt's feet
            risky = [t for t in walk_windows() if t[2]]
            assert not risky, (path, risky)
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    settle()
    # answered and closed, the dialogs and the right-click menus are gone:
    # nothing new is left among the application's windows
    strays = [t[:3] for t in walk_windows() if t[3] not in before and not t[1]]
    assert not strays, strays


def test_a_dialog_run_modally_stays_its_parents(w):
    """Any dialog, after exec(): Qt's again, not the collector's."""
    dialog = QDialog(w)
    QTimer.singleShot(30, dialog.reject)
    dialog.exec()
    assert shiboken6.isValid(dialog) and not shiboken6.ownedByPython(dialog)
    assert dialog.isWindow() and dialog.parent() is w
    dialog.deleteLater()
