"""Novice usability harness (docs/qa/QA_PLAN.md section 3).

Builds the real MainWindow headless, the way tests/conftest.py's ``window``
fixture does, but with ``interactive_prompts`` left on so a dialog appears the
way it does for a user. Everything is driven with real events:

* mouse and keys go to ``window.view.viewport()`` through QTest / sendEvent;
* menus are opened by walking ``window.menuBar()`` (one click per level);
* right-click menus and modal dialogs run modally, so a QTimer polls
  ``QApplication.activePopupWidget()`` / ``activeModalWidget()``, records
  what is shown, hands it to the task's handler and closes it.

Clicks and keys are counted in ``Log`` so each task can report them. Nothing
in the application is changed.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SANDBOX = tempfile.mkdtemp(prefix="calcforge-novice-")
for _v in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
    os.environ[_v] = os.path.join(_SANDBOX, _v.lower())
    os.makedirs(os.environ[_v], exist_ok=True)
os.environ["CALCFORGE_SETTINGS_FILE"] = os.path.join(_SANDBOX, "novice.ini")
os.environ["CALCFORGE_MARKFORGE_SETTINGS_FILE"] = os.path.join(_SANDBOX, "mf-absent.ini")
sys.path.insert(0, ROOT)

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QAction, QContextMenuEvent, QMouseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (QAbstractButton, QApplication, QDialog,  # noqa: E402
                               QLabel, QLineEdit, QMenu, QWidget, QComboBox,
                               QAbstractSpinBox, QCheckBox, QRadioButton,
                               QToolBar, QToolButton, QDockWidget)

SHOTS = os.environ.get(
    "NOVICE_SHOTS",
    "/tmp/claude-0/-home-user-Test/612018b6-a7e0-52c2-960e-e0bdb34e3bba/"
    "scratchpad/qa/novice")
os.makedirs(SHOTS, exist_ok=True)
WORK = tempfile.mkdtemp(prefix="novice-work-")

APP = None


def app():
    global APP
    if APP is None:
        from calcforge.app import build_application
        APP = QApplication.instance() or build_application([])
    return APP


def pump(n: int = 3) -> None:
    for _ in range(n):
        app().processEvents()


# ---------------------------------------------------------------------------
# the log a task fills in
# ---------------------------------------------------------------------------
CURRENT = None          # the Log of the task being run, for stall timing
WATCHING = [0]          # >0 while a modal dialog/popup may be on screen


def _stall(label: str, ms: float) -> None:
    if CURRENT is not None and ms > 100 and not WATCHING[0]:
        after = CURRENT.path[-1] if CURRENT.path else "start"
        CURRENT.stalls.append(f"{label} (after '{after}'): {ms:.0f} ms")


def timed(label):
    """Record a call over 100 ms (no dialog involved) as a visible stall."""
    def wrap(fn):
        def inner(*a, **k):
            t0 = time.perf_counter()
            out = fn(*a, **k)
            _stall(label, (time.perf_counter() - t0) * 1000)
            return out
        inner.__name__ = fn.__name__
        inner.__doc__ = fn.__doc__
        return inner
    return wrap


class Log:
    def __init__(self, task: str):
        global CURRENT
        CURRENT = self
        self.task = task
        self.clicks = 0
        self.keys = 0
        self.path: list[str] = []
        self.wrong: list[str] = []
        self.confusion: list[str] = []
        self.success = False
        self.notes: list[str] = []
        self.stalls: list[str] = []

    def step(self, what: str, clicks: int = 0, keys: int = 0) -> None:
        if os.environ.get("NOVICE_TRACE"):
            print("  step:", what, file=sys.stderr, flush=True)
        self.clicks += clicks
        self.keys += keys
        self.path.append(what)

    def wrong_turn(self, what: str) -> None:
        self.wrong.append(what)

    def confused(self, what: str) -> None:
        self.confusion.append(what)

    def note(self, what: str) -> None:
        if os.environ.get("NOVICE_TRACE"):
            print("  note:", what[:200], file=sys.stderr, flush=True)
        self.notes.append(what)

    def timed(self, label: str, fn, *a, **k):
        t0 = time.perf_counter()
        out = fn(*a, **k)
        pump()
        ms = (time.perf_counter() - t0) * 1000
        if ms > 100:
            self.stalls.append(f"{label}: {ms:.0f} ms")
        return out

    def summary(self) -> dict:
        return dict(task=self.task, success=self.success, clicks=self.clicks,
                    keys=self.keys, path=self.path, wrong=self.wrong,
                    confusion=self.confusion, stalls=self.stalls, notes=self.notes)


# ---------------------------------------------------------------------------
# the window
# ---------------------------------------------------------------------------
def new_window(prompts: bool = True):
    app()
    from calcforge.ui.mainwindow import MainWindow
    main = MainWindow()
    main.confirm_discard = lambda: True
    main.interactive_prompts = prompts
    main.resize(1280, 860)
    main.show()
    main.activateWindow()
    main.view.set_zoom(1.0)
    pump()
    return main


def shot(window, name: str) -> str:
    path = os.path.join(SHOTS, name + ".png")
    window.grab().save(path)
    return path


def widget_shot(widget, name: str) -> str:
    path = os.path.join(SHOTS, name + ".png")
    widget.grab().save(path)
    return path


# ---------------------------------------------------------------------------
# menus
# ---------------------------------------------------------------------------
def _clean(text: str) -> str:
    return text.replace("&&", "\x00").replace("&", "").replace("\x00", "&")


def _fill(menu: QMenu) -> None:
    menu.aboutToShow.emit()
    pump(1)


def menu_tree(window) -> list[tuple[str, QAction]]:
    """Every menu-bar entry as ('File > Save As...', action)."""
    out = []

    def walk(menu: QMenu, prefix: str, depth: int):
        if depth > 5:
            return
        _fill(menu)
        for act in menu.actions():
            if act.isSeparator():
                continue
            label = prefix + " > " + _clean(act.text())
            out.append((label, act))
            if act.menu():
                walk(act.menu(), label, depth + 1)

    for top in window.menuBar().actions():
        if top.menu():
            walk(top.menu(), _clean(top.text()), 1)
    return out


def menu_search(window, *words: str) -> list[str]:
    """Labels a novice would spot that contain any of *words* (case-insensitive)."""
    found = []
    for label, _ in menu_tree(window):
        leaf = label.split(" > ")[-1].lower()
        if any(w.lower() in leaf for w in words):
            found.append(label)
    return found


def menu_action(window, path: str) -> QAction | None:
    for label, act in menu_tree(window):
        if label == path:
            return act
    return None


def top_menu_names(window) -> list[str]:
    return [_clean(a.text()) for a in window.menuBar().actions()]


def menu_items(window, top: str) -> list[str]:
    for a in window.menuBar().actions():
        if _clean(a.text()) == top and a.menu():
            _fill(a.menu())
            return [_clean(x.text()) if not x.isSeparator() else "----"
                    for x in a.menu().actions()]
    return []


def use_menu(window, log: Log, path: str, handler=None, timeout_ms: int = 4000):
    """Click through the menu bar to *path*; one click per level.

    *handler(widget)* is called with the first modal dialog that appears."""
    act = menu_action(window, path)
    if act is None:
        raise LookupError(path)
    levels = path.count(" > ") + 1
    log.step("menu " + path, clicks=levels)
    if not act.isEnabled():
        log.confused(f"'{path}' is greyed out")
        return None
    return run_with_modal(lambda: act.trigger(), handler, timeout_ms, log, path)


# ---------------------------------------------------------------------------
# modal things: dialogs and popups
# ---------------------------------------------------------------------------
class _Watch:
    def __init__(self, handler, log, label):
        self.handler = handler
        self.log = log
        self.label = label
        self.seen = []
        self.timer = QTimer()
        self.timer.setInterval(30)
        self.timer.timeout.connect(self.tick)
        self.busy = False

    def tick(self):
        if self.busy:
            return
        widget = QApplication.activePopupWidget() or QApplication.activeModalWidget()
        if widget is None or widget in self.seen:
            return
        self.seen.append(widget)
        self.busy = True
        try:
            if self.handler is not None:
                self.handler(widget)
            else:
                close(widget)
        except Exception as exc:  # noqa: BLE001
            if self.log:
                self.log.note(f"handler error on {self.label}: {exc!r}")
            close(widget)
        finally:
            self.busy = False


def close(widget) -> None:
    if isinstance(widget, QDialog):
        widget.reject()
    else:
        widget.close()


def run_with_modal(fn, handler=None, timeout_ms=4000, log=None, label=""):
    """Run *fn*; dialogs or popups it opens go to *handler*. The time is a
    stall when nothing modal appeared and it took over 100 ms."""
    watch = _Watch(handler, log, label)
    t0 = time.perf_counter()
    WATCHING[0] += 1
    watch.timer.start()
    guard = QTimer()
    guard.setSingleShot(True)

    def give_up():
        w = QApplication.activePopupWidget() or QApplication.activeModalWidget()
        if w is not None:
            if log:
                log.note(f"timeout: closed {type(w).__name__} '{w.windowTitle()}'")
            close(w)
    guard.timeout.connect(give_up)
    guard.start(timeout_ms)
    try:
        out = fn()
        pump()
    finally:
        watch.timer.stop()
        guard.stop()
        WATCHING[0] -= 1
        _refocus()
    if not watch.seen:
        _stall(label or getattr(fn, "__name__", "action"), (time.perf_counter() - t0) * 1000)
    return out, watch.seen


def _refocus() -> None:
    """A window manager gives the keyboard back to the main window when a
    dialog closes; the offscreen platform does not, so do it here (a closed
    dialog's field otherwise keeps the keyboard and swallows shortcuts)."""
    fw = QApplication.focusWidget()
    if fw is not None and QWidget.window(fw).isVisible():
        return
    for top in QApplication.topLevelWidgets():
        if top.isVisible() and type(top).__name__ == "MainWindow":
            top.activateWindow()
            top.view.setFocus()
            pump(1)
            return


def describe(widget) -> str:
    """What a novice reads on a dialog: title, labels, buttons, fields."""
    parts = [f"[{type(widget).__name__}] '{widget.windowTitle()}'"]
    for child in widget.findChildren(QWidget):
        if not child.isVisibleTo(widget):
            continue
        if isinstance(child, QLabel) and child.text().strip():
            parts.append("label:" + child.text().strip()[:80])
        elif isinstance(child, QCheckBox) or isinstance(child, QRadioButton):
            parts.append(f"{type(child).__name__[1:]}:{child.text()}={child.isChecked()}")
        elif isinstance(child, QAbstractButton) and child.text():
            parts.append("button:" + child.text())
        elif isinstance(child, QLineEdit) and not isinstance(child.parent(), (QComboBox, QAbstractSpinBox)):
            parts.append(f"edit:'{child.text()}'")
        elif isinstance(child, QComboBox):
            parts.append(f"combo:{child.currentText()}")
        elif isinstance(child, QAbstractSpinBox):
            parts.append(f"spin:{child.text()}")
    return " | ".join(parts)


def menu_labels(menu: QMenu) -> list[str]:
    return [_clean(a.text()) if not a.isSeparator() else "----" for a in menu.actions()]


def pick_from_popup(menu: QMenu, *path: str) -> bool:
    """Trigger path[0] (> path[1] ...) in a popup menu; returns True if found."""
    current = menu
    for i, name in enumerate(path):
        hit = None
        for act in current.actions():
            if _clean(act.text()).rstrip(".…").lower() == name.rstrip(".…").lower():
                hit = act
                break
        if hit is None:
            current.close() if i == 0 else menu.close()
            return False
        if hit.menu() and i < len(path) - 1:
            _fill(hit.menu())
            current = hit.menu()
            continue
        menu.close()
        QTimer.singleShot(0, hit.trigger)
        return True
    return False


def find_button(widget, text: str):
    for b in widget.findChildren(QAbstractButton):
        if _clean(b.text()).rstrip(".…").lower() == text.rstrip(".…").lower():
            return b
    return None


# ---------------------------------------------------------------------------
# pointer and keys
# ---------------------------------------------------------------------------
def _mouse(view, kind, x, y, button=Qt.LeftButton, buttons=None, modifiers=Qt.NoModifier):
    local = view.mapFromScene(QPointF(x, y))
    globally = view.viewport().mapToGlobal(local)
    if buttons is None:
        buttons = button if kind != QEvent.MouseButtonRelease else Qt.NoButton
    return QMouseEvent(kind, QPointF(local), QPointF(globally), button, buttons, modifiers)


@timed("click")
def click(view, x, y, button=Qt.LeftButton, modifiers=Qt.NoModifier):
    for kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
        QApplication.sendEvent(view.viewport(), _mouse(view, kind, x, y, button,
                                                       modifiers=modifiers))
    pump(1)


@timed("double-click")
def double_click(view, x, y):
    for kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease,
                 QEvent.MouseButtonDblClick, QEvent.MouseButtonRelease):
        QApplication.sendEvent(view.viewport(), _mouse(view, kind, x, y))
    pump(1)


def hover(view, x, y):
    QApplication.sendEvent(view.viewport(), _mouse(view, QEvent.MouseMove, x, y,
                                                   Qt.NoButton, Qt.NoButton))


@timed("drag")
def drag(view, x0, y0, x1, y1, modifiers=Qt.NoModifier, steps=4):
    QApplication.sendEvent(view.viewport(), _mouse(view, QEvent.MouseButtonPress, x0, y0,
                                                   modifiers=modifiers))
    for i in range(1, steps + 1):
        f = i / steps
        QApplication.sendEvent(view.viewport(), _mouse(
            view, QEvent.MouseMove, x0 + (x1 - x0) * f, y0 + (y1 - y0) * f,
            Qt.NoButton, Qt.LeftButton, modifiers))
    QApplication.sendEvent(view.viewport(), _mouse(view, QEvent.MouseButtonRelease, x1, y1,
                                                   modifiers=modifiers))
    pump(1)


def right_click_menu(view, x, y, handler=None, log=None, label="right-click",
                     on_dialog=None):
    """Right-click at scene (x, y); return the labels of the popup that opened.

    *handler(menu)* may pick an entry; otherwise the menu is closed."""
    local = view.mapFromScene(QPointF(x, y))
    got = {}

    def h(widget):
        if isinstance(widget, QMenu):
            got["labels"] = menu_labels(widget)
            got["menu"] = widget
            if handler is not None:
                handler(widget)
            else:
                widget.close()
        else:
            got.setdefault("dialogs", []).append(describe(widget))
            if on_dialog is not None:
                on_dialog(widget)
            else:
                close(widget)

    def fire():
        QApplication.sendEvent(view.viewport(), QContextMenuEvent(
            QContextMenuEvent.Mouse, local, view.viewport().mapToGlobal(local)))
    if log:
        log.step(label, clicks=1)
    run_with_modal(fire, h, 4000, log, label)
    return got.get("labels", [])


def right_click_widget(widget, pos: QPoint, handler=None, on_dialog=None):
    """Right-click a widget; *handler(menu)* may pick an entry and
    *on_dialog(dialog)* handles a dialog that entry opens."""
    got = {}

    def h(w):
        if isinstance(w, QMenu):
            got["labels"] = menu_labels(w)
            if handler is not None:
                handler(w)
            else:
                w.close()
        elif on_dialog is not None:
            on_dialog(w)
        else:
            close(w)

    def fire():
        QApplication.sendEvent(widget, QContextMenuEvent(
            QContextMenuEvent.Mouse, pos, widget.mapToGlobal(pos)))
    run_with_modal(fire, h)
    # a menu shown with popup() rather than exec() is still open here
    pump(2)
    popup = QApplication.activePopupWidget()
    if "labels" not in got and isinstance(popup, QMenu):
        h(popup)
        pump(2)
    return got.get("labels", [])


@timed("key")
def key(widget, k, mods=Qt.NoModifier, log=None, label=None):
    QTest.keyClick(widget, k, mods)
    pump(1)
    if log:
        log.step(label or f"key {k}", keys=1)


def type_into(widget, text: str, log=None):
    QTest.keyClicks(widget, text)
    pump(1)
    if log:
        log.step(f"type '{text}'", keys=len(text))


def focus_target(window):
    w = QApplication.focusWidget()
    return w or window.view.viewport()


# ---------------------------------------------------------------------------
# toolbars and panels
# ---------------------------------------------------------------------------
def toolbar_buttons(window) -> list[str]:
    out = []
    for bar in window.findChildren(QToolBar):
        if not bar.isVisible():
            continue
        for act in bar.actions():
            if act.isSeparator():
                continue
            out.append(f"{bar.windowTitle() or bar.objectName()}: "
                       f"{_clean(act.text())} [{act.toolTip()}]")
    return out


def toolbar_action(window, *words, exact=False):
    """Visible toolbar actions whose text (or tooltip) has one of *words*;
    with *exact*, the button's own name must equal a word."""
    hits = []
    for bar in window.findChildren(QToolBar):
        if not bar.isVisible():
            continue
        for act in bar.actions():
            name = _clean(act.text()).lower()
            text = (name + " " + act.toolTip()).lower()
            if exact and name in [w.lower() for w in words]:
                hits.append((bar, act))
            elif not exact and any(w.lower() in text for w in words):
                hits.append((bar, act))
    return hits


def click_toolbar(window, act, log=None, handler=None):
    """Click the tool button that shows *act*."""
    for bar in window.findChildren(QToolBar):
        btn = bar.widgetForAction(act)
        if isinstance(btn, QToolButton) and btn.isVisible():
            if log:
                log.step(f"toolbar '{_clean(act.text())}'", clicks=1)
            run_with_modal(lambda: QTest.mouseClick(btn, Qt.LeftButton), handler, 4000,
                           log, act.text())
            return True
    return False


def docks(window) -> list[str]:
    return [f"{d.windowTitle()} ({'shown' if d.isVisible() else 'hidden'})"
            for d in window.findChildren(QDockWidget)]


def make_pdf(path: str, pages: int = 4, size=(1190.55, 841.89)) -> str:
    """A small drawing set: a room outline on every page, some 'TBC' notes."""
    import fitz
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=size[0], height=size[1])
        page.draw_rect(fitz.Rect(200, 200, 600, 500), color=(0, 0, 0), width=2)
        page.insert_text((220, 180), f"ROOM {i + 1}  (1:100)", fontsize=14)
        page.insert_text((220, 540), "Wall height TBC", fontsize=11)
        if i % 2 == 0:
            page.insert_text((700, 300), "Beam size TBC by engineer", fontsize=11)
        page.insert_text((1000, 800), f"Sheet A-{101 + i}", fontsize=10)
    doc.save(path)
    doc.close()
    return path
