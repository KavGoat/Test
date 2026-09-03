"""The handful of choices that belong to the person, not the document.

A page size belongs to the document and travels with it. Whether the wheel
zooms, whether a new block keeps its names to itself, whether spelling is
checked — those belong to whoever is sitting at the desk, so they live in
QSettings and are the same in every document they open.

Everything here has a default that is right for most people, so the
preferences page is somewhere to go when one of them is wrong for you, not
somewhere you have to visit before you can start.
"""
from __future__ import annotations

from dataclasses import dataclass, fields

from PySide6.QtCore import QSettings

PREFIX = "preferences/"

# What the wheel does with no modifier held.
WHEEL_ZOOM = "zoom"
WHEEL_SCROLL = "scroll"


@dataclass
class Preferences:
    """Every preference, its type and its default, in one place."""

    wheel: str = WHEEL_ZOOM
    """Whether a notch of the wheel zooms (as Bluebeam does) or scrolls."""

    self_contained_blocks: bool = False
    """Whether a new block hides its names from the rest of the page."""

    check_spelling: bool = True
    """Whether words typed on the page are checked against the dictionary."""

    dictionary: str = "en_NZ"
    """Which spelling to check against."""

    snap_while_drawing: bool = True
    """Whether a markup being drawn catches on what is already on the page."""

    autosize_text: bool = True
    """Whether a text box grows to fit what is typed into it."""

    def wheel_zooms(self) -> bool:
        return self.wheel == WHEEL_ZOOM


_current: Preferences | None = None


def _settings() -> QSettings:
    return QSettings("CalcForge", "CalcForge")


def _as_bool(value, fallback: bool) -> bool:
    """QSettings hands booleans back as the strings it wrote them as."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return fallback


def load() -> Preferences:
    """Read the preferences, falling back to the defaults one by one.

    One unreadable value must not cost the others, so each is taken on its
    own rather than the whole record being thrown away.
    """
    settings = _settings()
    prefs = Preferences()
    for field in fields(Preferences):
        stored = settings.value(PREFIX + field.name, None)
        if stored is None:
            continue
        default = getattr(prefs, field.name)
        if isinstance(default, bool):
            setattr(prefs, field.name, _as_bool(stored, default))
        else:
            setattr(prefs, field.name, str(stored))
    return prefs


def save(prefs: Preferences) -> None:
    settings = _settings()
    for field in fields(Preferences):
        settings.setValue(PREFIX + field.name, getattr(prefs, field.name))
    settings.sync()


def current() -> Preferences:
    """The preferences in force, read once and kept."""
    global _current
    if _current is None:
        _current = load()
    return _current


def apply(prefs: Preferences) -> None:
    """Adopt and remember a new set of preferences."""
    global _current
    _current = prefs
    save(prefs)


def forget() -> None:
    """Drop the cached copy — used by the tests between runs."""
    global _current
    _current = None
