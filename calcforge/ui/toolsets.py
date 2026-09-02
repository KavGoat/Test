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
from typing import Any, Optional

from PySide6.QtCore import QSettings

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
    "text", "html", "sheet", "asset_key", "created", "modified", "subject",
    "comment", "label", "named_cells", "table_name", "series", "index",
    "custom_label", "value", "background_key", "title",
})


def _settings() -> QSettings:
    return QSettings("CalcForge", "CalcForge")


def default_key(item) -> str:
    """The kind of markup this is, for the purpose of remembering a default.

    A rectangle and an ellipse are both ``RectItem`` but nobody thinks of them
    as the same tool, so the kind is part of the key.
    """
    kind = getattr(item, "kind", "") or getattr(item, "shape_kind", "")
    return f"{item.TYPE}:{kind}" if kind else item.TYPE


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

    def to_dict(self) -> dict:
        return {"label": self.label, "payload": self.payload, "mode": self.mode}

    @classmethod
    def from_dict(cls, data: dict) -> "ToolEntry":
        return cls(str(data.get("label", "Tool")), dict(data.get("payload", {})),
                   data.get("mode", COPY))

    @property
    def type_name(self) -> str:
        return str(self.payload.get("type", ""))


@dataclass
class ToolSet:
    """A named collection of tools."""

    name: str
    entries: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"name": self.name, "entries": [e.to_dict() for e in self.entries]}

    @classmethod
    def from_dict(cls, data: dict) -> "ToolSet":
        return cls(str(data.get("name", "Tools")),
                   [ToolEntry.from_dict(entry) for entry in data.get("entries", [])])


def load_toolsets() -> list:
    """Every tool set, with My Tools always first and always present."""
    stored = _settings().value(TOOLSETS_KEY, "")
    try:
        sets = [ToolSet.from_dict(entry) for entry in (json.loads(stored) if stored else [])]
    except (ValueError, TypeError):
        sets = []
    if not any(group.name == MY_TOOLS for group in sets):
        sets.insert(0, ToolSet(MY_TOOLS))
    sets.sort(key=lambda group: 0 if group.name == MY_TOOLS else 1)
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
    return ToolEntry(label or describe(item), payload, mode)


def describe(item) -> str:
    """A short name for a markup, for the row in the panel."""
    words = (getattr(item, "summary", lambda: "")() or "").strip().replace("\n", " ")
    name = item.display_name() if hasattr(item, "display_name") else item.NAME
    return f"{name} — {words[:40]}" if words else name
