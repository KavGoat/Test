"""Markup styles: numbered looks for each markup tool (the user's design,
2026-10-15).

Pick a tool — Q for a callout — and it draws in its default look. Press 1 and
the next callout is drawn in callout style 1; 2 for style 2, and so on up to
9. After that one markup the tool is back on its default, so every styled
markup asks for its number again; 0, or the tool's own letter, also goes back
to the default.

A style is what Bluebeam's Tool Chest keeps for a tool in Properties Mode —
everything about a markup except where it is and what it says — and it is
applied to the next markup the same way a Tool Chest tool's properties are
(``toolsets.apply_properties``, through the view's pending properties). The
"Default" a style falls back to is the tool's own default ("Set as Default").

The Markup Styles toolbar shows the styles of the tool in hand, each drawn
in its own colours, line and fill. Clicking one picks it, and while it is
picked (and nothing is selected) the Properties toolbar and panel edit it,
as Revu's Properties Mode edits a Tool Chest tool. "+" saves the tool's
current look as a new style; the right-click menu renames, updates from the
selected markup, removes and moves; a style can be dragged along the bar.

Styles belong to the person, not the document, so they live in the app's
settings beside the Tool Chest, keyed by the tool that draws them. Editing
them is not part of a document's undo.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from PySide6.QtCore import QObject, QPoint, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QInputDialog, QLabel, QMenu,
                               QToolBar, QToolButton)

from ..settings import app_settings
from . import toolsets
from .tools import ERASE, NONE, SNAPSHOT, TOOL_MAP

STYLES_KEY = "markups/styles"
MAX_STYLES = 9
ICON_SIZE = QSize(36, 22)

# The example a style is drawn on, in points: small, so that at the size of a
# toolbar icon a point of line is about a pixel and widths can be told apart.
_EXAMPLE_BOX = [0.0, 0.0, 34.0, 19.0]
_EXAMPLE_LINE = [[0.0, 17.0], [34.0, 2.0]]
_EXAMPLE_SHAPE = [[0.0, 19.0], [7.0, 1.0], [34.0, 0.0], [29.0, 19.0]]
_CLOSED_KINDS = {"polygon", "area", "perimeter", "volume"}

# Tools that draw something a style means nothing to: a region, a hole cut
# out of an area, a scale being set, a picture, a link, a contents list, a
# stamp (whose colours come from its wording).
_NOT_STYLED = {"calibrate", "cutout_polygon", "cutout_ellipse", "stamp", "image",
               "link", "contents", "crop_image", "viewport", "whiteout", "crop",
               "snapshot", "eraser", "table"}
_styled_cache: dict = {}
_tool_by_kind: dict = {}


@dataclass
class MarkupStyle:
    """One numbered look for a tool."""

    name: str
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"name": self.name, "payload": self.payload}

    @classmethod
    def from_dict(cls, data: dict) -> "MarkupStyle":
        return cls(str(data.get("name", "Style")), dict(data.get("payload", {})))


# ---------------------------------------------------------------------------
# storage
# ---------------------------------------------------------------------------

def load_all() -> dict:
    """Every tool's styles: {tool key: [MarkupStyle, ...]}."""
    stored = app_settings().value(STYLES_KEY, "")
    try:
        raw = json.loads(stored) if stored else {}
    except (ValueError, TypeError):
        raw = {}
    styles = {}
    if isinstance(raw, dict):
        for key, entries in raw.items():
            try:
                styles[str(key)] = [MarkupStyle.from_dict(e) for e in entries][:MAX_STYLES]
            except (AttributeError, TypeError):
                continue
    return styles


def save_all(styles: dict) -> None:
    settings = app_settings()
    settings.setValue(STYLES_KEY, json.dumps(
        {key: [s.to_dict() for s in entries] for key, entries in styles.items() if entries}))
    settings.sync()


def styles_for(tool_key: str) -> list:
    return load_all().get(tool_key, [])


def set_styles_for(tool_key: str, entries: list) -> None:
    styles = load_all()
    styles[tool_key] = list(entries)[:MAX_STYLES]
    save_all(styles)


def styled(tool_key: str) -> bool:
    """Whether the tool draws a markup that can wear a style."""
    if tool_key in _styled_cache:
        return _styled_cache[tool_key]
    tool = TOOL_MAP.get(tool_key)
    answer = False
    if (tool is not None and tool.factory is not None and tool_key not in _NOT_STYLED
            and tool.mode not in (SNAPSHOT, NONE, ERASE)):
        try:
            answer = tool.factory().TYPE in toolsets.PROPERTIES_TYPES
        except Exception:  # noqa: BLE001 - a tool that cannot be sampled has no styles
            answer = False
    _styled_cache[tool_key] = answer
    return answer


def payload_of(item) -> dict:
    """A markup's look, as the Tool Chest keeps a tool in Properties Mode."""
    return toolsets.entry_for(item, toolsets.PROPERTIES).payload


# ---------------------------------------------------------------------------
# pictures
# ---------------------------------------------------------------------------

def preview_pixmap(payload: dict, size: QSize = ICON_SIZE, ratio: float = 2.0) -> QPixmap:
    """The style drawn as a small example of its markup, on a scrap of white
    paper — markups are drawn on paper, so the colours read true in the dark
    theme as well as the light one (the Tool Chest's own thumbnail inside)."""
    from .panels import entry_thumbnail

    width, height = int(size.width() * ratio), int(size.height() * ratio)
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(QColor("#8d9299"))
    painter.setBrush(QColor("#ffffff"))
    painter.drawRoundedRect(QRectF(1, 1, width - 2, height - 2), 3 * ratio, 3 * ratio)
    example = dict(payload)
    if example.get("type") in ("rect", "callout", "text", "note"):
        example.setdefault("rect", list(_EXAMPLE_BOX))
    elif example.get("type") in ("poly", "measure"):
        closed = str(example.get("kind", "")) in _CLOSED_KINDS
        example.setdefault("points", [list(p) for p in
                                      (_EXAMPLE_SHAPE if closed else _EXAMPLE_LINE)])
    entry = toolsets.ToolEntry("style", example, toolsets.PROPERTIES)
    try:
        inner = entry_thumbnail(entry, width - int(4 * ratio), height - int(4 * ratio),
                                max_scale=ratio)
        painter.drawPixmap(int(2 * ratio), int(2 * ratio), inner)
    except Exception:  # noqa: BLE001 - a picture is not worth a crash
        pass
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


# ---------------------------------------------------------------------------
# the toolbar
# ---------------------------------------------------------------------------

def _quietly(command, *args) -> None:
    """Run a command from a button or menu: a Qt slot hands nothing back."""
    command(*args)


class StyleButton(QToolButton):
    """A style on the bar: click to pick it, right-click for its menu, drag it
    along the bar to put it somewhere else."""

    def __init__(self, controller: "MarkupStyles", number: int):
        super().__init__()
        self.controller = controller
        self.number = number
        self._press: Optional[QPoint] = None
        self._dragging = False
        self.setCheckable(True)
        self.setAutoRaise(True)
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.number > 0:
            self._press = event.position().toPoint()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if (self._press is not None and event.buttons() & Qt.LeftButton
                and (event.position().toPoint() - self._press).manhattanLength()
                >= QApplication.startDragDistance()):
            if not self._dragging:
                self._dragging = True
                self.setCursor(Qt.ClosedHandCursor)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging:
            self._dragging = False
            self._press = None
            self.unsetCursor()
            self.setDown(False)
            bar = self.parentWidget()
            target = bar.childAt(bar.mapFromGlobal(self.mapToGlobal(event.position().toPoint()))) \
                if bar is not None else None
            while target is not None and not isinstance(target, StyleButton):
                target = target.parentWidget()
            if isinstance(target, StyleButton) and target.number > 0 \
                    and target.number != self.number:
                self.controller.move_to(self.number, target.number)
            event.accept()
            return
        self._press = None
        super().mouseReleaseEvent(event)


class MarkupStylesBar(QToolBar):
    """Default, then style 1…9, then +, for the tool in hand."""

    def __init__(self, controller: "MarkupStyles"):
        super().__init__("Markup Styles")
        self.controller = controller
        self.setObjectName("toolbar_markup_styles")
        self.setIconSize(ICON_SIZE)
        self.setToolTip("")
        self.buttons: list = []          # [Default, 1, 2, ...]
        self.add_button: Optional[QToolButton] = None
        self.title = QLabel("")
        self.title.setObjectName("markupStylesTitle")
        self._shown_key = object()
        self._dirty = True
        self.visibilityChanged.connect(self._shown)

    def _shown(self, shown: bool) -> None:
        if shown and self._dirty:
            self.refresh()

    def refresh(self, force: bool = False) -> None:
        """Rebuild the buttons for whatever the bar is about now."""
        if not self.isVisibleTo(self.parentWidget() or self) and not force:
            self._dirty = True
            return
        self._dirty = False
        controller = self.controller
        key = controller.tool_key()
        state = (key, json.dumps([s.to_dict() for s in styles_for(key)]) if key else "",
                 json.dumps(controller.default_payload(key)) if key else "",
                 controller.active())
        if state == self._shown_key and not force:
            return
        self._shown_key = state
        self.clear()
        self.buttons = []
        self.add_button = None
        if key is None:
            hint = QLabel("  Markup Styles: pick a markup tool  ")
            hint.setObjectName("markupStylesHint")
            hint.setEnabled(False)
            self.addWidget(hint)
            return
        tool = TOOL_MAP[key]
        letter = tool.shortcut or ""
        self.title = QLabel(f" {tool.label} styles ")
        self.title.setObjectName("markupStylesTitle")
        self.addWidget(self.title)
        active = controller.active()
        default = StyleButton(controller, 0)
        default.setText("Default")
        default.setIcon(QIcon(preview_pixmap(controller.default_payload(key))))
        default.setToolTip(f"Default — how a {tool.label.lower()} is drawn unless a "
                           f"style is picked\nKey: 0" + (f" or {letter}" if letter else ""))
        default.setChecked(active == 0)
        default.clicked.connect(lambda _checked=False: _quietly(controller.pick, 0))
        self.addWidget(default)
        self.buttons.append(default)
        for number, style in enumerate(styles_for(key), start=1):
            button = StyleButton(controller, number)
            button.setObjectName(f"markupStyle{number}")
            button.setText(str(number))
            button.setIcon(QIcon(preview_pixmap(style.payload)))
            button.setToolTip(f"Style {number}: {style.name}\n"
                              f"Key: {letter + ' then ' if letter else ''}{number}\n"
                              "Click to draw with it and edit it in Properties; "
                              "right-click for more; drag to reorder")
            button.setChecked(active == number)
            button.clicked.connect(
                lambda _checked=False, n=number: _quietly(controller.pick, n))
            button.customContextMenuRequested.connect(
                lambda point, b=button: self._menu(b, point))
            self.addWidget(button)
            self.buttons.append(button)
        self.addSeparator()
        plus = QToolButton()
        plus.setObjectName("markupStyleAdd")
        plus.setText("+")
        plus.setAutoRaise(True)
        full = len(self.buttons) - 1 >= MAX_STYLES
        plus.setEnabled(not full)
        plus.setToolTip("Save the current look as a new style" if not full
                        else f"A tool holds at most {MAX_STYLES} styles")
        plus.clicked.connect(lambda _checked=False: _quietly(controller.add_style))
        self.addWidget(plus)
        self.add_button = plus

    def _menu(self, button, point) -> None:
        menu = self.controller.build_menu(button.number)
        menu.exec(button.mapToGlobal(point))
        menu.deleteLater()


# ---------------------------------------------------------------------------
# the controller
# ---------------------------------------------------------------------------

class MarkupStyles(QObject):
    """Ties the toolbar, the number keys, the Properties toolbar and panel and
    the held tool together."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.bar = MarkupStylesBar(self)
        self._panel_item = None
        view = window.view
        view.toolChanged.connect(self._tool_changed)
        view.markupStyleChanged.connect(self._style_changed)
        view.selectionChanged.connect(self._selection_changed)
        self.bar.refresh(force=True)

    # -- what the bar is about ---------------------------------------------
    def tool_key(self) -> Optional[str]:
        """The tool whose styles are shown: the one in hand, or — with only
        Select in hand — the kind of the markup(s) selected, when that is one
        styled kind."""
        view = self.window.view
        key = view.tool_key
        if styled(key):
            return key
        if key != "select":
            return None
        items = self.window.selected_items()
        if not items:
            return None
        kinds = {self.tool_for_item(item) for item in items}
        if len(kinds) == 1:
            only = kinds.pop()
            return only if only and styled(only) else None
        return None

    def tool_for_item(self, item) -> Optional[str]:
        """The tool that draws markups like *item* (worked out once per kind:
        a selection of hundreds must not cost hundreds of look-ups)."""
        kind = (getattr(item, "TYPE", ""),
                getattr(item, "kind", "") or getattr(item, "shape_kind", ""))
        if kind not in _tool_by_kind:
            try:
                _tool_by_kind[kind] = self.window._tool_for_payload(
                    {"type": kind[0], "kind": kind[1]} if kind[1] else {"type": kind[0]})
            except Exception:  # noqa: BLE001 - a markup with no tool of its own
                _tool_by_kind[kind] = None
        return _tool_by_kind[kind]

    def active(self) -> int:
        """The style the next markup is drawn in: 0 for the default."""
        return int(getattr(self.window.view, "markup_style", 0) or 0)

    def sample(self, key: str, number: int = 0):
        """A markup of the tool's kind, dressed as style *number* would draw it."""
        tool = TOOL_MAP.get(key)
        if tool is None or tool.factory is None:
            return None
        item = tool.factory()
        self.window.apply_default_style(item)
        if number:
            entries = styles_for(key)
            if 1 <= number <= len(entries):
                toolsets.apply_properties(item, entries[number - 1].payload)
        return item

    def default_payload(self, key: Optional[str]) -> dict:
        if not key:
            return {}
        item = self.sample(key)
        return payload_of(item) if item is not None else {}

    # -- picking -----------------------------------------------------------
    def pick(self, number: int) -> bool:
        """Draw the next markup in style *number* (0: the default) — the
        toolbar's click. With Select in hand it picks the tool up first."""
        key = self.tool_key()
        if key is None:
            return False
        view = self.window.view
        if view.tool_key != key:
            self.window.select_tool(key)
        return self.activate(number)

    def activate(self, number: int) -> bool:
        view = self.window.view
        key = view.tool_key
        if not styled(key):
            return False
        entries = styles_for(key)
        if number and not (1 <= number <= len(entries)):
            self.bar.refresh()
            return False
        scene = view.scene()
        if scene is not None and scene.selectedItems() and view.editing_item() is None:
            # As a tool picked in Revu's Tool Chest: what is edited from now on
            # is the style, not the markup that happened to be selected.
            scene.clearSelection()
        if number:
            view.set_markup_style(number, entries[number - 1].payload)
            self.window.status_hint.setText(
                f"{TOOL_MAP[key].label} style {number}: {entries[number - 1].name} — "
                "the next one is drawn in it")
        else:
            view.set_markup_style(0, None)
            self.window.status_hint.setText(f"{TOOL_MAP[key].label}: default style")
        return True

    def key_press(self, event) -> bool:
        """1–9 (and 0) with a drawing tool in hand, and the tool's own letter
        again for its default. False leaves the key to everything else."""
        from . import preferences
        from .shortcuts import TOOL
        from .view import typing_somewhere_else

        view = self.window.view
        text = event.text()
        if not text or not styled(view.tool_key) or view.calc.calc_mode():
            return False
        if (view.editing_item() is not None or view._label_editor is not None
                or view._size_editor is not None or view._draft is not None
                or view._mode != "idle" or view.tables.is_open()
                or typing_somewhere_else()):
            return False
        modifiers = event.modifiers() & ~Qt.KeypadModifier
        if text.isdigit() and len(text) == 1 and not (
                modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)):
            if not preferences.current().markup_style_keys:
                return False
            number = int(text)
            if number and number > len(styles_for(view.tool_key)):
                self.window.status_hint.setText(
                    f"{TOOL_MAP[view.tool_key].label} has no style {number} — "
                    "+ on the Markup Styles toolbar saves one")
                return True
            return self.activate(number)
        binding = self.window.shortcuts.match_typed(text, event.modifiers(), view.calc.mode)
        if binding is not None and binding.kind == TOOL and binding.payload == view.tool_key:
            # The tool's own letter again: its default.
            if self.active():
                self.activate(0)
            return True
        return False

    # -- the bar's commands ------------------------------------------------
    def _selected_of_kind(self, key: str):
        items = self.window.selected_items()
        if len(items) == 1 and self.tool_for_item(items[0]) == key:
            return items[0]
        return None

    def add_style(self, name: str = "") -> int:
        """+: keep the current look as a new style. Returns its number."""
        key = self.tool_key()
        if key is None:
            return 0
        entries = styles_for(key)
        if len(entries) >= MAX_STYLES:
            self.window.status_hint.setText(f"A tool holds at most {MAX_STYLES} styles")
            return 0
        selected = self._selected_of_kind(key) if self.window.view.tool_key == "select" \
            else None
        source = selected if selected is not None else self.sample(key, self.active())
        number = len(entries) + 1
        entries.append(MarkupStyle(name or f"Style {number}", payload_of(source)))
        set_styles_for(key, entries)
        if self.window.view.tool_key != key:
            self.window.select_tool(key)
        self.activate(number)
        self.bar.refresh(force=True)
        return number

    def rename(self, number: int, name: str = "") -> bool:
        key = self.tool_key()
        entries = styles_for(key) if key else []
        if not (1 <= number <= len(entries)):
            return False
        if not name:
            if not self.window.interactive_prompts:
                return False
            name, accepted = QInputDialog.getText(
                self.window, "Rename Style", "Name:", text=entries[number - 1].name)
            if not accepted or not name.strip():
                return False
        entries[number - 1].name = name.strip()
        set_styles_for(key, entries)
        self.bar.refresh(force=True)
        return True

    def update_from_selected(self, number: int) -> bool:
        key = self.tool_key()
        entries = styles_for(key) if key else []
        item = self._selected_of_kind(key) if key else None
        if item is None or not (1 <= number <= len(entries)):
            return False
        entries[number - 1].payload = payload_of(item)
        set_styles_for(key, entries)
        self._reapply(number)
        self.bar.refresh(force=True)
        return True

    def remove(self, number: int) -> bool:
        key = self.tool_key()
        entries = styles_for(key) if key else []
        if not (1 <= number <= len(entries)):
            return False
        del entries[number - 1]
        set_styles_for(key, entries)
        active = self.active()
        if active == number:
            self.window.view.set_markup_style(0, None)
        elif active > number:
            self._renumber(active - 1)
        self.bar.refresh(force=True)
        return True

    def move_to(self, number: int, place: int) -> bool:
        """Move style *number* so it becomes style *place*."""
        key = self.tool_key()
        entries = styles_for(key) if key else []
        if not (1 <= number <= len(entries)) or not (1 <= place <= len(entries)) \
                or number == place:
            return False
        moving = entries.pop(number - 1)
        entries.insert(place - 1, moving)
        set_styles_for(key, entries)
        active = self.active()
        if active:
            order = list(range(1, len(entries) + 1))
            old = order.pop(number - 1)
            order.insert(place - 1, old)
            self._renumber(order.index(active) + 1)
        self.bar.refresh(force=True)
        return True

    def move(self, number: int, step: int) -> bool:
        return self.move_to(number, number + step)

    def _renumber(self, number: int) -> None:
        """The held style moved place on the bar: it is still the one held."""
        view = self.window.view
        view.markup_style = number
        self.bar.refresh(force=True)

    def _reapply(self, number: int) -> None:
        """A style that is held changed: the next markup wears the change."""
        view = self.window.view
        if self.active() == number:
            entries = styles_for(view.tool_key)
            if 1 <= number <= len(entries):
                view.set_markup_style(number, entries[number - 1].payload)

    def build_menu(self, number: int) -> QMenu:
        """The right-click menu of a style on the bar."""
        key = self.tool_key()
        count = len(styles_for(key)) if key else 0
        menu = QMenu(self.bar)

        def entry(text, command, *args):
            action = menu.addAction(text)
            action.triggered.connect(lambda _checked=False: _quietly(command, *args))
            return action
        entry("Rename…", self.rename, number)
        update = entry("Update from Selected Markup", self.update_from_selected, number)
        update.setEnabled(key is not None and self._selected_of_kind(key) is not None)
        if not update.isEnabled():
            update.setToolTip("Select one markup of this kind first")
        entry("Remove", self.remove, number)
        menu.addSeparator()
        entry("Move Left", self.move, number, -1).setEnabled(number > 1)
        entry("Move Right", self.move, number, 1).setEnabled(number < count)
        return menu

    # -- the Properties toolbar and panel edit the held style --------------
    def editing(self) -> int:
        """The style the Properties toolbar and panel are editing: the held
        one, while nothing is selected."""
        if self.active() and not self.window.selected_items():
            return self.active()
        return 0

    def edit(self, mutate) -> bool:
        """A Properties toolbar control moved. True if it changed the held
        style (*mutate* is given the sample markup to change)."""
        number = self.editing()
        if not number:
            return False
        key = self.window.view.tool_key
        item = self.sample(key, number)
        if item is None:
            return False
        mutate(item)
        if hasattr(item, "apply_style"):
            item.apply_style()
        self._store(key, number, item)
        properties = getattr(self.window, "properties_panel", None)
        if properties is not None:
            properties.show_items(self.window.selected_items())
        self.window._refresh_style_controls()
        return True

    def _store(self, key: str, number: int, item) -> None:
        entries = styles_for(key)
        if not (1 <= number <= len(entries)):
            return
        entries[number - 1].payload = payload_of(item)
        set_styles_for(key, entries)
        view = self.window.view
        view._pending_properties = dict(entries[number - 1].payload)
        view._preview_key = None
        self.bar.refresh()

    def dress(self, item) -> None:
        """The Properties toolbar is about to show the tool's look: with a
        style being edited, that style's."""
        number = self.editing()
        if not number:
            return
        self.window.apply_default_style(item)
        entries = styles_for(self.window.view.tool_key)
        if 1 <= number <= len(entries):
            toolsets.apply_properties(item, entries[number - 1].payload)

    def panel_sample(self):
        """What the Properties panel edits with nothing selected: the held
        style, as (sample markup, heading, called after each change)."""
        number = self.editing()
        if not number:
            self._panel_item = None
            return None
        key = self.window.view.tool_key
        entries = styles_for(key)
        if not (1 <= number <= len(entries)):
            return None
        item = self.sample(key, number)
        self._panel_item = item
        title = f"{TOOL_MAP[key].label} Style {number} — {entries[number - 1].name}"

        def changed(edited, key=key, number=number) -> None:
            if self.editing() == number and self.window.view.tool_key == key:
                self._store(key, number, edited)
                self.window._refresh_style_controls()
        return item, title, changed

    # -- keeping up --------------------------------------------------------
    def _style_changed(self, _number: int) -> None:
        self.bar.refresh()
        window = self.window
        properties = getattr(window, "properties_panel", None)
        if properties is not None:
            properties.show_items(window.selected_items())
        if hasattr(window, "_style_widgets"):
            window._refresh_style_controls()

    def _tool_changed(self, _key: str) -> None:
        self.bar.refresh()

    def _selection_changed(self) -> None:
        if self.window.view.tool_key == "select":
            self.bar.refresh()
