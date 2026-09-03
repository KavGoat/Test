"""A long randomised session against the real application.

    python tools/session_fuzz.py [seed] [rounds] [trace]

Picks tools, drags, clicks, double-clicks, types, deletes, undoes, changes
pages, pastes, rescales and prints — hundreds of times — then asks the verifier
whether the document still re-derives, and finally whether it still prints. It
reports anything that raised and any answer the page can no longer justify.

Everything modal is stubbed first: a randomised run must never sit waiting for
somebody to click OK. Runs are seeded, so a failure can be reproduced exactly,
and `trace` prints the gesture before and after each round so a crash can be
pinned to the one that caused it.

This found the crash while rendering a page thumbnail, the page insertion that
emptied the document, the move that did not recalculate, and the reading order
that was not a total order. It scrolls and zooms as well as drawing, because on
a canvas holding every page those are the gestures most likely to leave a
gesture aimed at the wrong page.
"""
import faulthandler, functools, os, random, sys, traceback
print = functools.partial(print, flush=True)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
faulthandler.enable()

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from calcforge.app import build_application
from calcforge.ui.mainwindow import MainWindow
from calcforge.ui.tools import TOOLS

SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 1
ROUNDS = int(sys.argv[2]) if len(sys.argv) > 2 else 400

# Nothing in a randomised run may sit waiting for a human.  Every modal way
# out of the application is stubbed before the window is built.
from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox
QDialog.exec = lambda self: QDialog.Rejected
QMessageBox.exec = lambda self: QMessageBox.Cancel
for _name in ("warning", "critical", "information", "about"):
    setattr(QMessageBox, _name, staticmethod(lambda *a, **k: QMessageBox.Ok))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))
QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: ([], ""))
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: "")
QInputDialog.getText = staticmethod(lambda *a, **k: ("", False))
QInputDialog.getMultiLineText = staticmethod(lambda *a, **k: ("", False))
QInputDialog.getInt = staticmethod(lambda *a, **k: (0, False))
QInputDialog.getDouble = staticmethod(lambda *a, **k: (0.0, False))
QInputDialog.getItem = staticmethod(lambda *a, **k: ("", False))

app = build_application([])
win = MainWindow()
win.confirm_discard = lambda: True
win.interactive_prompts = False
win.resize(1500, 980)
win.show()
QTest.qWaitForWindowExposed(win)
win.view.set_zoom(1.0)
rng = random.Random(SEED)
view = win.view

FAILURES = []


def guard(label):
    def wrap(fn):
        @functools.wraps(fn)
        def run(*a, **k):
            try:
                return fn(*a, **k)
            except Exception:
                FAILURES.append((label, traceback.format_exc()))
        return run
    return wrap


def vpos(x, y):
    return view.mapFromScene(QPointF(x, y))


def send(kind, pt, button=Qt.LeftButton, buttons=Qt.NoButton, mods=Qt.NoModifier):
    app.sendEvent(view.viewport(), QMouseEvent(
        kind, QPointF(pt), view.viewport().mapToGlobal(pt), button, buttons, mods))


def spot():
    """A point somewhere in the visible part of the canvas."""
    rect = view.mapToScene(view.viewport().rect()).boundingRect()
    return (rng.uniform(rect.left(), rect.right()),
            rng.uniform(rect.top(), rect.bottom()))


@guard("drag")
def do_drag():
    x0, y0 = spot()
    x1, y1 = x0 + rng.uniform(-200, 200), y0 + rng.uniform(-200, 200)
    a, b = vpos(x0, y0), vpos(x1, y1)
    send(QEvent.MouseButtonPress, a, buttons=Qt.LeftButton)
    for step in (0.4, 0.8, 1.0):
        send(QEvent.MouseMove, vpos(x0 + (x1 - x0) * step, y0 + (y1 - y0) * step),
             Qt.NoButton, Qt.LeftButton)
    send(QEvent.MouseButtonRelease, b)


@guard("click")
def do_click():
    p = vpos(*spot())
    send(QEvent.MouseButtonPress, p, buttons=Qt.LeftButton)
    send(QEvent.MouseButtonRelease, p)


@guard("double_click")
def do_double_click():
    p = vpos(*spot())
    for kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease,
                 QEvent.MouseButtonDblClick, QEvent.MouseButtonRelease):
        send(kind, p)


@guard("right_click")
def do_right_click():
    items = win.selected_items()
    menu = win.build_context_menu(items[0] if items else None, QPointF(*spot()))
    menu.deleteLater()


KEYS = [Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down, Qt.Key_Return,
        Qt.Key_Backspace, Qt.Key_Escape, Qt.Key_Tab, Qt.Key_Delete, Qt.Key_Home,
        Qt.Key_End, Qt.Key_F2]
TEXTS = ['"', "\\", "|", "@", "c", "r", "q", "m", "a", "p", "t", "b", "g", "e",
         "n", "s", "k", "l", "h"]
SNIPPETS = ["L = 6 m", "w = 12 kN/m", "M = w*L^2/8", "sigma = 275 MPa",
            "x = 3 in", "T = 20 degC", "q = 5 kPa", "r = 6 m / 200 mm",
            "bad = 1 m + 1 kN", "f(x) := x^2", "y = f(3 m)", "n = 4",
            "A = n*pi*(20 mm)^2/4", "# a note", "z = undefined_name*2"]


@guard("key")
def do_key():
    key = rng.choice(KEYS)
    mods = rng.choice([Qt.NoModifier, Qt.NoModifier, Qt.ShiftModifier, Qt.ControlModifier])
    app.sendEvent(view, QKeyEvent(QEvent.KeyPress, key, mods, ""))
    app.sendEvent(view, QKeyEvent(QEvent.KeyRelease, key, mods, ""))


@guard("typed")
def do_typed():
    ch = rng.choice(TEXTS)
    app.sendEvent(view, QKeyEvent(QEvent.KeyPress, Qt.Key_unknown, Qt.NoModifier, ch))
    app.sendEvent(view, QKeyEvent(QEvent.KeyRelease, Qt.Key_unknown, Qt.NoModifier, ch))


@guard("write")
def do_write():
    item = view.editing_item()
    if item is not None and getattr(item, "_editor", None) is not None:
        item._editor.setPlainText(rng.choice(SNIPPETS))
        view.end_item_edit()


@guard("tool")
def do_tool():
    win.select_tool(rng.choice([t.key for t in TOOLS]))


@guard("undo")
def do_undo():
    (win.undo_stack.undo if rng.random() < 0.6 else win.undo_stack.redo)()


@guard("page")
def do_page():
    roll = rng.random()
    if roll < 0.3 and len(win.document.pages) < 5:
        win.add_page()
    elif roll < 0.5 and len(win.document.pages) > 1:
        win.delete_page()
    else:
        win.go_to_page(rng.randrange(len(win.document.pages)))


@guard("clipboard")
def do_clipboard():
    roll = rng.random()
    if roll < 0.3:
        win.copy_selection()
    elif roll < 0.6:
        win.paste_items()
    elif roll < 0.8:
        win.duplicate_selection()
    else:
        QApplication.clipboard().setText("a\tb\n1 m\t2 kN")


@guard("chrome")
def do_chrome():
    """Panels, toolbars, themes and the layout — the window's own surface."""
    roll = rng.random()
    if roll < 0.15:
        dock = rng.choice(win.panels)
        dock.set_pinned(not dock.pinned)
    elif roll < 0.3:
        dock = rng.choice(win.panels)
        dock.setVisible(not dock.isVisibleTo(win))
    elif roll < 0.4:
        win.addDockWidget(rng.choice([Qt.LeftDockWidgetArea, Qt.RightDockWidgetArea,
                                      Qt.TopDockWidgetArea, Qt.BottomDockWidgetArea]),
                          rng.choice(win.panels))
    elif roll < 0.5:
        win.addToolBar(rng.choice([Qt.TopToolBarArea, Qt.LeftToolBarArea,
                                   Qt.RightToolBarArea, Qt.BottomToolBarArea]),
                       rng.choice(win.toolbars))
    elif roll < 0.6:
        win.lock_toolbars(rng.random() < 0.5)
    elif roll < 0.7:
        win.pin_all_panels(rng.random() < 0.5)
    elif roll < 0.8:
        win.toggle_theme(rng.random() < 0.5)
    elif roll < 0.9:
        win.visible_tools = {t.key for t in TOOLS if rng.random() < 0.6}
        win.apply_visible_tools()
    else:
        win.reset_layout()


@guard("shortcuts")
def do_shortcuts():
    """Rebind something, then make sure the canvas still agrees."""
    keys = ["j", "y", "z", "Alt+J", "Ctrl+Alt+U", ""]
    binding = rng.choice([b for b in win.shortcuts.bindings()
                          if b.kind in ("tool", "insert")])
    win.shortcuts.set_sequence(binding.action_id, rng.choice(keys))
    win.apply_shortcuts()


@guard("navigate")
def do_navigate():
    roll = rng.random()
    bar = view.verticalScrollBar()
    if roll < 0.3:
        bar.setValue(rng.randint(bar.minimum(), max(bar.maximum(), bar.minimum())))
    elif roll < 0.5:
        view.set_zoom(rng.choice([0.15, 0.35, 0.7, 1.0, 1.6, 3.0]))
    elif roll < 0.65:
        view.fit_page()
    elif roll < 0.8:
        view.fit_width()
    else:
        win.go_to_page(rng.randrange(len(win.document.pages)))


@guard("scale")
def do_scale():
    from calcforge.core.document import PageScale
    win.current_page().scale = (PageScale.from_ratio(rng.choice([20, 50, 100, 200]))
                                if rng.random() < 0.7 else PageScale())
    win.apply_scale_change()


@guard("recalc")
def do_recalc():
    win.recalculate()


@guard("toolset")
def do_toolset():
    """Keep things in tool sets, take them out again, and put them down."""
    from calcforge.ui import toolsets

    what = rng.random()
    items = [i for i in view.scene().markups()]
    if what < 0.3 and items:
        one = rng.choice(items)
        groups = toolsets.load_toolsets()
        group = rng.choice(groups)
        group.entries.append(toolsets.entry_for(
            one, rng.choice([toolsets.COPY, toolsets.PROPERTIES])))
        toolsets.save_toolsets(groups)
        win.toolsets_panel.rebuild()
    elif what < 0.5:
        groups = toolsets.load_toolsets()
        groups.append(toolsets.ToolSet(f"Set {rng.randint(1, 5)}"))
        toolsets.save_toolsets(groups)
        win.toolsets_panel.rebuild()
    elif what < 0.7:
        win.activate_my_tool(rng.randint(1, 9))
        do_click()
    elif what < 0.85:
        panel = win.toolsets_panel
        tree = panel.tree
        headers = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
        headers = [h for h in headers if h.childCount()]
        if headers:
            header = rng.choice(headers)
            header.setExpanded(rng.random() < 0.8)
            row = header.child(rng.randrange(header.childCount()))
            tree.setCurrentItem(row)
            rng.choice([panel.toggle_mode, panel.use_selected,
                        panel.remove_entry, panel.refresh_buttons,
                        lambda: panel.build_menu()])()
    else:
        view.clear_pending_tool()


@guard("group")
def do_group():
    """Group and ungroup whatever is selected, and set defaults from it."""
    items = [i for i in view.scene().markups()]
    if not items:
        return
    for one in rng.sample(items, min(len(items), rng.randint(1, 3))):
        one.setSelected(True)
    rng.choice([win.group_selection, win.ungroup_selection,
                lambda: win.set_as_default(rng.choice(items)),
                win.forget_defaults])()


ACTIONS = ([do_drag] * 12 + [do_click] * 4 + [do_double_click] * 4 +
           [do_right_click] * 2 + [do_key] * 4 + [do_typed] * 8 +
           [do_write] * 8 + [do_tool] * 8 + [do_undo] * 2 + [do_page] * 1 +
           [do_clipboard] * 2 + [do_scale] * 2 + [do_recalc] * 2 +
           [do_navigate] * 6 + [do_chrome] * 4 + [do_shortcuts] * 2 +
           [do_toolset] * 4 + [do_group] * 3)

TRACE = len(sys.argv) > 3 and sys.argv[3] == "trace"
for round_number in range(ROUNDS):
    action = rng.choice(ACTIONS)
    if TRACE:
        print(f"{round_number:4} {action.__name__} tool={view.current_tool().key} "
              f"page={win.current_index} editing={view.editing_item() is not None} "
              f"table={view.active_table is not None}")
    action()
    if TRACE:
        print(f"     ...done {action.__name__}")
    if round_number % 25 == 0:
        app.processEvents()
    if round_number % 100 == 99:
        try:
            view.end_item_edit()
            view.deactivate_table()
            result = win.verify_document(quiet=True)
            kinds = {}
            for problem in result.problems:
                kinds[problem.kind] = kinds.get(problem.kind, 0) + 1
            bad = [p for p in result.problems if p.kind == "disagreement"]
            if bad:
                detail = "\n".join(
                    f"  {p.item_name} {p.where}: {p.source!r} -> {p.message}"
                    for p in bad)
                FAILURES.append(("verify", f"round {round_number}:\n{detail}"))
        except Exception:
            FAILURES.append(("verify", traceback.format_exc()))

# and finally: does it still print?
try:
    view.end_item_edit()
    view.deactivate_table()
    import tempfile

    from calcforge.io import export as export_io
    path = os.path.join(tempfile.gettempdir(), f"session_fuzz_{SEED}.pdf")
    export_io.export_pdf(win.document, path)
    from PySide6.QtPdf import QPdfDocument
    doc = QPdfDocument()
    assert doc.load(path) == QPdfDocument.Error.None_
    assert doc.pageCount() == len(win.document.pages), (
        doc.pageCount(), len(win.document.pages))
except Exception:
    FAILURES.append(("print", traceback.format_exc()))

markups = sum(len(p.frame.markups()) for p in win.document.pages if p.frame)
print(f"seed {SEED}: {ROUNDS} rounds, {len(win.document.pages)} pages, "
      f"{markups} markups, {len(FAILURES)} failure(s)")
seen = set()
for label, detail in FAILURES:
    key = (label, detail.strip().splitlines()[-1] if detail.strip() else "")
    if key in seen:
        continue
    seen.add(key)
    print(f"\n=== {label} ===\n{detail}")
win.close()
app.quit()
