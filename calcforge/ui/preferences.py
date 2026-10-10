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
from dataclasses import field as _field

from PySide6.QtCore import QSettings

from ..settings import app_settings

PREFIX = "preferences/"

# What the wheel does with no modifier held.
WHEEL_ZOOM = "zoom"
WHEEL_SCROLL = "scroll"


def login_name() -> str:
    """The name the computer knows its user by: what Bluebeam signs markups with."""
    import getpass
    import os
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 — no login name to be had
        return os.environ.get("USERNAME") or os.environ.get("USER") or ""


@dataclass
class Preferences:
    """Every preference, its type and its default, in one place."""

    wheel: str = WHEEL_ZOOM
    """Whether a notch of the wheel zooms (as Bluebeam does) or scrolls."""

    author: str = _field(default_factory=login_name)
    """The name new markups are signed with (the login name to begin with,
    as Bluebeam does; 2026-10-10). Saved PDFs carry it as each annotation's
    author."""

    check_spelling: bool = True
    """Whether words typed on the page are checked against the dictionary."""

    dictionary: str = "en_NZ"
    """Which spelling to check against."""

    snap_while_drawing: bool = True
    """Whether a markup being drawn catches on what is already on the page."""

    autosize_text: bool = True
    """Whether a text box grows to fit what is typed into it."""

    insertion_point: bool = False
    """Whether an empty-canvas click leaves an insertion point to type at."""

    gpu_drawing: bool = True
    """Draw the pages with the graphics card (OpenGL): scrolling and panning
    stay smooth on a high-density display, where moving every pixel on the
    processor stutters. Falls back to the processor where there is no
    OpenGL."""

    recover_flattened: bool = True
    """Keep source item data when content is flattened into the page."""

    page_thumbnails: float = 1.0
    """How big the pictures in the page list are, as a multiple of their
    ordinary size. Ctrl and the wheel over the list changes it."""

    # -- calculations (decision 20 / phase 5): SMath's Tools > Options ------------
    result_decimals: int = 4
    """Decimal places a result is shown with, unless an equation says otherwise."""

    result_threshold: int = 5
    """Exponential threshold: longer numbers are shown with a power of ten."""

    result_trailing_zeros: bool = False
    """Whether 2.5 is shown as 2.5000 at four decimals."""

    result_fractions: str = "decimal"
    """decimal, fraction or auto."""

    equation_font_size: float = 10.0
    """The size a new equation is written at, in points."""

    equation_colour: str = "#000000"
    """The colour a new equation is written in."""

    def result_format(self) -> dict:
        """The number format these say, as a document keeps it."""
        return {"decimals": int(self.result_decimals), "threshold": int(self.result_threshold),
                "trailing_zeros": bool(self.result_trailing_zeros),
                "fractions": str(self.result_fractions)}

    def wheel_zooms(self) -> bool:
        return self.wheel == WHEEL_ZOOM


_current: Preferences | None = None


def _settings() -> QSettings:
    return app_settings()


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
        elif isinstance(default, int):
            try:
                setattr(prefs, field.name, int(stored))
            except (TypeError, ValueError):
                pass
        elif isinstance(default, float):
            # QSettings hands back whatever it wrote, and on some platforms
            # that is the string of it. A number that will not parse is a
            # number to ignore, not a reason to lose the rest.
            try:
                setattr(prefs, field.name, float(stored))
            except (TypeError, ValueError):
                pass
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
