"""Every command a person can give is a named binding (the user, 2026-10-16:
"Whatever features you add should show up in the shortcuts manager as a
feature, and then the user can add whatever shortcuts they want").

The window's own commands are QActions made by ``MainWindow._act`` (and the
tools'); they carry their key themselves. Everything else a person can
click — the entries a right-click menu builds for whatever was clicked, the
entries a menu fills in as it opens, a panel's buttons — is made fresh each
time, so it cannot carry a key of its own. Those are given a *command id*:

* every menu is tagged with the *context* its entries belong to (the
  ``cf_context`` property: ``page`` for a page's menu, wherever it is opened
  — a thumbnail, Document ▸ Current Page — ``canvas`` for a markup's,
  ``cell`` for a table's cells, and so on). A submenu inherits its parent's,
  and a menu on the menu bar is in ``menu``;
* an entry's id is the context and its path in that menu
  (``page.rotate_pages.clockwise``), unless ``bindable_list.ALIASES`` says it
  is a command already known by another id (a markup's Cut is Edit ▸ Cut,
  a cell's Cut is the spreadsheet's), so one key works from every place the
  command is offered and is shown beside it in each;
* a key bound to such an id does what the click would: the context's menu
  is built for what is current — the page in view, the selection, the active
  cell — and the entry with that id is triggered. If it is not offered there
  (Arc Segment with a rectangle selected) the status bar says so.

``bindable_list.COMMANDS`` names every id with its category and where it
acts; ``tests/test_every_command_is_bindable.py`` walks the live window and
fails for an entry, toolbar button or panel button with no listed id, so
nothing new can be added without being bindable.

Entries that are data rather than commands — Open Recent's files, Undo
History's steps, a tool set's name, a column filter's values — are marked
with :func:`data_entry` (or their menu with :func:`data_menu`) and are left
out; so are the greyed lines that only say something ("3 selected").
"""
from __future__ import annotations

import re
import unicodedata
from typing import Callable, Optional

from PySide6.QtCore import QObject, QPointF, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QAbstractButton, QMenu, QMenuBar, QToolBar, QWidgetAction

#: QAction property: the binding id the action runs.
COMMAND = "cf_command"
#: QAction property: a menu's own entry, whose key is only shown there (the
#: window's QAction, or the router's, is the one that answers to it).
SHOWN = "cf_shown"
#: QMenu property: the context the menu's entries belong to.
CONTEXT = "cf_context"
#: QAction / QMenu property: data, not a command (not bindable).
DATA = "cf_data"
#: QAbstractButton property: the binding id the button runs.
BUTTON = "cf_button"

#: The greyed lines a menu shows only to say something.
_INFO = re.compile(r"^(\d+ selected|nothing (selected|to undo|to redo)|no recent files|"
                   r"\(none\)|—)$", re.IGNORECASE)

_CHARS = {"+": "plus", "−": "minus", "%": "pct", "&": "and", "#": "hash", "/": "per",
          "*": "times", "=": "equals", "<": "lt", ">": "gt", "·": "dot", "°": "deg",
          "→": "to", "←": "from"}


def clean(text: str) -> str:
    """The words of a menu entry: no mnemonic &, no key after a tab."""
    text = (text or "").split("\t")[0]
    text = text.replace("&&", "\0").replace("&", "").replace("\0", "&")
    return text.strip()


def label_of(text: str) -> str:
    """An entry's words as a command's name: without the dots of a dialog."""
    # "4 *" is Decimal places' 4, starred as the document's default
    return clean(text).rstrip("…").rstrip().removesuffix("...").removesuffix(" *")


def slug(text: str) -> str:
    """A stable identifier for a menu entry's words."""
    text = label_of(text)
    out = []
    for ch in text.lower():
        if ch.isascii() and ch.isalnum():
            out.append(ch)
        elif ch in _CHARS:
            out.append(f"_{_CHARS[ch]}_")
        elif ch.isspace() or ch in "-_.,:;'()[]{}!?\"|\\‘’“”":
            out.append("_")
        else:
            # a Greek letter, a symbol: by its name, so the id stays ASCII
            try:
                out.append("_" + unicodedata.name(ch).lower().replace(" ", "_") + "_")
            except ValueError:
                out.append("_")
    return re.sub(r"_+", "_", "".join(out)).strip("_") or "entry"


def data_entry(action: QAction) -> QAction:
    """Mark *action* as data shown in a menu (a recent file, a step)."""
    action.setProperty(DATA, True)
    return action


def data_menu(menu: QMenu) -> QMenu:
    """Mark every entry of *menu* as data, except those that carry an id."""
    menu.setProperty(DATA, True)
    return menu


def set_context(menu: QMenu, context: str) -> QMenu:
    menu.setProperty(CONTEXT, context)
    return menu


def is_info(action: QAction) -> bool:
    return not action.isEnabled() and bool(_INFO.match(clean(action.text())))


# ---------------------------------------------------------------------------
# where each context's menu comes from, for running an entry by its key
# ---------------------------------------------------------------------------
#: What the "Where" column says for a context's entries.
PLACES = {
    "menu": "Menu bar",
    "page": "Right-click a thumbnail · Document ▸ Current Page",
    "insert": "Document ▸ Insert · File ▸ Import · Thumbnails panel",
    "canvas": "Right-click on the page · Tools ▸ Selected Markups",
    "cell": "Right-click a cell",
    "heading": "Right-click a row or column heading",
    "filter": "A filtered column's drop-down",
    "tablebar": "Style bar, with a table open",
    "propbar": "Properties toolbar",
    "sheettab": "Right-click a sheet tab",
    "doctab": "Right-click a document tab",
    "markuprow": "Markups List ▸ right-click a row",
    "chest": "Tool Chest ▸ Tool Sets button",
    "chesttool": "Tool Chest ▸ right-click a tool, or a set's gear",
    "variables": "Variables panel ▸ right-click a row",
    "ruler": "Right-click a ruler",
    "styles": "Markup Styles toolbar ▸ right-click a style",
    "print": "File ▸ Print… dialog",
    "panel": "Panel button",
    "button": "Button",
}


def _canvas_menu(window):
    items = window.selected_items()
    if items:
        item = items[0]
        centre = (item.mapToScene(item.local_rect().center()) if hasattr(item, "local_rect")
                  else item.sceneBoundingRect().center())
        return window.build_context_menu(item, centre)
    view = window.view
    pos = getattr(view, "_last_scene_pos", None)
    if not isinstance(pos, QPointF):
        pos = view.mapToScene(view.viewport().rect().center())
    return window.build_context_menu(None, pos)


def _open_table(window):
    tables = window.view.tables
    return tables if tables.item is not None else None


def _heading_menu(window):
    tables = _open_table(window)
    if tables is None:
        return None
    t, l, b, r = tables.selection()
    rows, cols = tables.item.size
    whole_col = t == 0 and b == rows - 1 and not (l == 0 and r == cols - 1)
    return tables.heading_menu("col", l) if whole_col else tables.heading_menu("row", t)


def _filter_menu(window):
    tables = _open_table(window)
    if tables is None or tables.item.sheet.filter is None:
        return None
    from . import datatools
    return datatools.filter_menu(tables, tables.active[1], None)


def _sheettab_menu(window):
    tabs = getattr(window, "sheet_tabs", None)
    if tabs is None or tabs.bar.count() == 0:
        return None
    return tabs.build_menu(tabs.bar.currentIndex())


def _doctab_menu(window):
    bar = window.document_tabs
    index = getattr(window, "_active_tab", 0)
    if bar.count() == 0 or not 0 <= index < bar.count():
        return None
    return window._tab_context_menu(bar.tabRect(index).center(), QMenu(window))


def _ruler_menu(window):
    from .rulers import Ruler
    rulers = window.findChildren(Ruler)
    return rulers[0].build_menu() if rulers else None


def _styles_menu(window):
    styles = window.markup_styles
    number = styles.active()
    return styles.build_menu(number) if number else None


#: How each context's menu is built for what is current.
BUILDERS: dict[str, Callable] = {
    "page": lambda window: window.page_menu(window.current_index),
    "canvas": _canvas_menu,
    "cell": lambda window: _open_table(window) and _open_table(window).cell_menu(),
    "heading": _heading_menu,
    "filter": _filter_menu,
    "sheettab": _sheettab_menu,
    "doctab": _doctab_menu,
    "markuprow": lambda window: window.markups_panel._row_menu(None),
    "chest": lambda window: window.toolsets_panel.build_chest_menu(),
    "chesttool": lambda window: window.toolsets_panel.build_menu(),
    "variables": lambda window: window.variables_panel.build_menu(),
    "ruler": _ruler_menu,
    "styles": _styles_menu,
    # the Print dialog's Defaults ▾, while the dialog is up
    "print": lambda window: (window.print_dialog.build_defaults_menu()
                             if getattr(window, "print_dialog", None) is not None
                             and window.print_dialog.isVisible() else None),
}


#: Where panel and bar buttons are found, and the context their ids are in.
BUTTON_ROOTS = (
    ("thumbnails", lambda w: w.pages_panel),
    # its buttons sit on its title bar, after "Thumbnails ▾"
    ("thumbnails", lambda w: w.pages_panel.header_tools),
    ("bookmarks", lambda w: w.bookmarks_panel),
    ("markupslist", lambda w: w.markups_panel),
    ("toolchest", lambda w: w.toolsets_panel),
    ("search", lambda w: w.search_panel),
    ("pagepanel", lambda w: w.page_panel),
    ("maths", lambda w: w.maths_panel),
    ("variablespanel", lambda w: w.variables_panel),
    ("properties", lambda w: w.properties_panel),
    ("propbar", lambda w: w.style_bar),
    ("styles", lambda w: w.markup_styles.bar),
    ("status", lambda w: w.statusBar()),
    ("print", lambda w: getattr(w, "print_dialog", None)),
)
BUTTON_CONTEXTS = {name for name, _root in BUTTON_ROOTS} | {"tablebar"}
BUTTON_PLACES = {"thumbnails": "Thumbnails panel", "bookmarks": "Bookmarks panel",
                 "markupslist": "Markups List", "toolchest": "Tool Chest panel",
                 "search": "Search panel", "pagepanel": "Page panel", "maths": "Maths panel",
                 "variablespanel": "Variables panel", "properties": "Properties panel",
                 "propbar": "Properties toolbar", "styles": "Markup Styles toolbar",
                 "status": "Status bar", "tablebar": "Style bar, with a table open",
                 "print": "File ▸ Print… dialog"}


def is_field(button: QAbstractButton) -> bool:
    """A button that holds a value or only opens a menu, not a command:
    a colour, a drop-down's face, a tick box, a tab bar's scroll arrow."""
    from PySide6.QtWidgets import (QAbstractSpinBox, QCheckBox, QComboBox, QLineEdit,
                                   QRadioButton, QTabBar, QToolButton)
    from .widgets import ColorButton
    if isinstance(button, (QCheckBox, QRadioButton, ColorButton)):
        return True
    if button.objectName().startswith("qt_"):
        return True
    parent = button.parentWidget()
    if isinstance(parent, (QTabBar, QAbstractSpinBox, QComboBox, QLineEdit)):
        return True
    if isinstance(button, QToolButton) and button.menu() is not None \
            and button.popupMode() == QToolButton.InstantPopup:
        return True          # it only opens its menu, whose entries are the commands
    return False


def _tip_name(button: QAbstractButton) -> str:
    """A tooltip's name for the command: its first line, without the key
    and the explanation after a dash."""
    tip = clean(button.property("cf_tip") or button.toolTip()).split("\n")[0]
    tip = re.split(r"\s+[—–]\s+|\s+\(|;\s|:\s", tip)[0]
    return tip.strip()


def _wordy(text: str) -> bool:
    """Words (or a keypad's digit), not a symbol standing for them."""
    return bool(re.search(r"[A-Za-z]{2}", text)) or text.isdigit()


def button_key(button: QAbstractButton) -> str:
    """The words a button's id is made from: its own when they are words
    (or a digit on a keypad), else its tooltip's."""
    text = clean(button.text())
    return text if text and _wordy(text) else (_tip_name(button) or text
                                               or button.objectName())


def button_label(button: QAbstractButton) -> str:
    """What a button is called in Keyboard Shortcuts: its words, and what
    its tooltip calls it when its face is only a symbol."""
    text = clean(button.text())
    tip = _tip_name(button)
    if text and tip and not _wordy(text) and tip.lower() != text.lower():
        return f"{tip} {text}"
    return text or tip or button.objectName()


class CommandRouter(QObject):
    """Gives every menu entry and panel button an id, shows its key, and runs
    it when the key is pressed."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.manager = window.shortcuts
        self.proxies: dict[str, QAction] = {}
        self.seen: dict[str, set] = {}               # id -> where it has been offered
        from .bindable_list import COMMANDS
        self.manager.register_many(
            (command_id, label, category, scope, "menu")
            for command_id, (label, category, scope) in COMMANDS.items())

    # -- ids -----------------------------------------------------------------
    def context_of(self, menu: QMenu):
        """(context, path) of *menu*: its own context, or its parent's with
        its title added; None when it belongs to none."""
        own = menu.property(CONTEXT)
        if own:
            return str(own), []
        inherited = getattr(menu, "_cf_where", None)
        if inherited is not None:
            return inherited
        action = menu.menuAction()
        for owner in action.associatedObjects():
            if isinstance(owner, QMenuBar):
                return "menu", [clean(action.text())]
            if isinstance(owner, QMenu) and owner is not menu:
                found = self.context_of(owner)
                if found is not None:
                    return found[0], found[1] + [clean(action.text())]
        return None

    @staticmethod
    def derive(context: str, path: list) -> str:
        from .bindable_list import ALIASES
        raw = context + "." + ".".join(slug(part) for part in path)
        return ALIASES.get(raw, raw)

    def _ensure(self, command_id: str, label: str) -> None:
        """An id not in the list is still bindable: it shows under Other
        until it is listed (the test insists that it is)."""
        if command_id not in self.manager._sequences:
            self.manager.register(command_id, label, "", "Other", payload="menu",
                                  kind="menu")

    # -- menus ---------------------------------------------------------------
    def decorate(self, menu: QMenu, context: Optional[str] = None,
                 path: Optional[list] = None) -> QMenu:
        """Give every entry of *menu* (and its submenus) its id and show the
        key bound to it beside it."""
        if context is None:
            found = self.context_of(menu)
            if found is None:
                return menu
            context, path = found
        path = list(path or [])
        data = bool(menu.property(DATA))
        root = PLACES.get(context.split(".")[0], "")
        for action in menu.actions():
            if action.isSeparator():
                continue
            text = clean(action.text())
            if isinstance(action, QWidgetAction) and not text:
                continue
            sub = action.menu()
            command_id = action.property(COMMAND)
            if sub is not None and not command_id:
                if not sub.property(CONTEXT):
                    sub._cf_where = (context, path + [text])
                self.decorate(sub)
                continue
            if not text or (data and not command_id) or action.property(DATA) \
                    or is_info(action):
                continue
            if not command_id:
                command_id = self.derive(context, path + [text])
                action.setProperty(COMMAND, command_id)
                action.setProperty(SHOWN, True)
                named = path[1:] if context == "menu" else path
                self._ensure(command_id, " ▸ ".join(named + [label_of(text)]))
            where = path + [text]
            if context != "menu" and root:
                where = [root] + where
            self.seen.setdefault(command_id, set()).add(" ▸ ".join(where))
            if action.property(SHOWN):
                action.setShortcuts(self.keys_of(command_id))
                action.setShortcutContext(Qt.WidgetShortcut)
            if sub is not None:
                self.decorate(sub)
        return menu

    def keys_of(self, command_id: str) -> list:
        """The keys *command_id* answers to, as the window carries them."""
        window = self.window
        for key, action_id in window.action_ids.items():
            if action_id == command_id and getattr(window, f"act_{key}", None) is not None:
                return window._keys_for(key, self.manager.sequence(action_id))
        text = self.manager.sequence(command_id)
        return [QKeySequence(text)] if text else []

    # -- running an entry by its key -----------------------------------------
    def _menu_for(self, command_id: str):
        """(menu holding *command_id*'s entry, whether to throw it away)."""
        context = command_id.split(".")[0]
        builder = BUILDERS.get(context)
        if builder is not None:
            return builder(self.window), True
        # a menu that lives as long as the window: Insert's Before / After,
        # the Style bar's
        best = None
        for menu in self.window.findChildren(QMenu):
            own = menu.property(CONTEXT)
            if own and (command_id + ".").startswith(str(own) + ".") and (
                    best is None or len(str(own)) > len(str(best.property(CONTEXT)))):
                best = menu
        return best, False

    def find(self, menu: QMenu, command_id: str):
        """The entry of *menu* (submenus filled as on opening) that runs
        *command_id*."""
        self.decorate(menu)
        for action in menu.actions():
            if action.isSeparator():
                continue
            if action.property(COMMAND) == command_id:
                return action
            sub = action.menu()
            if sub is not None:
                sub.aboutToShow.emit()
                found = self.find(sub, command_id)
                if found is not None:
                    return found
        return None

    def run(self, command_id: str) -> bool:
        """Do what clicking *command_id*'s entry would do, here and now."""
        root = command_id.split(".")[0]
        if root in BUTTON_CONTEXTS:
            button = self.find_button(command_id)
            if button is not None:
                if not button.isEnabled():
                    return self._not_here(command_id)
                button.click()
                return True
            if root not in BUILDERS:
                return self._not_here(command_id)
        if root == "menu":
            return self._run_on_menu_bar(command_id)
        menu, throw_away = self._menu_for(command_id)
        if menu is None:
            return self._not_here(command_id)
        try:
            action = self.find(menu, command_id)
            if action is None or not action.isEnabled() or not action.isVisible():
                return self._not_here(command_id)
            action.trigger()
            return True
        finally:
            if throw_away and isinstance(menu, QMenu):
                menu.deleteLater()

    def _run_on_menu_bar(self, command_id: str) -> bool:
        """A menu-bar entry the window has no action of its own for (View ▸
        Dimmer's levels, Open Recent's Clear): its menus are filled as they
        would be on opening, down the path its id names."""
        parts = command_id.split(".")[1:]
        opened = []
        current = None
        try:
            holder = self.window.menuBar()
            for part in parts[:-1]:
                step = next((a.menu() for a in holder.actions()
                             if a.menu() is not None and slug(a.text()) == part), None)
                if step is None:
                    break
                step.aboutToShow.emit()
                opened.append(step)
                self.decorate(step)
                holder = current = step
            if current is not None:
                action = next((a for a in current.actions()
                               if a.property(COMMAND) == command_id), None)
                if action is not None and action.isEnabled():
                    action.trigger()
                    return True
        finally:
            for menu in reversed(opened):
                menu.aboutToHide.emit()
        return self._not_here(command_id)

    def _not_here(self, command_id: str) -> bool:
        from .shortcuts import BY_ID
        binding = BY_ID.get(command_id)
        name = binding.label if binding is not None else command_id
        hint = getattr(self.window, "status_hint", None)
        if hint is not None:
            hint.setText(f"{name} is not available here")
        return False

    # -- buttons -------------------------------------------------------------
    def bind_button(self, button: QAbstractButton, command_id: str) -> QAbstractButton:
        """Give *button* the command *command_id*: a key bound to it clicks
        the button (or runs the window command or menu entry of that id,
        when the button is another place for one), and its tooltip says the
        key."""
        button.setProperty(BUTTON, command_id)
        if not self._runs_elsewhere(command_id):
            self._ensure(command_id, button_label(button))
        self._tip_key(button, command_id)
        return button

    def _runs_elsewhere(self, command_id: str) -> bool:
        """Whether *command_id* is a window action's or a menu entry's, so a
        key runs that rather than clicking a button."""
        from .shortcuts import BY_ID
        if command_id in self.window.action_ids.values():
            return True
        binding = BY_ID.get(command_id)
        if binding is not None and binding.kind != "menu":
            return True          # a tool's, a spreadsheet key's
        return command_id.split(".")[0] not in BUTTON_CONTEXTS

    def tag_buttons(self) -> None:
        """Give every panel and bar button its command id."""
        from .rail import RailButton
        for button in self.window.findChildren(RailButton):
            self.tag_one(button)
        for context, root in self._roots():
            for button in root.findChildren(QAbstractButton):
                self.tag_one(button, context)

    def _roots(self):
        out = []
        for context, root_of in BUTTON_ROOTS:
            try:
                root = root_of(self.window)
            except AttributeError:
                continue
            if root is not None:
                out.append((context, root))
        return out

    def tag_one(self, button: QAbstractButton, context: Optional[str] = None) -> None:
        """Give *button* its command id, if it is a command (a panel that
        builds its buttons afresh has them tagged as they are shown)."""
        from .rail import RailButton
        if button.property(BUTTON) or button.property(DATA) or is_field(button):
            return
        action = button.defaultAction() if hasattr(button, "defaultAction") else None
        if action is not None and action.property(COMMAND):
            return
        if isinstance(button, RailButton):
            command_id = self.window.action_ids.get(f"panel_{button.panel_name[5:]}")
            if command_id:
                self.bind_button(button, command_id)
            return
        if context is None:
            roots = self._roots()
            current = button.parentWidget()
            while current is not None and context is None:
                context = next((name for name, root in roots if root is current), None)
                current = current.parentWidget()
            if context is None:
                return
        self.bind_button(button, self.derive(context, [button_key(button)]))

    def find_button(self, command_id: str):
        self.tag_buttons()
        for button in self.window.findChildren(QAbstractButton):
            if button.property(BUTTON) == command_id:
                return button
        return None

    def _tip_key(self, button: QAbstractButton, command_id: str) -> None:
        base = button.property("cf_tip")
        if base is None:
            base = button.toolTip()
            button.setProperty("cf_tip", base)
        keys = ", ".join(k.toString(QKeySequence.NativeText) for k in self.keys_of(command_id))
        tip = f"{base}  ({keys})" if keys and base else base
        if button.toolTip() != tip:
            button.setToolTip(tip)

    # -- keys ----------------------------------------------------------------
    def apply(self) -> None:
        """Put the current keys on the router's own actions: one for each id
        that has a key and no window QAction to carry it."""
        from .shortcuts import ALWAYS, BY_ID, CALC, MARKUP
        calc_on = self.window.view.calc.calc_mode()
        for command_id, binding in list(BY_ID.items()):
            if binding.kind != "menu":
                continue
            text = self.manager.sequence(command_id)
            proxy = self.proxies.get(command_id)
            if not text and proxy is None:
                continue
            if proxy is None:
                proxy = QAction(binding.label, self.window)
                proxy.setProperty(COMMAND, command_id)
                proxy.triggered.connect(lambda _c=False, c=command_id: self.run(c))
                self.window.addAction(proxy)
                self.proxies[command_id] = proxy
            # a table's keys belong to the open table, which runs them itself
            # (TableEditor._bound_command); Calc and Markup keys are live only
            # in their own mode, so one key can mean one thing in each
            live = binding.scope == ALWAYS or (binding.scope == CALC and calc_on) \
                or (binding.scope == MARKUP and not calc_on)
            proxy.setShortcuts([QKeySequence(text)] if text and live else [])

    def refresh_buttons(self) -> None:
        """Every button's tooltip says the key it now has."""
        self.tag_buttons()
        for button in self.window.findChildren(QAbstractButton):
            command_id = button.property(BUTTON)
            if command_id:
                self._tip_key(button, command_id)

    # -- where -----------------------------------------------------------------
    def places(self, command_id: str) -> list[str]:
        """Where *command_id* is offered: the menus and bars its window
        action is on, the menus it has been seen in, its context's place."""
        return self.places_map([command_id]).get(command_id, [])

    def places_map(self, ids=None) -> dict[str, list[str]]:
        """places() for every binding (or those in *ids*), worked out in one
        pass over the window's actions."""
        from .shortcuts import BY_ID, INSERT, SHEET, SMATH, SYMBOL
        by_command: dict[str, list] = {}
        for action in self._window_actions():
            command_id = action.property(COMMAND)
            if command_id:
                by_command.setdefault(str(command_id), []).append(action)
        wanted = ids if ids is not None else [b.action_id for b in self.manager.bindings()]
        # the other places a command is offered under its own id (ALIASES)
        from .bindable_list import ALIASES
        elsewhere: dict[str, set] = {}
        for raw, target in ALIASES.items():
            context = raw.split(".")[0]
            place = BUTTON_PLACES.get(context) if context in BUTTON_CONTEXTS else None
            place = place or PLACES.get(context)
            if place and context != "menu":
                elsewhere.setdefault(target, set()).add(place)
        out = {}
        for command_id in wanted:
            own = command_id[:-len(".also")] if command_id.endswith(".also") else command_id
            found = set(self.seen.get(own, ()))
            seen_roots = {where.split(" ▸ ")[0] for where in found}
            found |= {place for place in elsewhere.get(own, ()) if place not in seen_roots}
            for action in by_command.get(own, []):
                for owner in action.associatedObjects():
                    if isinstance(owner, QMenu):
                        where = self.menu_path(owner)
                        if where:
                            found.add(" ▸ ".join(where + [clean(action.text())]))
                    elif isinstance(owner, QToolBar):
                        found.add(f"{owner.windowTitle()} toolbar")
            context = own.split(".")[0]
            binding = BY_ID.get(command_id)
            kind = binding.kind if binding is not None else ""
            if kind == "menu" and context in BUTTON_CONTEXTS:
                found.add(BUTTON_PLACES.get(context, PLACES["panel"]))
            elif kind == "menu" and context in PLACES and context != "menu" \
                    and PLACES[context] not in seen_roots:
                found.add(PLACES[context])
            if not found:
                if kind == SYMBOL:
                    found.add("While typing words or an equation")
                elif kind == SMATH:
                    found.add("In an equation")
                elif kind == SHEET:
                    found.add("In an open table or spreadsheet")
                elif kind == INSERT:
                    found.add("Typed straight onto the page")
                elif kind == "menu" and context == "menu" and binding is not None:
                    found.add("Menu bar ▸ " + binding.label)
                elif kind == "menu" and context in PLACES:
                    found.add(PLACES[context])
                elif own == "command.calc_mode":
                    found.add("The Markup | Calc switch on the menu bar")
                else:
                    found.add("Keyboard only")
            out[command_id] = sorted(found)
        return out

    def _window_actions(self):
        window = self.window
        out = [getattr(window, f"act_{key}", None) for key in window.action_ids]
        out += list(getattr(window, "tool_actions", {}).values())
        for entries in getattr(window, "insert_tool_actions", {}).values():
            out += entries
        return [a for a in out if a is not None]

    @staticmethod
    def menu_path(menu: QMenu) -> list:
        """The menu bar path to *menu*, or [] when it is not on the bar."""
        path = []
        current = menu
        for _ in range(8):
            action = current.menuAction()
            path.insert(0, clean(action.text() or current.title()))
            parents = [o for o in action.associatedObjects()
                       if isinstance(o, (QMenu, QMenuBar)) and o is not current]
            if not parents:
                return []
            if isinstance(parents[0], QMenuBar):
                return path
            current = parents[0]
        return []


def owning_window(widget):
    """The MainWindow a menu or button belongs to, or None."""
    from .mainwindow import MainWindow
    current = widget
    for _ in range(40):
        if current is None or isinstance(current, MainWindow):
            return current
        current = current.parent()
    return None
