"""Feature inventory for the QA pass (docs/qa/QA_PLAN.md §1).

Builds the real MainWindow headless and walks everything a user can reach:
the menu bar (lazy submenus included), every toolbar, the status bar, every
panel and its header buttons, every right-click menu (built the way the app
builds them, with QMenu.exec captured instead of run), the dialogs, the
keyboard bindings and the mouse gestures. Each line is matched against the
test suite by grep, and placement smells are flagged mechanically.

    QT_QPA_PLATFORM=offscreen python tools/qa/inventory.py [out.md]

Writes docs/qa/feature_inventory.md by default. Changes nothing in the app.
"""
from __future__ import annotations

import ast
import os
import re
import sys
import tempfile
import traceback
from collections import Counter, OrderedDict, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
_SANDBOX = tempfile.mkdtemp(prefix="calcforge-inventory-")
for _v in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
    os.environ[_v] = os.path.join(_SANDBOX, _v.lower())
    os.makedirs(os.environ[_v], exist_ok=True)
os.environ["CALCFORGE_SETTINGS_FILE"] = os.path.join(_SANDBOX, "calcforge-inventory.ini")
os.environ["CALCFORGE_MARKFORGE_SETTINGS_FILE"] = os.path.join(_SANDBOX, "markforge-absent.ini")
sys.path.insert(0, ROOT)

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPoint, QPointF, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QAction, QContextMenuEvent, QKeySequence  # noqa: E402
from PySide6.QtWidgets import (QAbstractButton, QAbstractSpinBox, QApplication,  # noqa: E402
                               QCheckBox, QComboBox, QDialog, QFileDialog,
                               QFormLayout, QGroupBox, QInputDialog, QLabel,
                               QLineEdit, QMenu, QMessageBox, QPushButton,
                               QRadioButton, QToolBar, QToolButton, QWidget,
                               QWidgetAction, QColorDialog)

UI = os.path.join(ROOT, "calcforge", "ui")
TESTS = os.path.join(ROOT, "tests")
GAPS: list[str] = []          # what the walk could not reach, said in the output


# ---------------------------------------------------------------------------
# nothing modal may run: menus are captured, dialogs refused
# ---------------------------------------------------------------------------
CAPTURED: list[QMenu] = []


class _Closer(QObject):
    """Shiboken ignores a patched QMenu.exec on instances, so every popup menu
    or dialog that is shown is noted and closed on the next turn of its own
    event loop: exec() returns at once and the menu is left to be read."""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Show and isinstance(obj, QWidget) and obj.isWindow():
            if isinstance(obj, QMenu):
                CAPTURED.append(obj)
                QTimer.singleShot(0, obj.close)
            elif isinstance(obj, QDialog):
                QTimer.singleShot(0, obj.reject)
        return False


CLOSER = None


def install_closer(app) -> None:
    global CLOSER
    CLOSER = _Closer()
    app.installEventFilter(CLOSER)


QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))
QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: ([], ""))
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: "")
QInputDialog.getText = staticmethod(lambda *a, **k: ("", False))
QInputDialog.getItem = staticmethod(lambda *a, **k: ("", False))
QInputDialog.getInt = staticmethod(lambda *a, **k: (0, False))
QInputDialog.getDouble = staticmethod(lambda *a, **k: (0.0, False))
QColorDialog.getColor = staticmethod(lambda *a, **k: __import__("PySide6.QtGui").QtGui.QColor())
for _name in ("information", "warning", "question", "critical"):
    setattr(QMessageBox, _name, staticmethod(lambda *a, **k: QMessageBox.Cancel))


def take_captured() -> QMenu | None:
    menu = CAPTURED[-1] if CAPTURED else None
    CAPTURED.clear()
    return menu


# ---------------------------------------------------------------------------
# windows
# ---------------------------------------------------------------------------
APP = None


def pump(times: int = 2) -> None:
    for _ in range(times):
        APP.processEvents()


def new_window():
    from calcforge.ui.mainwindow import MainWindow
    main = MainWindow()
    main.confirm_discard = lambda: True
    main.interactive_prompts = False
    main.resize(1280, 860)
    main.show()
    main.activateWindow()
    main.view.set_zoom(1.0)
    pump()
    return main


def dispose(main) -> None:
    try:
        main.document.modified = False
        main.undo_stack.clear()
        main.view.setScene(None)
        for page in main.document.pages:
            page.frame = None
        main.close()
        main.setParent(None)
        main.deleteLater()
        pump(3)
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        pump()
    except Exception:          # noqa: BLE001 - a teardown problem is not an inventory one
        pass


# ---------------------------------------------------------------------------
# what the source says: action keys -> slot methods, labels -> methods
# ---------------------------------------------------------------------------
def _self_names(node) -> list[str]:
    """Method/attribute names reached through self/window/tables in *node*."""
    found = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute):
            found.append(sub.attr)
    return [n for n in found if not n.startswith("act_")]


GENERIC = {"window", "view", "tables", "scene", "document", "calc", "item", "menu",
           "self", "page", "frame", "panel", "list", "tree", "text", "pages",
           "selection", "settings", "style", "setChecked", "setEnabled", "addAction",
           "status_hint", "setText", "connect", "triggered", "toggled", "setSelected",
           "clearSelection", "sheet", "active", "name", "group", "groups", "row",
           "col", "index", "parentItem", "rows", "kind", "locked", "selected_items",
           "current_index", "bar", "pos", "x", "y", "mapToScene", "local_rect",
           "center", "setFocus", "PopupFocusReason", "triggered", "data", "get"}


SKIP_CALLS = {"setSelected", "clearSelection", "setFocus", "close", "leave", "setChecked",
              "isChecked", "selection", "list", "range", "len", "max", "min"}


def signature(slot) -> str:
    """What a slot does, without who it is called on: `insert_rows(below=True)`."""
    if isinstance(slot, ast.Attribute):
        return f"{slot.attr}()"
    if isinstance(slot, ast.Lambda):
        calls = []
        for sub in ast.walk(slot.body):
            if isinstance(sub, ast.Call):
                name = sub.func.attr if isinstance(sub.func, ast.Attribute) else getattr(
                    sub.func, "id", "")
                if not name or name in SKIP_CALLS:
                    continue
                args = ", ".join([ast.unparse(a) for a in sub.args]
                                 + [ast.unparse(k) for k in sub.keywords])
                calls.append(f"{name}({args})")
        params = {a.arg for a in slot.args.args}
        text = "; ".join(calls)
        if any(re.search(rf"\b{re.escape(p)}\b", text) for p in params if p != "_c"):
            return ""          # depends on the loop that built it: not one command
        return text
    return ""


def parse_sources():
    act_slots: dict[str, list[str]] = {}
    act_sigs: dict[str, str] = {}
    label_sigs: dict[str, set] = defaultdict(set)
    def_counts: Counter = Counter()
    label_methods: dict[str, set] = defaultdict(set)
    label_sites: dict[str, set] = defaultdict(set)
    func_calls: dict[str, set] = defaultdict(set)        # function -> self.X() it calls
    for name in sorted(os.listdir(UI)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(UI, name)
        tree = ast.parse(open(path, encoding="utf-8").read())
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                def_counts[fn.name] += 1
                for sub in ast.walk(fn):
                    if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                        func_calls[fn.name].add(sub.func.attr)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr == "_act" and len(node.args) >= 3 \
                    and isinstance(node.args[0], ast.Constant):
                slot = node.args[2]
                methods = [slot.attr] if isinstance(slot, ast.Attribute) else _self_names(slot)
                act_slots[node.args[0].value] = [m for m in methods if m not in GENERIC]
                act_sigs[node.args[0].value] = signature(slot)
            if node.func.attr in ("addAction", "addMenu"):
                label, rest = None, []
                for i, arg in enumerate(node.args):
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        label, rest = arg.value, node.args[i + 1:]
                        break
                if label is None:
                    continue
                label = clean(label)
                label_sites[label].add(name)
                if rest:
                    label_sigs[label].add(signature(rest[0]) if not (
                        isinstance(rest[0], ast.Call)) else "")
                for arg in rest:
                    for m in _self_names(arg):
                        if m not in GENERIC and not m[0].isupper():
                            label_methods[label].add(m)
                    if isinstance(arg, ast.Name) and arg.id not in GENERIC:
                        label_methods[label].add(arg.id)
    return act_slots, label_methods, label_sites, func_calls, act_sigs, label_sigs, def_counts


def clean(text: str) -> str:
    text = (text or "").replace("&&", "\0").replace("&", "").replace("\0", "&")
    return text.split("\t")[0].strip()


# ---------------------------------------------------------------------------
# rows
# ---------------------------------------------------------------------------
ROWS: list[dict] = []
MENUS: list[dict] = []        # raw menus, for the smell checks
SEEN = set()


def add_row(area, where, name, shortcut="", tokens=None, note="", key=None,
            enabled=True, checkable=False, dedupe=True):
    key = key or (area, where, name)
    if dedupe and key in SEEN:
        return None
    SEEN.add(key)
    row = dict(area=area, where=where, name=name, shortcut=shortcut,
               tokens=tokens or {}, note=note, enabled=enabled, checkable=checkable)
    ROWS.append(row)
    return row


class Ident:
    """Who an action or widget is, as the code names it."""

    def __init__(self, window):
        self.by_id = {}
        self.tool_by_id = {}
        for attr, value in vars(window).items():
            if isinstance(value, (QAction, QWidget)) and not attr.startswith("_"):
                self.by_id[id(value)] = attr
        for key, action in getattr(window, "tool_actions", {}).items():
            self.tool_by_id[id(action)] = key
        for key, actions in getattr(window, "insert_tool_actions", {}).items():
            for action in actions:
                self.tool_by_id[id(action)] = key

    def add_object(self, owner_name, obj):
        for attr, value in vars(obj).items():
            if isinstance(value, (QAction, QWidget)) and id(value) not in self.by_id \
                    and not attr.startswith("_"):
                self.by_id[id(value)] = f"{owner_name}.{attr}" if owner_name else attr


def action_tokens(action, ident, act_slots, label_methods, text):
    tokens = {"ident": [], "method": [], "text": [], "tool": [], "sig": []}
    attr = ident.by_id.get(id(action))
    if attr:
        tokens["ident"].append(attr)
        if attr.startswith("act_"):
            tokens["method"] += act_slots.get(attr[4:], [])
            if ACT_SIGS.get(attr[4:]):
                tokens["sig"] = [ACT_SIGS[attr[4:]]]
    elif text and len(LABEL_SIGS.get(text, ())) == 1 and next(iter(LABEL_SIGS[text])):
        tokens["sig"] = [next(iter(LABEL_SIGS[text]))]
    tool = ident.tool_by_id.get(id(action))
    if tool:
        tokens["tool"].append(tool)
    if not attr:
        tokens["method"] += sorted(label_methods.get(text, ()))
    if text:
        tokens["text"].append(text)
    return tokens


def shortcut_text(action) -> str:
    keys = [k.toString(QKeySequence.NativeText) for k in action.shortcuts() if not k.isEmpty()]
    return " / ".join(keys)


def walk_menu(menu, path, area, ident, sources, state="", rows=True, emit=True):
    """Every entry of *menu*, submenus included; lazy ones are asked to fill."""
    act_slots, label_methods = sources[0], sources[1]
    if emit:
        try:
            menu.aboutToShow.emit()
        except Exception as error:  # noqa: BLE001
            GAPS.append(f"{' ▸ '.join(path)}: aboutToShow raised {error!r}")
    entries = []
    for action in menu.actions():
        if action.isSeparator():
            entries.append(dict(sep=True))
            continue
        text = clean(action.text())
        if isinstance(action, QWidgetAction) and not text:
            widget = action.defaultWidget()
            fields = [widget] + widget.findChildren(QLineEdit) if widget is not None else []
            said = next((clean(getattr(f, "placeholderText", lambda: "")() or f.toolTip())
                         for f in fields if getattr(f, "placeholderText", lambda: "")()
                         or f.toolTip()), "")
            labels = widget.findChildren(QLabel) if widget is not None else []
            said = said or next((clean(lb.text()) for lb in labels if lb.text()), "")
            text = f"[field] {said}".strip()
        sub = action.menu()
        tokens = action_tokens(action, ident, act_slots, label_methods, text)
        entry = dict(sep=False, text=text, shortcut=shortcut_text(action),
                     enabled=action.isEnabled(), visible=action.isVisible(),
                     checkable=action.isCheckable(), sub=sub is not None,
                     ident=ident.by_id.get(id(action)), tool=ident.tool_by_id.get(id(action)),
                     methods=tokens["method"], sig=tokens["sig"])
        entries.append(entry)
        if not action.isVisible():
            continue
        if rows:
            flags = []
            if action.isCheckable():
                flags.append("toggle")
            if not action.isEnabled():
                flags.append("disabled" + (f" {state}" if state else ""))
            mirrored = MIRRORED.get(id(sub)) if sub is not None else None
            if mirrored:
                flags.append(mirrored)
            add_row(area, " ▸ ".join(path), text + (" ▸" if sub is not None else ""),
                    shortcut_text(action), tokens, note=", ".join(flags),
                    enabled=action.isEnabled())
        if sub is not None:
            walk_menu(sub, path + [text], area, ident, sources, state,
                      rows and not MIRRORED.get(id(sub)), emit)
    MENUS.append(dict(area=area, path=path, entries=entries,
                      collapsible=menu.separatorsCollapsible(), state=state))
    return entries


def describe_widget(widget) -> tuple[str, str]:
    """(kind, label) for a control."""
    kind = type(widget).__name__
    if isinstance(widget, QAbstractButton):
        label = clean(widget.text()) or clean(widget.toolTip().split("\n")[0])
        if isinstance(widget, QToolButton) and widget.defaultAction() is not None:
            label = clean(widget.defaultAction().text()) or label
    elif isinstance(widget, QLineEdit):
        label = clean(widget.placeholderText() or widget.toolTip().split("\n")[0])
    elif isinstance(widget, (QComboBox, QAbstractSpinBox)):
        label = clean(widget.toolTip().split("\n")[0]
                      or getattr(widget, "placeholderText", lambda: "")())
    else:
        label = clean(widget.toolTip().split("\n")[0])
    label = label.strip() or widget.objectName() or "(unlabelled)"
    return kind, label


def form_labels(root) -> dict:
    labels = {}
    for form in root.findChildren(QFormLayout):
        for r in range(form.rowCount()):
            label_item = form.itemAt(r, QFormLayout.LabelRole)
            field_item = form.itemAt(r, QFormLayout.FieldRole)
            if label_item is None or field_item is None:
                continue
            label = label_item.widget()
            field = field_item.widget()
            if isinstance(label, QLabel) and field is not None:
                labels[id(field)] = clean(label.text()).rstrip(":")
                for child in field.findChildren(QWidget):
                    labels.setdefault(id(child), clean(label.text()).rstrip(":"))
    for label in root.findChildren(QLabel):
        buddy = label.buddy()
        if buddy is not None:
            labels.setdefault(id(buddy), clean(label.text()).rstrip(":"))
    return labels


CONTROL_TYPES = (QAbstractButton, QComboBox, QAbstractSpinBox, QLineEdit)


def controls(root, only_visible=True):
    out = []
    for widget in root.findChildren(QWidget):
        if not isinstance(widget, CONTROL_TYPES):
            continue
        if isinstance(widget, QLineEdit) and isinstance(widget.parent(), (QComboBox,
                                                                           QAbstractSpinBox)):
            continue
        if widget.objectName() in ("qt_toolbar_ext_button", "qt_dockwidget_closebutton",
                                   "qt_dockwidget_floatbutton"):
            continue
        if type(widget).__name__ in ("QScrollBar",):
            continue
        if only_visible and not widget.isVisibleTo(root):
            continue
        out.append(widget)
    return out


def group_path(widget, root) -> list[str]:
    parts = []
    parent = widget.parentWidget()
    while parent is not None and parent is not root:
        if isinstance(parent, QGroupBox) and parent.title():
            parts.append(clean(parent.title()))
        title = getattr(parent, "title_text", None)
        if isinstance(title, str) and title:
            parts.append(title)
        parent = parent.parentWidget()
    return list(reversed(parts))


def walk_controls(area, where, root, ident, sources, collapse_at=14, state="",
                  labels=None, skip=()):
    labels = labels if labels is not None else form_labels(root)
    grouped = OrderedDict()
    for widget in controls(root):
        if any(widget is s or s.isAncestorOf(widget) for s in skip):
            continue
        kind, label = describe_widget(widget)
        label = labels.get(id(widget), label) if kind not in ("QToolButton", "QPushButton") \
            else label
        path = [where] + group_path(widget, root)
        grouped.setdefault(" ▸ ".join(path), []).append((widget, kind, label))
    for path, members in grouped.items():
        plain = [m for m in members if isinstance(m[0], QToolButton) and m[0].menu() is None
                 and ident.by_id.get(id(m[0])) is None]
        if len(plain) >= collapse_at:
            names = [m[2] for m in plain]
            add_row(area, path, f"{len(plain)} buttons: " + ", ".join(names[:18])
                    + (" …" if len(names) > 18 else ""), "",
                    {"text": names[:6]}, note="collapsed")
            members = [m for m in members if m not in plain]
        for widget, kind, label in members:
            attr = ident.by_id.get(id(widget))
            tokens = {"ident": [attr] if attr else [], "text": [label], "method": []}
            if widget.objectName():
                tokens["ident"].append(widget.objectName())
            action = widget.defaultAction() if isinstance(widget, QToolButton) else None
            shortcut = shortcut_text(action) if action is not None else ""
            if action is not None:
                a = ident.by_id.get(id(action))
                if a:
                    tokens["ident"].append(a)
                    if a.startswith("act_"):
                        tokens["method"] += sources[0].get(a[4:], [])
            kind_short = {"QToolButton": "button", "QPushButton": "button",
                          "QCheckBox": "check box", "QRadioButton": "option",
                          "QComboBox": "list", "QFontComboBox": "font list",
                          "QLineEdit": "field", "QSpinBox": "number",
                          "QDoubleSpinBox": "number"}.get(kind, kind)
            note = kind_short + (f", {state}" if state else "")
            if path == "Formula bar" and not widget.isEnabled():
                note += ", disabled here"     # Excel's ✗ and ✓, until a cell is typed in
            add_row(area, path, label, shortcut, tokens, note=note)
            menu = widget.menu() if isinstance(widget, (QToolButton, QPushButton)) else None
            if menu is not None:
                walk_menu(menu, [path, label], area, ident, sources, state)


def walk_toolbar(bar, ident, sources, state):
    area = "Toolbars"
    where = f"Toolbar {bar.windowTitle()}"
    for action in bar.actions():
        if action.isSeparator() or not action.isVisible():
            continue
        widget = bar.widgetForAction(action)
        if isinstance(action, QWidgetAction) or (widget is not None and not isinstance(
                widget, QToolButton)):
            target = action.defaultWidget() if isinstance(action, QWidgetAction) else widget
            if target is None:
                continue
            members = [target] if isinstance(target, CONTROL_TYPES) else controls(target)
            if isinstance(target, QLabel) and not members:
                continue
            for member in members:
                kind, label = describe_widget(member)
                attr = ident.by_id.get(id(member))
                tokens = {"ident": [attr] if attr else [], "text": [label]}
                add_row(area, where, label, "", tokens,
                        note=f"{kind.replace('Q', '', 1)}" + (f"; shown {state}" if state else ""),
                        key=(area, where, label, kind))
                menu = member.menu() if isinstance(member, (QToolButton, QPushButton)) else None
                if menu is not None:
                    walk_menu(menu, [where, label], area, ident, sources, state)
            continue
        text = clean(action.text()) or clean(action.toolTip().split("\n")[0])
        tokens = action_tokens(action, ident, sources[0], sources[1], text)
        flags = ["toggle"] if action.isCheckable() else []
        if state:
            flags.append(f"shown {state}")
        add_row(area, where, text, shortcut_text(action), tokens, note=", ".join(flags),
                key=(area, where, text))
        menu = action.menu() or (widget.menu() if isinstance(widget, QToolButton) else None)
        if menu is not None:
            walk_menu(menu, [where, text], area, ident, sources, state)


# ---------------------------------------------------------------------------
# the scenarios
# ---------------------------------------------------------------------------
def menubar(window, ident, sources, state="", rows=True):
    for top in window.menuBar().actions():
        menu = top.menu()
        if menu is None:
            continue
        name = clean(top.text())
        if name in ("Document",):
            pass
        walk_menu(menu, [name], "Menu bar", ident, sources, state, rows)


def draw_everything(window):
    """Draw one of each markup a tool can make, the way a user does."""
    from tests.test_usability import click, double_click, drag, markups, on_page, \
        press_key, type_text
    from calcforge.ui.tools import (ANCHOR, CLICK, CLOUD, CLOUDY, DRAG, FREE, POLY, TOOLS)
    skip = {"select", "pan", "eraser", "snapshot", "crop", "crop_image", "image",
            "calibrate", "viewport", "whiteout", "table", "cutout_polygon", "cutout_ellipse"}
    made = []
    slot = 0
    view = window.view
    for tool in TOOLS:
        log(f"  draw {tool.key}")
        if tool.key in skip or tool.mode not in (DRAG, POLY, CLICK, FREE, ANCHOR, CLOUDY, CLOUD):
            continue
        col, row = slot % 4, slot // 4
        slot += 1
        x0, y0 = 40 + col * 135, 40 + row * 80
        before = {id(i) for i in markups(window)}
        try:
            window.select_tool(tool.key)
            p = on_page(window, 0, x0, y0)
            q = on_page(window, 0, x0 + 90, y0 + 50)
            view.centerOn(QPointF(*p))
            pump(1)
            if tool.mode in (DRAG, FREE, CLOUDY):
                drag(view, p[0], p[1], q[0], q[1])
            elif tool.mode == POLY:
                click(view, p[0], p[1])
                click(view, q[0], p[1])
                double_click(view, q[0], q[1])
            elif tool.mode == CLICK:
                click(view, p[0], p[1])
            elif tool.mode == ANCHOR:
                click(view, p[0], p[1])
                click(view, q[0], q[1])
            elif tool.mode == CLOUD:
                drag(view, p[0], p[1], q[0], q[1])
                click(view, q[0] + 30, q[1] + 30)
            pump(1)
            if view._editing_item is not None:
                type_text(view, "x")
            press_key(view, Qt.Key_Escape)
            press_key(view, Qt.Key_Escape)
            window.select_tool("select")
        except Exception as error:  # noqa: BLE001
            GAPS.append(f"drawing with {tool.key}: {error!r}")
        new = [i for i in markups(window) if id(i) not in before]
        if not new:
            GAPS.append(f"drawing with tool '{tool.key}' made no markup headlessly; "
                        "its right-click menu is not listed")
        for item in new:
            made.append((tool, item))
    return made


def item_menu(window, item):
    window.view.scene().clearSelection()
    item.setSelected(True)
    pump(1)
    centre = item.mapToScene(item.local_rect().center()) if hasattr(item, "local_rect") \
        else item.sceneBoundingRect().center()
    return window.build_context_menu(item, centre)


def walk_flat(menu, where, ident, sources, state=""):
    """A menu's entries as (sub-path tuple, entry); its records go to MENUS
    under *where*, so the smells name the place a user would look."""
    start = len(MENUS)
    walk_menu(menu, [where], "Right-click menus", ident, sources, state, rows=False)
    flat = []
    for record in MENUS[start:]:
        for entry in record["entries"]:
            if not entry["sep"] and entry.get("visible", True):
                flat.append((tuple(record["path"][1:]), entry))
    return flat


def entry_tokens(entry):
    return {"ident": [entry["ident"]] if entry["ident"] else [],
            "tool": [entry["tool"]] if entry.get("tool") else [],
            "method": entry["methods"], "text": [entry["text"]], "sig": entry.get("sig", [])}


def rows_from_flat(where, flat, sources, note="", only=None):
    for sub, entry in flat:
        if only is not None and (sub, entry["text"]) not in only:
            continue
        flags = []
        if entry["checkable"]:
            flags.append("toggle")
        if not entry["enabled"]:
            flags.append("disabled here")
        if note:
            flags.append(note)
        add_row("Right-click menus", " ▸ ".join([where] + list(sub)),
                entry["text"] + (" ▸" if entry["sub"] else ""), entry["shortcut"],
                entry_tokens(entry), note=", ".join(flags))


# Every canvas item's right-click menu, gathered over all the scenarios and
# written once at the end: what every item offers, then each entry with the
# kinds of item that offer it.
ITEM_MENUS: "OrderedDict[str, list]" = OrderedDict()


def note_item_menu(label, menu, ident, sources):
    if label in ITEM_MENUS:
        return
    ITEM_MENUS[label] = walk_flat(menu, f"Canvas, {label}", ident, sources)


def item_menu_rows(sources):
    if not ITEM_MENUS:
        return
    keysets = {label: {(s, e["text"]) for s, e in flat} for label, flat in ITEM_MENUS.items()}
    common = set.intersection(*keysets.values())
    markups = [label for label in ITEM_MENUS if not label.startswith(("equation", "calculation",
                                                                       "table"))]
    markup_common = set.intersection(*(keysets[l] for l in markups)) - common if markups else set()
    first = next(iter(ITEM_MENUS.values()))
    rows_from_flat("Canvas, any item (markup, equation, block, table)", first, sources,
                   only=common)
    if markups:
        flat = ITEM_MENUS[markups[0]]
        rows_from_flat("Canvas, any markup (not equations or blocks)", flat, sources,
                       only=markup_common)
    owners = OrderedDict()
    entries = {}
    for label, flat in ITEM_MENUS.items():
        for s, e in flat:
            key = (s, e["text"])
            if key in common or (label in markups and key in markup_common):
                continue
            owners.setdefault(key, []).append(label)
            entries.setdefault(key, e)
    for (sub, text), labels in owners.items():
        names = [l.split(" (")[0] for l in labels]
        if len(names) > 6:
            where = f"Canvas, {len(names)} kinds ({', '.join(names[:4])}, …)"
        else:
            where = "Canvas, " + " / ".join(names)
        rows_from_flat(where, [(sub, entries[(sub, text)])], sources)


def right_click_at(window, x, y):
    from tests.test_usability import right_click
    CAPTURED.clear()
    right_click(window.view, x, y)
    pump(1)
    return take_captured()


def markup_scenarios(ident_for, sources):
    window = new_window()
    ident = ident_for(window)
    MIRRORED[id(window.current_page_menu)] = "same entries as a thumbnail's right-click menu"
    MIRRORED[id(window.selection_menu)] = "same entries as the selection's right-click menu"
    menubar(window, ident, sources, state="(fresh window)")
    for bar in window.findChildren(QToolBar):
        if bar.isVisible():
            walk_toolbar(bar, ident, sources, "")
    made = draw_everything(window)

    for tool, item in made:
        label = f"{tool.label} ({type(item).__name__}"
        label += f":{item.kind})" if getattr(item, "kind", "") else ")"
        try:
            note_item_menu(label, item_menu(window, item), ident, sources)
        except Exception as error:  # noqa: BLE001
            GAPS.append(f"right-click menu of {label}: {error!r}")

    # a multi-selection
    rects = [item for tool, item in made if tool.key in ("rect", "ellipse")]
    if len(rects) >= 2:
        window.view.scene().clearSelection()
        for item in rects[:2]:
            item.setSelected(True)
        pump(1)
        centre = rects[0].mapToScene(rects[0].local_rect().center())
        where = "Canvas, two shapes selected (entries beyond one rectangle's)"
        flat = walk_flat(window.build_context_menu(rects[0], centre), where, ident, sources)
        single = {(s, e["text"]) for s, e in ITEM_MENUS.get(next(
            (k for k in ITEM_MENUS if k.startswith("Rectangle")), ""), [])}
        rows_from_flat(where, flat, sources, only={(s, e["text"]) for s, e in flat} - single)
        menubar(window, ident, sources, state="(two selected)", rows=False)
    for tool, item in made:
        try:
            window.view.scene().clearSelection()
            item.setSelected(True)
            pump(1)
            walk_controls("Panels", "Properties", window.properties_panel, ident, sources)
            walk_toolbar(window.style_bar, ident, sources, "with a markup selected")
        except Exception as error:  # noqa: BLE001
            GAPS.append(f"Properties with {tool.key} selected: {error!r}")
    window.view.scene().clearSelection()
    pump(1)

    # the empty page, Markup mode — through the real right-click
    from tests.test_usability import on_page
    spot = on_page(window, 0, 520, 760)
    window.view.centerOn(QPointF(*spot))
    pump(1)
    menu = right_click_at(window, *spot) or window.build_context_menu(None, QPointF(*spot))
    where = "Canvas, empty page (Markup mode)"
    rows_from_flat(where, walk_flat(menu, where, ident, sources), sources)

    # the Markups list and its column filters
    panel = window.markups_panel
    try:
        panel.tree.selectAll()
        pump(1)
        where = "Markups List row"
        rows_from_flat(where, walk_flat(panel._row_menu(QPoint(5, 5)), where, ident, sources),
                       sources)
        for column, title in enumerate(panel.COLUMNS):
            if panel.filter_menu(column) is not None:
                add_row("Right-click menus", "Markups List column heading",
                        f"Filter {title}: (All) + a tick per value", "",
                        {"method": ["filter_menu", "set_column_filter"],
                         "text": [f"Filter {title}"]})
    except Exception as error:  # noqa: BLE001
        GAPS.append(f"Markups List menus: {error!r}")
    walk_controls("Panels", "Markups List", panel, ident, sources)

    # thumbnails / page menu: one page, then a run of two
    try:
        window.act_add_page.trigger()
        pump()
        menubar(window, ident, sources, state="(two pages)", rows=False)
        where = "Thumbnail (one page) — also Document ▸ Current Page"
        rows_from_flat(where, walk_flat(window.page_menu(0), where, ident, sources), sources)
        strip = window.pages_panel.list
        strip.clearSelection()
        for r in range(min(2, strip.count())):
            strip.item(r).setSelected(True)
        where = "Thumbnails (two pages picked out; entries that change)"
        flat = walk_flat(window.page_menu(0), where, ident, sources)
        single = {e["text"] for _s, e in walk_flat(window.page_menu(0), "(diff)", ident,
                                                   sources, state=DIFF_ONLY)}
        rows_from_flat(where, flat, sources,
                       only={(s, e["text"]) for s, e in flat if e["text"] not in single})
    except Exception as error:  # noqa: BLE001
        GAPS.append(f"page menu: {error!r}")

    # document tab, rulers, tool chest
    try:
        bar = window.document_tabs
        if bar.count():
            menu = window._tab_context_menu(bar.tabRect(0).center(), QMenu(window))
            rows_from_flat("Document tab", walk_flat(menu, "Document tab", ident, sources),
                           sources)
        else:
            GAPS.append("document tab bar had no tab")
    except Exception as error:  # noqa: BLE001
        GAPS.append(f"document tab menu: {error!r}")
    try:
        window.act_rulers.setChecked(True)
        pump()
        from calcforge.ui.rulers import Ruler
        for ruler in window.findChildren(Ruler)[:1]:
            CAPTURED.clear()
            ruler.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Mouse, QPoint(5, 5),
                                                     ruler.mapToGlobal(QPoint(5, 5))))
            menu = take_captured()
            if menu is not None:
                rows_from_flat("Ruler", walk_flat(menu, "Ruler", ident, sources), sources)
    except Exception as error:  # noqa: BLE001
        GAPS.append(f"ruler menu: {error!r}")
    try:
        chest = window.toolsets_panel
        for where, menu in (("Tool Chest ▸ Tool Sets button", chest.build_chest_menu()),
                            ("Tool Chest ▸ a set's gear button", chest.build_set_menu()),
                            ("Tool Chest ▸ a tool (right-click)", chest.build_menu())):
            rows_from_flat(where, walk_flat(menu, where, ident, sources), sources)
    except Exception as error:  # noqa: BLE001
        GAPS.append(f"tool chest menus: {error!r}")
    try:
        where = "Thumbnails ▸ Thumbnails ▾ (its title)"
        rows_from_flat(where, walk_flat(window.pages_panel.build_options_menu(), where,
                                        ident, sources), sources)
    except Exception as error:  # noqa: BLE001
        GAPS.append(f"thumbnails menu: {error!r}")

    # panels, header buttons
    for dock in window.panels:
        title = dock.windowTitle()
        bar = dock.titleBarWidget()
        # a panel's own header on its title bar (Thumbnails ▾ and its
        # buttons) is the panel's, walked with its controls below
        own = [getattr(bar, "header_title", None), getattr(bar, "header_tools", None)]
        own = [widget for widget in own if widget is not None]
        if bar is not None:
            for button in bar.findChildren(QToolButton):
                if any(button is widget or widget.isAncestorOf(button) for widget in own):
                    continue
                tip = clean(button.toolTip())
                method = {"collapse": "set_collapsed", "pin": "set_pinned",
                          "float": "setFloating", "close": "close"}
                tokens = {"text": [tip], "ident": [], "method": []}
                for attr in ("collapse", "pin", "float_button", "close_button"):
                    if getattr(bar, attr, None) is button:
                        tokens["raw"] = [f"titleBarWidget().{attr}"]
                add_row("Panels", f"{title} (title bar)", tip or button.objectName(), "",
                        tokens, note="header button")
        add_row("Panels", title, "(panel shown/hidden)", shortcut_text(dock.toggleViewAction()),
                {"ident": [dock.objectName()], "text": [title]})
        if dock.widget() is window.properties_panel:
            continue
        walk_controls("Panels", title, dock.widget(), ident, sources)
        tools = getattr(bar, "header_tools", None)
        if tools is not None:
            walk_controls("Panels", title, tools, ident, sources)

    # status bar, menu-bar corner
    walk_controls("Toolbars", "Status bar", window.statusBar(), ident, sources)
    corner = window.menuBar().cornerWidget()
    if corner is not None:
        walk_controls("Toolbars", "Menu-bar corner", corner, ident, sources)
    MIRRORED.clear()
    dispose(window)


DIFF_ONLY = "(diff only)"
MIRRORED: dict = {}


def table_scenarios(ident_for, sources):
    from tests.test_tables import make_table, cell_scene
    window = new_window()
    ident = ident_for(window)
    try:
        table = make_table(window)
        window.view.tables.open(table)
        pump()
        point = cell_scene(table, "B2")
        menu = right_click_at(window, point.x(), point.y())
        if menu is None:
            window.view.tables.context_menu(QPoint(0, 0))
            menu = take_captured()
        where = "Table cell (open table)"
        TABLE_FLAT[:] = walk_flat(menu, where, ident, sources)
        rows_from_flat(where, TABLE_FLAT, sources)
        ident.add_object("table_controls", window.table_controls)
        ident.add_object("formula_bar", window.formula_bar)
        walk_toolbar(window.style_bar, ident, sources, "with a table open")
        walk_controls("Toolbars", "Formula bar", window.formula_bar, ident, sources,
                      state="table open")
        menubar(window, ident, sources, state="(table open)", rows=False)
        window.view.tables.close()
        pump()
        note_item_menu("table (closed)", item_menu(window, table), ident, sources)
    except Exception as error:  # noqa: BLE001
        GAPS.append(f"table menus: {error!r}\n{traceback.format_exc(limit=3)}")
    dispose(window)


TABLE_FLAT: list = []


def sheet_scenarios(ident_for, sources):
    from tests.test_sheet_pages import sheet_page, open_at
    from tests.test_tables import cell_scene
    window = new_window()
    ident = ident_for(window)
    try:
        run = sheet_page(window)
        open_at(window, run, "C5")
        point = cell_scene(run, "C5")
        menu = right_click_at(window, point.x(), point.y())
        if menu is None:
            window.view.tables.context_menu(QPoint(0, 0))
            menu = take_captured()
        if menu is None:
            GAPS.append("the spreadsheet cell menu did not open headlessly")
        else:
            where = "Spreadsheet cell (entries beyond the table cell menu)"
            flat = walk_flat(menu, "Spreadsheet cell", ident, sources)
            table = {(s, e["text"]) for s, e in TABLE_FLAT}
            rows_from_flat(where, flat, sources,
                           only={(s, e["text"]) for s, e in flat} - table)
        sheet_tabs = window.sheet_tabs
        if sheet_tabs.bar.count():
            CAPTURED.clear()
            sheet_tabs._menu(sheet_tabs.bar.tabRect(0).center())
            menu = take_captured()
            if menu is not None:
                rows_from_flat("Sheet tab", walk_flat(menu, "Sheet tab", ident, sources),
                               sources)
        walk_controls("Toolbars", "Sheet tabs bar", sheet_tabs, ident, sources,
                      state="spreadsheet page")
        walk_toolbar(window.style_bar, ident, sources, "on a spreadsheet page")
        walk_controls("Toolbars", "Formula bar", window.formula_bar, ident, sources,
                      state="spreadsheet page")
        menubar(window, ident, sources, state="(sheet open)", rows=False)
    except Exception as error:  # noqa: BLE001
        GAPS.append(f"spreadsheet menus: {error!r}\n{traceback.format_exc(limit=3)}")
    dispose(window)


def calc_scenarios(ident_for, sources):
    from tests.test_calc_panels import an_equation
    from tests.test_usability import click, on_page, press_key, type_text
    window = new_window()
    ident = ident_for(window)
    try:
        window.toggle_calc_mode(True)
        pump()
        for bar in window.findChildren(QToolBar):
            if bar.isVisible():
                walk_toolbar(bar, ident, sources, "in Calc mode")
        menubar(window, ident, sources, state="(Calc mode)", rows=False)
        spot = on_page(window, 0, 400, 700)
        window.view.centerOn(QPointF(*spot))
        pump(1)
        menu = right_click_at(window, *spot) or window.build_context_menu(None, QPointF(*spot))
        where = "Canvas, empty page (Calc mode; entries beyond Markup mode's)"
        flat = walk_flat(menu, "Canvas, empty page (Calc mode)", ident, sources)
        markup_empty = {r["name"].rstrip(" ▸") for r in ROWS
                        if r["where"].startswith("Canvas, empty page (Markup")}
        rows_from_flat(where, flat, sources,
                       only={(s, e["text"]) for s, e in flat if e["text"] not in markup_empty})
        for name in sorted(markup_empty - {e["text"] for _s, e in flat}):
            add_row("Right-click menus", "Canvas, empty page (Calc mode)",
                    f"(no '{name}' here, unlike Markup mode)", "", {}, note="mode difference")
        window.toggle_calc_mode(False)
        pump()
        equation = an_equation(window, "a:2")
        pump()
        note_item_menu("equation", item_menu(window, equation), ident, sources)
        second = an_equation(window, "a+1=", 100, 200)
        window.view.scene().clearSelection()
        for item in (equation, second):
            item.setSelected(True)
        window.create_block()
        pump()
        from calcforge.items.calc import CalcBlockItem, CalcTextItem
        blocks = [i for i in window.view.scene().items() if isinstance(i, CalcBlockItem)]
        if blocks:
            note_item_menu("calculation block", item_menu(window, blocks[0]), ident, sources)
        else:
            GAPS.append("no calculation block was made headlessly")
        window.toggle_calc_mode(True)
        spot = on_page(window, 0, 100, 400)
        click(window.view, *spot)
        window.insert_calc_text()
        type_text(window.view, "Words")
        press_key(window.view, Qt.Key_Escape)
        press_key(window.view, Qt.Key_Escape)
        pump()
        texts = [i for i in window.view.scene().items() if isinstance(i, CalcTextItem)]
        if texts:
            note_item_menu("calculation text", item_menu(window, texts[0]), ident, sources)
        else:
            GAPS.append("no calculation text was made headlessly")
        panel = window.variables_panel
        pump()
        tree = panel.tree
        found = panel.first_row()         # (in a group: Blocks ▸ … opened to it)
        if found is not None:
            tree.scrollToItem(found)
            CAPTURED.clear()
            panel._menu(tree.visualItemRect(found).center())
            menu = take_captured()
            if menu is not None:
                rows_from_flat("Variables panel row",
                               walk_flat(menu, "Variables panel row", ident, sources), sources)
        else:
            GAPS.append("Variables panel had no row to right-click")
        for dock in window.panels:
            walk_controls("Panels", dock.windowTitle(), dock.widget(), ident, sources,
                          state="Calc mode")
    except Exception as error:  # noqa: BLE001
        GAPS.append(f"calc menus: {error!r}\n{traceback.format_exc(limit=4)}")
    dispose(window)


# ---------------------------------------------------------------------------
# dialogs, keys and the mouse
# ---------------------------------------------------------------------------
def dialogs(menu_rows_by_method):
    found = []
    classes = {}
    for name in sorted(os.listdir(UI)):
        if not name.endswith(".py"):
            continue
        tree = ast.parse(open(os.path.join(UI, name), encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases = [b.id if isinstance(b, ast.Name) else getattr(b, "attr", "")
                         for b in node.bases]
                if any(b in ("QDialog",) or b in classes for b in bases):
                    classes[node.name] = (name, node)
    callers = defaultdict(set)
    inline = []
    for name in sorted(os.listdir(UI)):
        if not name.endswith(".py"):
            continue
        tree = ast.parse(open(os.path.join(UI, name), encoding="utf-8").read())
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for sub in ast.walk(fn):
                if not isinstance(sub, ast.Call):
                    continue
                called = sub.func.id if isinstance(sub.func, ast.Name) else getattr(
                    sub.func, "attr", "")
                if called in classes:
                    callers[called].add(fn.name)
                if called == "QDialog":
                    title = _title_in(fn)
                    inline.append((name, fn.name, title, _fields_in(fn)))
                if called in ("getText", "getItem", "getInt", "getDouble", "getMultiLineText") \
                        and isinstance(sub.func, ast.Attribute) and getattr(
                            sub.func.value, "id", "") == "QInputDialog":
                    title = ""
                    if len(sub.args) >= 2 and isinstance(sub.args[1], ast.Constant):
                        title = sub.args[1].value
                    elif len(sub.args) >= 2 and isinstance(sub.args[1], ast.IfExp):
                        title = " / ".join(
                            a.value for a in (sub.args[1].body, sub.args[1].orelse)
                            if isinstance(a, ast.Constant))
                    inline.append((name, fn.name, title or "(input box)", 1))
    for cls, (module, node) in sorted(classes.items(), key=lambda kv: (kv[1][0], kv[0])):
        title = _title_in(node)
        openers = sorted(callers.get(cls, ()))
        found.append(dict(module=module, name=cls, title=title, fields=_fields_in(node),
                          openers=openers))
    for module, fn, title, fields in inline:
        found.append(dict(module=module, name=f"{fn}()", title=title, fields=fields,
                          openers=[fn]))
    return found


def _title_in(node) -> str:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and getattr(sub.func, "attr", "") == "setWindowTitle" \
                and sub.args:
            arg = sub.args[0]
            if isinstance(arg, ast.Constant):
                return arg.value
            if isinstance(arg, ast.JoinedStr):
                return "".join(v.value if isinstance(v, ast.Constant) else "{…}"
                               for v in arg.values)
            if isinstance(arg, ast.IfExp):
                return " / ".join(a.value for a in (arg.body, arg.orelse)
                                  if isinstance(a, ast.Constant))
            return "(computed)"
    return ""


def _fields_in(node) -> int:
    count = 0
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            called = sub.func.id if isinstance(sub.func, ast.Name) else getattr(sub.func, "attr", "")
            if called in ("QLineEdit", "QSpinBox", "QDoubleSpinBox", "QComboBox", "QCheckBox",
                          "QRadioButton", "QPlainTextEdit", "QTextEdit", "QFontComboBox",
                          "ColorButton", "QKeySequenceEdit", "QSlider", "UnitBox",
                          "QListWidget", "QTableWidget", "QTreeWidget"):
                count += 1
    return count


VIEW_KEYS = [
    # (keys, what, scope, coverage tokens: "w:word", "fn:test-name-prefix", "raw|also")
    ("Space (hold)", "Pan while held", "both", ["Key_Space"]),
    ("Esc", "Finish typing / drop the tool / clear the selection", "both", ["Key_Escape"]),
    ("Enter", "Close the polygon/polyline being clicked out; close a Shift lasso", "Markup",
     ["Key_Return|lasso", "Key_Return|poly", "Key_Enter"]),
    ("Delete / Backspace", "Delete the selection", "both", ["Key_Delete", "Key_Backspace"]),
    ("Arrows", "Nudge the selection (equations: one grid step); move the insertion cross",
     "both", ["fn:test_nudge", "Key_Left", "Key_Down"]),
    ("Shift+Arrows", "Nudge by 1 pt", "both", ["Key_Left|ShiftModifier",
                                               "Key_Down|ShiftModifier",
                                               "Key_Right|ShiftModifier"]),
    ("PgUp / PgDn", "Scroll a screenful", "both", ["Key_PageDown", "Key_PageUp"]),
    ("Home / End", "First / last page (Revu)", "both", ["Key_Home", "Key_End"]),
    ("Ctrl+Home / Ctrl+End", "Very start / end of the document", "both",
     ["fn:test_ctrl_home_and_end"]),
    ("1 … 9", "Use the n-th tool in My Tools", "Markup", ["w:activate_my_tool",
                                                         "fn:test_my_tools_are_numbered"]),
    ("Ctrl (held while dragging)", "Snapping off during a move", "both",
     ["fn:test_ctrl_turns_snapping_off", "Key_Control"]),
    ("Shift (held)", "Constrain angle/ratio while drawing or moving", "both",
     ["fn:test_shift_draws_a_straight", "Key_Shift"]),
    ("Ctrl+B / Ctrl+I / Ctrl+U", "In a text markup: bold / italic / underline the words",
     "while typing", ["fn:test_no_command_fires_from_ctrl_b_i_or_u_while_typing"]),
]

MOUSE = [
    # (gesture, where, what, coverage tokens)
    ("Wheel", "canvas", "Zoom at the pointer (a preference makes it scroll); page-by-page "
     "layouts turn pages", ["fn:test_a_wheel_notch_glides", "fn:test_a_plain_wheel"]),
    ("Ctrl+Wheel", "canvas", "The opposite of the plain wheel", [
        "fn:test_ctrl_does_the_opposite_of_whatever_the_wheel"]),
    ("Shift+Wheel", "canvas", "Scroll sideways", ["wheel(|ShiftModifier",
                                                   "wheel_at(|ShiftModifier"]),
    ("Two-finger scroll", "canvas", "Scroll both ways (pixel deltas)", ["pixels=True"]),
    ("Middle-button drag", "canvas", "Pan", ["w:MiddleButton"]),
    ("Space + drag / Pan tool", "canvas", "Pan", ["w:_space_pan", "select_tool(\"pan\")",
                                                   "fn:test_pan_"]),
    ("Drag on bare paper", "canvas (Select)", "Box select: rightwards takes what is wholly "
     "inside, leftwards what it crosses", ["fn:test_dragging_right_takes_only",
                                           "fn:test_dragging_left_takes"]),
    ("Shift+click on bare paper", "canvas (Select)", "Lasso: click corners; Enter or "
     "right-click closes", ["fn:test_a_lasso_takes"]),
    ("Click", "markup", "Select it", ["fn:test_click_selects_and_click_away"]),
    ("Shift+click", "markup", "Add to or take from the selection",
     ["fn:test_shift_click_adds"]),
    ("Ctrl+click", "markup", "Add to the selection", ["click(|ControlModifier"]),
    ("Drag", "markup", "Move it (Shift keeps it straight)", ["fn:test_dragging_moves_a_markup"]),
    ("Ctrl+drag", "markup", "Copy it (Revu); Ctrl pressed mid-move turns snapping off",
     ["fn:test_ctrl_dragging_a_copy"]),
    ("Drag onto another page", "markup", "It moves to that page",
     ["fn:test_a_markup_dragged_onto_the_next_page"]),
    ("Drag a handle", "selected markup", "Resize; move a vertex, leader, arc bulge or "
     "rounded corner", ["fn:test_a_rounded_corner_preview_updates_during_a_real_handle_drag",
                        "fn:test_handles_present"]),
    ("Drag the group box", "several selected", "Resize them together (Shift frees the ratio)",
     ["fn:test_a_group_scales_as_one"]),
    ("Shift/Ctrl+click a point or side", "outline", "Add or remove a vertex",
     ["fn:test_ctrl_click", "fn:test_shift_click_on_a_side", "fn:test_a_click_with_shift"]),
    ("Shift+drag a dimension's number", "dimension", "Pull the words onto a leader",
     ["fn:test_dragging_the_dot_with_the_mouse_pulls"]),
    ("Double-click", "text box / callout", "Edit the words (again: select a word)",
     ["fn:test_a_double_click_in_the_words"]),
    ("Double-click", "note", "Read and change what it says",
     ["fn:test_double_clicking_a_note"]),
    ("Double-click", "polyline / polygon / area", "Add a vertex",
     ["fn:test_double_clicking_an_area_measurement_adds_a_vertex"]),
    ("Double-click", "dimension / length", "Type on the measurement",
     ["fn:test_double_clicking_a_dimension_types_on_it"]),
    ("Double-click", "table", "Open its cells; in an open table, edit the cell",
     ["double=True", "fn:test_markup_mode_click_selects_and_double_click_opens"]),
    ("Double-click", "chart", "Chart dialog", ["fn:test_double_click_opens_the_chart_dialog"]),
    ("Double-click", "closed calculation block", "Open it, cursor inside",
     ["fn:test_double_click_opens_the_block"]),
    ("Double-click", "equation", "Cursor where it was clicked",
     ["fn:test_a_double_click_lands_where_it_was_aimed"]),
    ("Double-click", "link", "Follow it", ["w:follow_link"]),
    ("Click", "contents line", "Follow it", ["fn:test_a_contents_line"]),
    ("Click / drag (Format Painter held)", "markup / paper", "Paint the held look; a drag "
     "paints everything inside", ["fn:test_dragging_round_markups_paints_them_all"]),
    ("Right-click", "half-drawn polygon or cloud", "Close the shape",
     ["fn:test_a_right_click_finishes_the_cloud", "fn:test_a_right_click_closes_a_lasso"]),
    ("Drag", "thumbnail", "Reorder pages; a run moves together",
     ["fn:test_a_run_of_pages_is_dragged_as_a_run"]),
    ("Drag file", "thumbnail strip", "Insert a dropped PDF at that row",
     ["fn:test_a_dropped_pdf_is_imported"]),
    ("Drag", "document tab onto the other split pane", "Move the document there",
     ["fn:test_dragging_a_split_panes_other_document_across"]),
    ("Drag", "panel title bar / rail icon", "Move or float a panel (not when pinned)",
     ["fn:test_a_panel_dragged_to_the_other_rail", "fn:test_a_panel_can_go_to_any_edge"]),
    ("Double-click", "panel title bar", "Float / dock the panel",
     ["fn:test_double_clicking_the_title"]),
    ("Double-click", "Markups List handle", "Hide / show the list",
     ["fn:test_double_clicking_the_markups_lists_handle"]),
    ("Drag", "toolbar grip", "Move a toolbar (top or bottom)",
     ["fn:test_a_toolbar_has_a_grip"]),
    ("Drag", "window edge (frameless)", "Resize the window", ["w:_ResizesTheWindow"]),
    ("Drag", "empty menu-bar space", "Move the window", ["w:_MovesTheWindow"]),
    ("Click / drag", "cells", "Select cells", ["w:cell_scene"]),
    ("Drag", "row/column heading border", "Resize; double-click fits",
     ["fn:test_dragging_a_heading_border_resizes"]),
    ("Drag", "selection border", "Move the cells", ["fn:test_dragging_the_selection_border"]),
    ("Drag", "fill handle", "AutoFill a series or formulas",
     ["fn:test_fill_handle_continues", "fn:test_fill_handle_copies"]),
    ("Drag", "table corner", "Add rows and columns", ["fn:test_dragging_the_corner_adds_rows"]),
]


# ---------------------------------------------------------------------------
# coverage
# ---------------------------------------------------------------------------
class TestIndex:
    """The test suite, indexed by word and by quoted string, so each lookup is
    a dictionary hit and not a scan of 37 000 lines."""

    WORD = re.compile(r"[A-Za-z_]\w*")
    QUOTED = re.compile(r"\"([^\"\n]{1,120})\"|'([^'\n]{1,120})'")

    def __init__(self):
        self.files = {}
        self.words = defaultdict(list)
        self.quoted = defaultdict(list)
        self.tests = []                     # (rel, name, start, end)
        for folder, _dirs, files in os.walk(TESTS):
            for name in sorted(files):
                if not (name.endswith(".py") and name.startswith("test_")):
                    continue
                path = os.path.join(folder, name)
                text = open(path, encoding="utf-8").read()
                rel = os.path.relpath(path, ROOT)
                lines = text.split("\n")
                owner = [None] * (len(lines) + 2)
                try:
                    tree = ast.parse(text)
                    spans = sorted((n.lineno, n.end_lineno, n.name) for n in ast.walk(tree)
                                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
                    for begin, finish, func in spans:
                        for i in range(begin, finish + 1):
                            owner[i] = func
                        if func.startswith("test"):
                            self.tests.append((rel, func, begin, finish))
                except SyntaxError:
                    pass
                self.files[rel] = (lines, owner)
                for i, line in enumerate(lines, 1):
                    for word in set(self.WORD.findall(line)):
                        self.words[word].append((rel, i))
                    for a, b in self.QUOTED.findall(line):
                        self.quoted[a or b].append((rel, i))
        self.cache = {}
        self.callers = {}

    def _tests_for(self, rel, i):
        lines, owner = self.files[rel]
        func = owner[i]
        if func is None:
            return None
        if func.startswith("test"):
            return f"{rel}::{func}"
        key = (rel, func)
        if key not in self.callers:
            found = None
            for other_rel, j in self.words.get(func, ()):
                if other_rel != rel:
                    continue
                caller = owner[j]
                if caller and caller.startswith("test") and f"{func}(" in lines[j - 1]:
                    found = f"{rel}::{caller}"
                    break
            self.callers[key] = found
        return self.callers[key]

    def _collect(self, places, test_line):
        hits = []
        for rel, i in places:
            if test_line(self.files[rel][0][i - 1]):
                hit = self._tests_for(rel, i)
                if hit:
                    hits.append(hit)
        return list(OrderedDict.fromkeys(hits))

    def word(self, word, test_line=lambda line: True, tag=""):
        key = ("w", word, tag)
        if key not in self.cache:
            self.cache[key] = self._collect(self.words.get(word, ()), test_line)
        return self.cache[key]

    def string(self, text, test_line=lambda line: True, tag=""):
        key = ("q", text, tag)
        if key not in self.cache:
            self.cache[key] = self._collect(self.quoted.get(text, ()), test_line)
        return self.cache[key]

    def raw(self, spec):
        """'substring|also|also': lines holding every part."""
        parts = spec.split("|")
        words = sorted(self.WORD.findall(parts[0]), key=len, reverse=True)
        if not words:
            return []
        return self.word(words[0], lambda line: all(p in line for p in parts), tag=spec)

    def named(self, prefix):
        return [f"{rel}::{name}" for rel, name, _b, _e in self.tests if name.startswith(prefix)]

    def body_has(self, hit, needles) -> bool:
        rel, name = hit.split("::")
        for r, n, begin, end in self.tests:
            if r == rel and n == name:
                text = "\n".join(self.files[rel][0][begin - 1:end])
                return any(needle in text for needle in needles)
        return False


GENERIC_METHODS = {"paste", "close", "clear", "delete", "select", "update", "refresh",
                   "rebuild", "trigger", "insert", "remove", "rename", "merge", "hide",
                   "copy", "open", "show", "sort", "filter", "apply", "go", "fill",
                   "autofit", "distribute", "set_size", "toggle", "lambda", "go_to_page",
                   "setFloating"}
EXERCISE = (".trigger(", ".toggle(", ".setChecked(", ".click(", "keyClick", "activate(",
            "mouseClick", "clicked.emit", "triggered.emit")


def coverage(row, index: TestIndex) -> str:
    """The first test that exercises it; `≈` when a test only names it."""
    t = row["tokens"]
    named = []
    for ident in t.get("ident", []):
        if not ident:
            continue
        owner, _dot, attr = ident.rpartition(".")
        owner_word = owner.split(".")[-1]
        hits = index.word(attr, (lambda line, o=owner_word: o in line) if owner else
                          (lambda line: True), tag=owner)
        strong = index.word(attr, (lambda line, o=owner_word, a=attr: (not o or o in line)
                                   and (any(e in line for e in EXERCISE) or f"{a}(" in line)),
                            tag=owner + "+exercise")
        if strong:
            return _fmt(strong)
        named += hits
    for tool in t.get("tool", []):
        hits = index.string(tool, lambda line: "select_tool(" in line or "set_tool(" in line,
                            tag="tool")
        if hits:
            return _fmt(hits)
    for method in t.get("method", []):
        if method and len(method) >= 5 and method not in GENERIC_METHODS:
            hits = index.word(method, lambda line, m=method: f".{m}(" in line, tag="call")
            if hits:
                return _fmt(hits)
    for action_id in t.get("action_id", []):
        hits = index.string(action_id)
        if hits:
            return _fmt(hits)
    for spec in t.get("raw", []):
        if spec.startswith("fn:"):
            hits = index.named(spec[3:])
        elif spec.startswith("w:"):
            hits = index.word(spec[2:])
        else:
            hits = index.raw(spec)
        if hits:
            return _fmt(hits)
    if named:
        return "≈ " + _fmt(list(OrderedDict.fromkeys(named)))
    for text in t.get("text", []):
        if text and len(text) >= 3 and not text.startswith("["):
            for option in OrderedDict.fromkeys([text, text.rstrip("…").rstrip(".")]):
                hits = index.string(option)
                if hits:
                    return "≈ " + _fmt(hits)
    return "UNTESTED"


def _fmt(hits):
    first = hits[0].replace("tests/", "")
    return first + (f" (+{len(hits) - 1})" if len(hits) > 1 else "")


def key_coverage(sequence: str, index: TestIndex, context=()):
    """A test that presses this key: Key_X on one line with its modifiers (and,
    for a tool key, a test that is about that tool)."""
    for part in (sequence or "").split(","):
        part = part.strip()
        seq = QKeySequence(part)
        if seq.isEmpty():
            continue
        combo = seq[0]
        try:
            name = Qt.Key(combo.key()).name
        except Exception:  # noqa: BLE001
            continue
        if isinstance(name, bytes):
            name = name.decode()
        mods = combo.keyboardModifiers()
        need = [m for m, flag in (("Control", Qt.ControlModifier), ("Shift", Qt.ShiftModifier),
                                  ("Alt", Qt.AltModifier)) if mods & flag]
        avoid = [f"{m}Modifier" for m in ("Control", "Shift", "Alt") if m not in need]

        def pressed(line, need=need, avoid=avoid):
            return all(n in line for n in need) and not any(a in line for a in avoid)

        hits = index.word(name, pressed, tag="key" + "+".join(need))
        if context:
            hits = [h for h in hits if index.body_has(h, context)]
        if hits:
            return hits
        hits = index.string(part)
        if hits:
            return hits
    return []


# ---------------------------------------------------------------------------
# smells
# ---------------------------------------------------------------------------
SMALL = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "of", "on", "or",
         "the", "to", "with", "per", "vs", "via", "up", "off", "out", "it", "its", "is", "than"}
US_UK = [("Color", "Colour"), ("color", "colour"), ("Center", "Centre"),
         ("center", "centre"), ("Gray", "Grey"), ("gray", "grey"),
         ("Customize", "Customise"), ("customize", "customise"),
         ("Organize", "Organise"), ("Normalize", "Normalise"), ("Favorite", "Favourite"),
         ("Behavior", "Behaviour"), ("behavior", "behaviour"), ("Meter", "Metre"),
         ("Centimeter", "Centimetre"), ("Millimeter", "Millimetre"), ("meter", "metre"),
         ("Analyze", "Analyse"), ("Optimize", "Optimise"), ("Recognize", "Recognise"),
         ("Colorize", "Colourise"), ("colorize", "colourise"), ("Grayscale", "Greyscale"),
         ("Canceled", "Cancelled"), ("Labeled", "Labelled"), ("Dialog", "Dialogue"),
         ("Counterclockwise", "Anticlockwise"), ("counterclockwise", "anticlockwise")]
GROUP_VERBS = {"Insert", "Delete", "Clear", "Paste", "Merge", "Align", "Arrange", "Export",
               "Import", "Rotate", "Hide", "Unhide", "Sort", "Filter", "Format", "Names",
               "Remove", "Show", "Select"}
PLACEHOLDER = re.compile(r"^(No |Nothing|\(no )")


def case_style(text: str) -> str:
    words = [w for w in re.split(r"[\s/]+", re.sub(r"[…().,:'\"?▸+\-0-9&%]", " ", text)) if w]
    words = [w for w in words if w.isalpha() and not (len(w) > 1 and w.isupper())]
    if len(words) < 2:
        return "single"
    significant = [w for w in words[1:] if w.lower() not in SMALL]
    if not significant:
        return "single"
    if all(w[0].isupper() for w in significant):
        return "title"
    if all(w[0].islower() for w in significant):
        return "sentence"
    return "mixed"


def norm(name: str) -> str:
    return name.rstrip(" ▸").rstrip("…").strip()


class Smells:
    """Smells, folded together when the same one turns up in many menus."""

    def __init__(self):
        self.found = OrderedDict()      # (category, message) -> [priority, set(places)]

    def add(self, priority, category, message, place=""):
        entry = self.found.setdefault((category, message), [priority, []])
        if place and place not in entry[1]:
            entry[1].append(place)

    def listed(self):
        out = []
        for (category, message), (priority, places) in self.found.items():
            if places:
                shown = ", ".join(places[:3]) + (f" and {len(places) - 3} more"
                                                 if len(places) > 3 else "")
                message = f"{message} — in {shown}"
            out.append((priority, category, message, len(places)))
        return sorted(out, key=lambda s: (s[0], -s[3]))


def menu_records():
    """Each distinct menu once, with every place it was seen."""
    seen = OrderedDict()
    for record in MENUS:
        if record["state"] == DIFF_ONLY:
            continue
        texts = tuple(None if e["sep"] else e["text"] for e in record["entries"]
                      if e["sep"] or e.get("visible", True))
        key = (record["area"], tuple(record["path"][1:]), texts)
        if key not in seen:
            seen[key] = dict(record, roots=[record["path"][0]])
        elif record["path"][0] not in seen[key]["roots"]:
            seen[key]["roots"].append(record["path"][0])
    return list(seen.values())


def find_smells():
    smells = Smells()
    records = menu_records()
    for record in records:
        sub = " ▸ ".join(record["path"][1:])
        place = " / ".join(r for r in record["roots"][:1])
        here = lambda: " ▸ ".join([record["roots"][0]] + record["path"][1:])  # noqa: E731
        entries = [e for e in record["entries"] if e["sep"] or e.get("visible", True)]
        items = [e for e in entries if not e["sep"]]
        if not items:
            smells.add(4, "empty submenu", f"'{sub or record['path'][0]}' has nothing in it",
                       place)
            continue
        for a, b in zip(entries, entries[1:]):
            if a["sep"] and b["sep"]:
                smells.add(9, "double separator (Qt hides it)" if record["collapsible"]
                           else "double separator", f"{sub or '(top level)'}", place)
                break
        styles = {e["text"]: case_style(e["text"]) for e in items}
        counted = Counter(s for s in styles.values() if s in ("title", "sentence"))
        if counted["title"] and counted["sentence"]:
            minority = "sentence" if counted["title"] >= counted["sentence"] else "title"
            odd = [t for t, s in styles.items() if s == minority]
            majority = counted["title" if minority == "sentence" else "sentence"]
            smells.add(5, "case",
                       f"{here()}: {', '.join(repr(o) for o in odd[:5])} "
                       f"{'are' if len(odd) > 1 else 'is'} {minority} case beside "
                       f"{majority} {'Title Case' if minority == 'sentence' else 'sentence-case'}"
                       " siblings")
    # related commands outside their group
    trees = defaultdict(list)
    for record in records:
        for root in record["roots"]:
            trees[(record["area"], root)].append(record)
    for (area, root), members in trees.items():
        groups = {}
        for record in members:
            for e in record["entries"]:
                if not e["sep"] and e["sub"] and e["text"] in GROUP_VERBS:
                    groups.setdefault(e["text"], record["path"][1:] + [e["text"]])
        for record in members:
            inside = record["path"][1:]
            for e in record["entries"]:
                if e["sep"]:
                    continue
                verb = e["text"].split(" ")[0]
                home = groups.get(verb)
                if home and e["text"] != verb and inside[:len(home)] != home:
                    where = " ▸ ".join(inside + [e["text"]])
                    priority = {"Insert": 0, "Delete": 1, "Clear": 1, "Paste": 1}.get(verb, 2)
                    smells.add(priority, "split group",
                               f"'{where}' lives outside the '{' ▸ '.join(home)} ▸' group",
                               root)
    # the same command under different names, and a key shown in one place only
    by_command = defaultdict(list)
    for row in ROWS:
        if row["area"] in ("Keys", "Mouse", "Dialogs"):
            continue
        name = norm(row["name"])
        if not name or name.startswith(("(", "[")) or row["name"].endswith("▸") \
                or row["note"].startswith("value list"):
            continue
        ident = next((i for i in row["tokens"].get("ident", []) if i.startswith("act_")), None)
        sig = (row["tokens"].get("sig") or [None])[0]
        command = ident and ACT_SIGS.get(ident[4:]) or sig
        if command:
            by_command[command].append(row)
    for command, rows in by_command.items():
        names = OrderedDict()
        for row in rows:
            names.setdefault(norm(row["name"]).lower(), (norm(row["name"]), row["where"]))
        if len(names) > 1:
            spots = list(names.values())
            smells.add(2, "different names",
                       f"`{command}` is called " + "; ".join(f"'{n}' ({w})" for n, w in spots[:4]))
        keyed = [r for r in rows if r["shortcut"]]
        bare = [r for r in rows if not r["shortcut"] and r["area"] in ("Right-click menus",
                                                                      "Menu bar")]
        if keyed and bare:
            for row in bare[:3]:
                smells.add(3, "missing shortcut",
                           f"'{row['name']}' in {row['where']} shows no key; "
                           f"{keyed[0]['where']} shows {keyed[0]['shortcut']}")
    # same words, different command, different case
    by_words = defaultdict(dict)
    for command, rows in by_command.items():
        for row in rows:
            by_words[norm(row["name"]).lower()].setdefault(command, (norm(row["name"]),
                                                                    row["where"]))
    for words, commands in by_words.items():
        spellings = {n for n, _w in commands.values()}
        if len(commands) > 1 and len(spellings) > 1:
            smells.add(3, "look-alike names",
                       "different commands with the same words: "
                       + "; ".join(f"'{n}' ({w})" for n, w in list(commands.values())[:3]))
    # one method, two wordings where one is the other with words added
    # ("Rows above" in the cell menu, "Insert Rows Above" on the toolbar)
    by_method = defaultdict(OrderedDict)
    for row in ROWS:
        methods = [m for m in row["tokens"].get("method", []) if m not in GENERIC_METHODS]
        if row["area"] in ("Keys", "Mouse", "Dialogs") or len(methods) != 1 \
                or row["note"].startswith("value list") or row["name"].endswith("▸"):
            continue
        by_method[methods[0]].setdefault(norm(row["name"]).lower(), (norm(row["name"]),
                                                                    row["where"]))
    for method, names in by_method.items():
        words = {n: {w for w in re.findall(r"[a-z]+", n) if w not in SMALL}
                 for n in names}
        for a in names:
            for b in names:
                if a != b and words[a] and words[a] < words[b]:
                    smells.add(2, "different names",
                               f"`{method}()`: '{names[a][0]}' ({names[a][1]}) and "
                               f"'{names[b][0]}' ({names[b][1]})")
    # spelling (the user chose UK spelling)
    for row in ROWS:
        if row["area"] in ("Keys", "Mouse"):
            name = row["name"]
        elif row["area"] == "Dialogs":
            name = row["name"].split(" — ")[0]
        else:
            name = row["name"]
        for us, uk in US_UK:
            if re.search(rf"\b{us}", name):
                smells.add(6, "US spelling", f"'{norm(name)}': {us} → {uk}", row["where"])
    # disabled in every state walked (placeholders aside)
    enabled_somewhere = defaultdict(bool)
    for record in MENUS:
        if record["area"] != "Menu bar":
            continue
        for e in record["entries"]:
            if not e["sep"]:
                enabled_somewhere[(" ▸ ".join(record["path"]), e["text"])] |= e["enabled"]
    for (path, text), on in enabled_somewhere.items():
        if not on and not PLACEHOLDER.match(text):
            smells.add(4, "disabled in every state walked",
                       f"{path} ▸ {text} (states: fresh; two selected; two pages with the "
                       "second current; table; sheet; Calc mode)")
    # a dialog's title against the command that opens it
    for row in ROWS:
        if row["area"] != "Dialogs":
            continue
        title = row["name"].split(" — ")[0]
        for where, name in row.get("openers", []):
            a, b = norm(title), norm(name)
            if a.lower() == b.lower() and a != b:
                smells.add(5, "case", f"dialog title '{a}' vs command '{b}' ({where})")
            elif a and "/" not in a and "{" not in a and a.lower() not in b.lower() \
                    and b.lower() not in a.lower() and not a.startswith("("):
                smells.add(7, "dialog title differs from its command",
                           f"'{b}' ({where}) opens '{a}'")
    return smells.listed()


# ---------------------------------------------------------------------------
# output
# ---------------------------------------------------------------------------
AREAS = ["Menu bar", "Toolbars", "Right-click menus", "Panels", "Dialogs", "Keys", "Mouse"]


def md_escape(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def collapse_value_lists():
    """A submenu of values (paper sizes, decimal places, line widths…) is one
    line: the inventory counts features, not the values of one."""
    groups = OrderedDict()
    for row in ROWS:
        if " ▸ " in row["where"] and row["area"] in ("Menu bar", "Right-click menus", "Toolbars"):
            groups.setdefault((row["area"], row["where"]), []).append(row)
    drop = set()
    for (area, where), rows in groups.items():
        if any(r["name"].endswith("▸") for r in rows) or len(rows) < 6:
            continue
        toggles = all("toggle" in r["note"] for r in rows)
        short = all(len(r["name"]) <= 14 for r in rows)
        commands = any("…" in r["name"] for r in rows)
        if commands or not (toggles or short):
            continue
        names = [r["name"] for r in rows]
        merged = {"ident": [], "method": [], "text": [], "tool": [], "sig": []}
        for r in rows:
            for k, v in r["tokens"].items():
                merged.setdefault(k, [])
                merged[k] += [x for x in v if x not in merged[k]]
        first = rows[0]
        first["name"] = f"{len(rows)} choices: " + ", ".join(names[:8]) + (
            " …" if len(names) > 8 else "")
        first["note"] = "value list" + (", toggles" if toggles else "")
        first["shortcut"] = ""
        first["tokens"] = merged
        drop.update(id(r) for r in rows[1:])
    ROWS[:] = [r for r in ROWS if id(r) not in drop]


def write(out_path, smells, head):
    counts = Counter(r["area"] for r in ROWS)
    untested = Counter(r["area"] for r in ROWS if r["covered"] == "UNTESTED")
    weak = Counter(r["area"] for r in ROWS if r["covered"].startswith("≈"))
    cmd_only = Counter(r["area"] for r in ROWS if r["covered"].startswith("cmd:"))
    lines = [
        "# Feature inventory",
        "",
        f"Generated by `tools/qa/inventory.py` from commit {head}: the real MainWindow, "
        "headless (QT_QPA_PLATFORM=offscreen). Regenerate it rather than edit it:",
        "`QT_QPA_PLATFORM=offscreen python tools/qa/inventory.py` (about ten minutes on a "
        "loaded machine).",
        "",
        "The denominator for the passes in [QA_PLAN.md](QA_PLAN.md): every user-reachable "
        "feature once, with a test that exercises it.",
        "",
        "How it was walked: the menu bar with every lazy submenu asked to fill "
        "(`aboutToShow`), in six states (fresh; two shapes selected; two pages; a table open; "
        "a spreadsheet page open; Calc mode); every toolbar and the status bar in those "
        "states; every panel, its title-bar buttons and its own menus; right-click menus "
        "built by the app's own builders, with real right-clicks on the canvas, on one of "
        "every markup the tools draw headlessly, a multi-selection, an equation, a "
        "calculation block and text, table and spreadsheet cells, thumbnails, the document "
        "tab, the Markups List, the Tool Chest, the Variables panel, the ruler and the "
        "sheet tabs. Dialogs, keys and mouse gestures come from the source: every QDialog "
        "subclass and input box in `calcforge/ui`, the shortcut registry "
        "(`ShortcutManager.bindings()`) plus the fixed keys and gestures in `view.py`.",
        "",
        "**Covered by** is a grep of `tests/`, not a run: the first test that triggers the "
        "action or calls the method behind the entry (or picks the tool, or presses the "
        "key). `≈` means a test only names it (its attribute or its label, often a "
        "menu-wording check): weaker than exercising it. For keys, `key:` means a test "
        "sends that key with exactly those modifiers; `cmd:` means only the command is "
        "tested, not its key. `(+n)` counts further matching tests. A value list (paper "
        "sizes, decimal places, widths) is one line.",
        "",
        "## Summary",
        "",
        "| Area | Lines | UNTESTED | ≈ named only | cmd: key not pressed |",
        "|---|---:|---:|---:|---:|",
    ]
    for area in AREAS:
        lines.append(f"| {area} | {counts[area]} | {untested[area]} | {weak[area]} | "
                     f"{cmd_only[area] or ''} |")
    lines.append(f"| **Total** | **{sum(counts.values())}** | **{sum(untested.values())}** | "
                 f"**{sum(weak.values())}** | **{sum(cmd_only.values())}** |")
    lines += ["", "### Top 20 placement smells", ""]
    picked, by_cat = [], OrderedDict()
    for s in smells:
        by_cat.setdefault(s[1], []).append(s)
    quota = {"split group": 6, "different names": 5, "look-alike names": 2,
             "missing shortcut": 2, "case": 2, "US spelling": 2,
             "disabled in every state walked": 1, "empty submenu": 1,
             "dialog title differs from its command": 1}
    for cat, members in by_cat.items():
        picked += members[:quota.get(cat, 0)]
    for s in smells:
        if len(picked) >= 20:
            break
        if s not in picked:
            picked.append(s)
    for i, (_p, cat, text, _n) in enumerate(sorted(picked[:20], key=lambda s: s[0]), 1):
        lines.append(f"{i}. **{cat}**: {md_escape(text)}")
    lines += ["", f"All {len(smells)} are in the last section.", ""]
    if GAPS:
        lines += ["### What the walk could not reach", ""]
        for gap in GAPS:
            lines.append(f"- {md_escape(gap.splitlines()[0])}")
        lines.append("")
    for area in AREAS:
        rows = [r for r in ROWS if r["area"] == area]
        lines += [f"## {area} ({len(rows)})", ""]
        head_cell = "Where (opened by)" if area == "Dialogs" else "Where (path)"
        lines += [f"| {head_cell} | Name | Shortcut | Covered by |", "|---|---|---|---|"]
        for r in rows:
            name = r["name"] + (f" *({r['note']})*" if r["note"] else "")
            lines.append(f"| {md_escape(r['where'])} | {md_escape(name)} | "
                         f"{md_escape(r['shortcut'])} | {md_escape(r['covered'])} |")
        lines.append("")
    lines += ["## Placement smells (all, found mechanically)", "",
              "Each is a lead for the placement pass, not a verdict: some are Revu's or "
              "Excel's own choices.", ""]
    for cat in OrderedDict.fromkeys(s[1] for s in smells):
        members = [s for s in smells if s[1] == cat]
        lines += [f"### {cat} ({len(members)})", ""]
        for _p, _c, text, _n in members:
            lines.append(f"- {md_escape(text)}")
        lines.append("")
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


ACT_SLOTS: dict = {}
ACT_SIGS: dict = {}
LABEL_SIGS: dict = {}


def log(message: str) -> None:
    if os.environ.get("INVENTORY_VERBOSE"):
        print(message, file=sys.stderr, flush=True)


def main():
    global APP, ACT_SLOTS, ACT_SIGS, LABEL_SIGS
    if os.environ.get("INVENTORY_VERBOSE"):
        import faulthandler
        faulthandler.dump_traceback_later(120, repeat=True)
    out_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        ROOT, "docs", "qa", "feature_inventory.md")
    from calcforge.app import build_application
    APP = QApplication.instance() or build_application([])
    install_closer(APP)
    sources = parse_sources()
    ACT_SLOTS = sources[0]
    ACT_SIGS, LABEL_SIGS = sources[4], sources[5]

    def ident_for(window):
        ident = Ident(window)
        for attr in ("properties_panel", "markups_panel", "pages_panel", "bookmarks_panel",
                     "toolsets_panel", "search_panel", "page_panel", "maths_panel",
                     "variables_panel", "sheet_tabs"):
            obj = getattr(window, attr, None)
            if obj is not None:
                ident.add_object(attr, obj)
        return ident

    for scenario in (markup_scenarios, table_scenarios, sheet_scenarios, calc_scenarios):
        log(f"scenario {scenario.__name__}")
        try:
            scenario(ident_for, sources)
        except Exception as error:  # noqa: BLE001
            GAPS.append(f"{scenario.__name__}: {error!r}\n{traceback.format_exc(limit=5)}")
        CAPTURED.clear()
    item_menu_rows(sources)

    # keys: the shortcut registry, as a fresh window registers it
    log("keys")
    window = new_window()
    from calcforge.ui.shortcuts import SCOPE_NAMES
    manager = window.shortcuts
    for binding in manager.bindings():
        sequence = manager.sequence(binding.action_id)
        scope = SCOPE_NAMES.get(binding.scope, binding.scope)
        tokens = {"action_id": [binding.action_id]}
        context = ()
        if binding.action_id.startswith("command."):
            key = binding.action_id.split(".")[1]
            tokens["ident"] = [f"act_{key}"]
            tokens["method"] = ACT_SLOTS.get(key, [])
        if binding.kind == "tool":
            tokens["tool"] = [binding.payload]
            context = (f'"{binding.payload}"', f"'{binding.payload}'")
        elif binding.payload and binding.payload.isidentifier():
            tokens["method"] = tokens.get("method", []) + [binding.payload]
        row = add_row("Keys", f"{binding.category} · {scope}", binding.label, sequence, tokens,
                      note=binding.kind, key=("Keys", binding.action_id))
        if row is not None:
            row["sequence"] = sequence
            row["context"] = context
    for keys, what, scope, raw in VIEW_KEYS:
        add_row("Keys", f"Canvas, fixed in view.py · {scope}", what, keys,
                {"raw": [r if (r.startswith(("fn:", "w:")) or "|" in r) else f"{r}|"
                         for r in raw]},
                note="not rebindable")
    registered = {QKeySequence(manager.sequence(b.action_id)).toString()
                  for b in manager.bindings() if manager.sequence(b.action_id)}
    for row in [r for r in ROWS if r["area"] == "Right-click menus" and r["shortcut"]]:
        for part in row["shortcut"].split(" / "):
            if QKeySequence(part).toString() not in registered:
                add_row("Keys", f"Shown only on a menu ({row['where']})", row["name"], part,
                        row["tokens"], note="not in the shortcut list, so it cannot be rebound",
                        key=("Keys", "menu", part, row["name"]))
    dispose(window)

    for gesture, where, what, raw in MOUSE:
        add_row("Mouse", where, f"{gesture}: {what}", "", {"raw": list(raw)},
                key=("Mouse", gesture, where))

    # dialogs, with the commands that open them
    log("dialogs")
    menu_rows_by_method = defaultdict(list)
    for row in ROWS:
        if row["area"] in ("Menu bar", "Right-click menus", "Toolbars", "Panels"):
            for method in row["tokens"].get("method", []):
                menu_rows_by_method[method].append(row)
    func_calls, def_counts = sources[3], sources[6]
    for dialog in dialogs(menu_rows_by_method):
        openers = []
        for fn in dialog["openers"]:
            if def_counts.get(fn, 0) != 1:
                continue            # a name defined twice cannot say which one opens it
            hits = menu_rows_by_method.get(fn, [])
            if not hits:
                for caller, called in func_calls.items():
                    if fn in called and def_counts.get(caller, 0) == 1 \
                            and caller in menu_rows_by_method:
                        hits = menu_rows_by_method[caller]
                        break
            for hit in hits[:2]:
                methods = set(hit["tokens"].get("method", []))
                if len(methods) > 1:
                    continue        # its label is several commands' (Rename…): not this one's
                openers.append((hit["where"], norm(hit["name"])))
        openers = list(OrderedDict.fromkeys(openers))
        where = "; ".join(f"{w} ▸ {n}" for w, n in openers) or (
            "via " + ", ".join(f"{dialog['module'][:-3]}.{f}()" for f in dialog["openers"])
            if dialog["openers"] else "(no opener found)")
        row = add_row("Dialogs", where,
                      f"{dialog['title'] or '(untitled)'} — {dialog['module']}:{dialog['name']}"
                      + (f", {dialog['fields']} fields" if dialog["fields"] else ""), "",
                      {"ident": [dialog["name"]] if not dialog["name"].endswith("()") else [],
                       "method": [o for o in dialog["openers"]
                                  if def_counts.get(o, 0) == 1]},
                      key=("Dialogs", dialog["module"], dialog["name"], dialog["title"]))
        if row is not None:
            row["openers"] = openers

    log("coverage")
    collapse_value_lists()
    index = TestIndex()
    for row in ROWS:
        if row["area"] == "Keys" and row.get("sequence") is not None:
            hits = key_coverage(row["sequence"], index, row.get("context", ()))
            if hits:
                row["covered"] = "key: " + _fmt(hits)
            else:
                cmd = coverage(row, index)
                row["covered"] = ("cmd: " + cmd) if cmd != "UNTESTED" else "UNTESTED"
        else:
            row["covered"] = coverage(row, index)
    log("smells")
    smells = find_smells()
    head = os.popen(f"git -C '{ROOT}' rev-parse --short HEAD").read().strip()
    write(out_path, smells, head)
    print(f"wrote {out_path}: {len(ROWS)} lines, "
          f"{sum(1 for r in ROWS if r['covered'] == 'UNTESTED')} UNTESTED, {len(smells)} smells, "
          f"{len(GAPS)} gaps", flush=True)
    for gap in GAPS:
        print("GAP:", gap.splitlines()[0], flush=True)
    sys.stdout.flush()
    os._exit(0)          # skip Qt's teardown: it only prints noise about dead slots


if __name__ == "__main__":
    main()
