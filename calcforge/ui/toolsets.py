"""Default properties, and tool sets.

Two things that both answer "I want the next one to look like that one":

*Defaults* remember how a kind of markup should be drawn — the colour, the
thickness, the font — so every rectangle after the first comes out the way you
set the first one up.

*Tool sets* are Bluebeam's tool chest: named collections holding anything at
all, each entry usable two ways. **As a copy** it puts back exactly what was
added, contents and all — a text box comes back with its words in it. **As
properties** it draws a new one of that kind wearing the stored properties, and
you draw it where and how big you like.

Both live in the user's settings rather than in the document, because they
belong to the person, not to the job.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from PySide6.QtCore import QSettings

from ..settings import app_settings

DEFAULTS_KEY = "markups/defaults"
TOOLSETS_KEY = "toolsets/sets"
MY_TOOLS = "My Tools"

COPY = "copy"                # put back exactly what was added
PROPERTIES = "properties"    # draw a new one wearing its properties

# What makes a markup *that* markup rather than a markup of that kind: where it
# is, how big, and what it says. None of it belongs in a default or in a
# properties-mode tool.
CONTENT_KEYS = frozenset({
    "uid", "x", "y", "z", "rotation", "rect", "points", "leader", "source",
    "text", "html", "sheet", "asset", "asset_key", "created", "modified", "subject",
    "comment", "label", "named_cells", "table_name", "series", "index",
    "custom_label", "value", "background_key", "title",
    # which of Revu's two kinds a rectangle or ellipse is — plain or Sketch
    # to Scale — comes from the tool that draws it, never from a look
    "to_scale",
})


def _settings() -> QSettings:
    return app_settings()


def default_key(item) -> str:
    """The kind of markup this is, for the purpose of remembering a default.

    A rectangle and an ellipse are both ``RectItem`` but nobody thinks of them
    as the same tool, so the kind is part of the key.
    """
    kind = getattr(item, "kind", "") or getattr(item, "shape_kind", "")
    key = f"{item.TYPE}:{kind}" if kind else item.TYPE
    # Sketch to Scale's rectangle is a tool of its own, with its own default
    return f"{key}:scale" if getattr(item, "to_scale", False) else key


def properties_of(item) -> dict:
    """Everything about a markup except what makes it that particular one."""
    return {key: value for key, value in item.serialize().items()
            if key not in CONTENT_KEYS}


def apply_properties(item, properties: dict) -> None:
    """Put stored properties onto an item, leaving its own content alone."""
    if not properties:
        return
    data = item.serialize()
    data.update({key: value for key, value in properties.items()
                 if key not in CONTENT_KEYS})
    item.deserialize(data)
    doc = getattr(item, "doc", None)
    if doc is not None and hasattr(doc, "toPlainText") and not doc.toPlainText():
        # A box with no words yet keeps none of its old look either: the
        # empty line read back from it carried the old font — 10 pt, not
        # bold, not italic — and what was typed took that rather than the
        # style's (the user, 2026-10-16: a bold text box style drew plain).
        doc.clear()
    if hasattr(item, "apply_style"):
        item.apply_style()


# ---------------------------------------------------------------------------
# defaults
# ---------------------------------------------------------------------------

def load_defaults() -> dict:
    stored = _settings().value(DEFAULTS_KEY, "")
    try:
        return json.loads(stored) if stored else {}
    except (ValueError, TypeError):
        return {}


def save_defaults(defaults: dict) -> None:
    settings = _settings()
    settings.setValue(DEFAULTS_KEY, json.dumps(defaults))
    settings.sync()


def remember_default(item) -> str:
    """Make this markup's properties the ones its kind is drawn with."""
    defaults = load_defaults()
    key = default_key(item)
    defaults[key] = properties_of(item)
    save_defaults(defaults)
    return key


def forget_default(key: str) -> None:
    defaults = load_defaults()
    if defaults.pop(key, None) is not None:
        save_defaults(defaults)


def apply_default(item) -> bool:
    """Draw this new markup the way its kind was last set up. True if it was."""
    stored = load_defaults().get(default_key(item))
    if not stored:
        return False
    apply_properties(item, stored)
    return True


# ---------------------------------------------------------------------------
# tool sets
# ---------------------------------------------------------------------------

@dataclass
class ToolEntry:
    """One thing in a tool set."""

    label: str
    payload: dict = field(default_factory=dict)
    mode: str = COPY
    # Revu's Scale: a tool put down exactly (Drawing Mode) keeps its real
    # size from one drawing scale to another — a 1 m desk kept off a 1:100
    # plan comes down twice the size on a 1:50 one. What a point measured
    # where it was kept, in mm; 0 when that page had no scale.
    scaled: bool = False
    mm_per_pt: float = 0.0

    def to_dict(self) -> dict:
        data = {"label": self.label, "payload": self.payload, "mode": self.mode}
        if self.scaled:
            data["scaled"] = True
        if self.mm_per_pt:
            data["mm_per_pt"] = self.mm_per_pt
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ToolEntry":
        return cls(str(data.get("label", "Tool")), dict(data.get("payload", {})),
                   data.get("mode", COPY), bool(data.get("scaled", False)),
                   float(data.get("mm_per_pt", 0.0) or 0.0))

    @property
    def type_name(self) -> str:
        return str(self.payload.get("type", ""))

    def size_on(self, page) -> float:
        """How much bigger it comes down on *page*, scaled: 1 unless Scale is
        on and both its own page and this one have a drawing scale."""
        if not self.scaled or self.mode != COPY or not self.mm_per_pt:
            return 1.0
        here = mm_per_pt(page)
        return self.mm_per_pt / here if here else 1.0


def mm_per_pt(page) -> float:
    """What one point on *page* measures, in mm — 0 if it has no scale."""
    scale = getattr(page, "scale", None)
    if scale is None or not getattr(scale, "calibrated", False):
        return 0.0
    try:
        return float(scale.length_per_pt.to("mm").magnitude)
    except Exception:  # noqa: BLE001 - a unit that will not convert: no scale
        return 0.0


def _kept_from(item) -> float:
    return mm_per_pt(getattr(item.parentItem(), "page", None))


# Only a single markup can be kept "as properties": an image or a snapshot has
# nothing worth drawing again without its contents, and a group is several
# things at once.
PROPERTIES_TYPES = {"rect", "poly", "text", "callout", "note", "stamp",
                    "measure", "count"}


def can_be_properties(payload: dict) -> bool:
    """Whether this entry could sensibly be drawn again as a fresh markup."""
    return str(payload.get("type", "")) in PROPERTIES_TYPES


@dataclass
class ToolSet:
    """A named collection of tools."""

    name: str
    entries: list = field(default_factory=list)
    hidden: bool = False      # unticked in Manage Tool Sets: kept, not shown

    def to_dict(self) -> dict:
        data = {"name": self.name, "entries": [e.to_dict() for e in self.entries]}
        if self.hidden:
            data["hidden"] = True
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ToolSet":
        return cls(str(data.get("name", "Tools")),
                   [ToolEntry.from_dict(entry) for entry in data.get("entries", [])],
                   bool(data.get("hidden", False)))


def load_toolsets() -> list:
    """Every tool set, with My Tools always first and always present."""
    stored = _settings().value(TOOLSETS_KEY, "")
    try:
        sets = [ToolSet.from_dict(entry) for entry in (json.loads(stored) if stored else [])]
    except (ValueError, TypeError):
        sets = []
    if not any(group.name == MY_TOOLS for group in sets):
        sets.insert(0, ToolSet(MY_TOOLS))
    sets.sort(key=lambda group: group.name != MY_TOOLS)
    return sets


def save_toolsets(sets: list) -> None:
    settings = _settings()
    settings.setValue(TOOLSETS_KEY, json.dumps([group.to_dict() for group in sets]))
    settings.sync()


def entry_for(item, mode: str = COPY, label: str = "") -> ToolEntry:
    """Turn a markup on the page into something a tool set can hold."""
    payload = item.serialize()
    if mode == PROPERTIES:
        payload = {key: value for key, value in payload.items()
                   if key not in CONTENT_KEYS}
        payload["type"] = item.TYPE
        kind = getattr(item, "kind", "") or getattr(item, "shape_kind", "")
        if kind:
            payload.setdefault("kind", kind)
        if getattr(item, "to_scale", False):
            # drawn again with Sketch to Scale's tool, not the plain one
            payload["to_scale"] = True
    return ToolEntry(label or describe(item), payload, mode, mm_per_pt=_kept_from(item))


def entry_for_many(items: list, label: str = "") -> ToolEntry:
    """Several markups kept as one tool, laid out as they are on the page.

    A group is one thing, so it goes into a set as one entry and comes back
    as one: every member, in the same arrangement, grouped again.
    """
    items = list(items)
    if len(items) == 1:
        return entry_for(items[0])
    left = min(item.pos().x() for item in items)
    top = min(item.pos().y() for item in items)
    parts = []
    for item in items:
        data = item.serialize()
        data["x"] = float(data.get("x", 0.0)) - left
        data["y"] = float(data.get("y", 0.0)) - top
        parts.append(data)
    payload = {"type": GROUP, "items": parts}
    name = label or f"Group of {len(items)}"
    return ToolEntry(name, payload, COPY, mm_per_pt=_kept_from(items[0]))


GROUP = "__group__"     # what a multi-markup entry's payload calls itself


def entry_for_block(block, label: str = "") -> ToolEntry:
    """A calculation block and the equations in it, as one tool. They come
    back down as they are on the page, but not grouped: a block holds its
    equations itself, and each is still clicked into on its own."""
    entry = entry_for_many([block] + block.members(), label or describe(block))
    entry.payload["ungrouped"] = True
    return entry


# ---------------------------------------------------------------------------
# bringing a Bluebeam tool set in
# ---------------------------------------------------------------------------

def toolset_from_btx(path) -> tuple["ToolSet", int]:
    """Read a Bluebeam ``.btx`` file into a tool set. Returns it and what it
    could not read.

    A tool made of one markup becomes one entry; a tool made of several — a
    section with its centre line and its label, say — becomes a group entry,
    so it comes back onto the page in one piece exactly as it went in.
    """
    from ..io import btx

    imported = btx.read(path)
    entries = []
    for tool in imported.tools:
        if len(tool.payloads) == 1:
            payload = dict(tool.payloads[0])
        else:
            payload = {"type": GROUP, "items": [dict(p) for p in tool.payloads]}
        entries.append(ToolEntry(tool.name or "Tool", payload, COPY))
    return ToolSet(imported.name, entries), imported.skipped


def add_toolset(group: "ToolSet") -> "ToolSet":
    """Store a tool set, giving it a fresh name if that one is taken."""
    sets = load_toolsets()
    taken = {existing.name for existing in sets}
    name = group.name
    suffix = 2
    while name in taken:
        name = f"{group.name} ({suffix})"
        suffix += 1
    group.name = name
    sets.append(group)
    save_toolsets(sets)
    return group


def describe(item) -> str:
    """A short name for a markup, for the row in the panel."""
    words = (getattr(item, "summary", lambda: "")() or "").strip().replace("\n", " ")
    name = item.display_name() if hasattr(item, "display_name") else item.NAME
    return f"{name} — {words[:40]}" if words else name
