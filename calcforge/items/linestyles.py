"""Line styles of one's own, beside the built-in ones (Revu's Line Style
Manage…; the user's screenshots, 2026-10-16).

A line style is a run of dashes and gaps, in points, the same as the
built-in ones in :data:`calcforge.items.base.DASH_ARRAYS`. One's own are kept
in the settings and added to that list, so every list that offers a line
style offers them. A markup given one carries its dashes with it
(``Style.dash_array``), so it is drawn the same on a computer that has never
heard of the style, and in any other PDF reader (the border's /D).
"""
from __future__ import annotations

import json
import re

from .base import DASH_ARRAYS

#: What a line-style list's first row carries: open Line Styles.
MANAGE = "__manage_lines__"

#: One's own styles, by name: their dashes and gaps, in points.
CUSTOM: dict[str, list[float]] = {}

CUSTOM_KEY = "linestyles/custom"

#: Points in an inch and in a millimetre, for an AutoCAD .lin file.
LIN_UNITS = {"in": 72.0, "mm": 72.0 / 25.4}


def built_in(name: str) -> bool:
    return name in DASH_ARRAYS and name not in CUSTOM


def named(name) -> str:
    """The built-in style a Bluebeam file's /LineStyleName means — Revu's
    "Dashed 1", "Fenceline Circle", "Hot Water", "Zig Zag" however it is
    spaced or cased — or "" for any other name."""
    if not isinstance(name, str):
        return ""
    squeezed = "".join(character for character in name.lower() if character.isalnum())
    for key in DASH_ARRAYS:
        if built_in(key) and "".join(c for c in key if c.isalnum()) == squeezed:
            return key
    return ""


def parse_dashes(text: str) -> list[float]:
    """Dashes and gaps typed as numbers — "6, 2, 1, 2" — in points. Empty
    when the text is not a pattern: a run needs a dash and a gap, none
    negative, and something to draw."""
    try:
        steps = [abs(float(part)) for part in re.split(r"[,\s]+", text.strip()) if part]
    except ValueError:
        return []
    if len(steps) < 2 or len(steps) % 2 or not any(steps[0::2]) or not any(steps[1::2]):
        return []
    return steps


def parse_lin(text: str, unit: str = "in") -> dict[str, list[float]]:
    """The simple line types in an AutoCAD .lin file: ``*NAME,description``
    then ``A,dash,-gap,0,…`` (a dot is 0). Lengths in *unit*. Complex types
    (with text or shapes in brackets) are left out."""
    scale = LIN_UNITS.get(unit, LIN_UNITS["in"])
    found: dict[str, list[float]] = {}
    name = ""
    for raw in text.splitlines():
        line = raw.split(";;")[0].strip()
        if line.startswith("*"):
            name = line[1:].split(",")[0].strip()
            continue
        if not name or not line.upper().startswith("A,") or "[" in line:
            continue
        steps = []
        for part in line[2:].split(","):
            part = part.strip()
            if not part:
                continue
            try:
                value = float(part)
            except ValueError:
                steps = []
                break
            # a dot is drawn as a dash a point long, so it shows
            steps.append(max(abs(value) * scale, 0.5 if value == 0 else 0.0))
        if steps and len(steps) % 2:
            steps.append(steps[-1])          # an odd run repeats as AutoCAD's does
        if parse_dashes(", ".join(f"{s:g}" for s in steps)):
            found[name] = [round(s, 3) for s in steps]
        name = ""
    return found


def add_style(name: str, dashes) -> str:
    """Add (or replace) one's own style. Its name, or "" if it cannot be
    added: no name, a built-in style's name, or no pattern."""
    name = " ".join((name or "").split())
    steps = [float(step) for step in dashes or []]
    if not name or name.lower() in {key.lower() for key in DASH_ARRAYS if built_in(key)} \
            or name == MANAGE or len(steps) < 2:
        return ""
    CUSTOM[name] = steps
    DASH_ARRAYS[name] = list(steps)
    return name


def remove_style(name: str) -> bool:
    """Take one's own style out; the built-in ones stay."""
    if name not in CUSTOM:
        return False
    del CUSTOM[name]
    DASH_ARRAYS.pop(name, None)
    return True


def save_custom() -> None:
    from ..settings import app_settings
    app_settings().setValue(CUSTOM_KEY, json.dumps(CUSTOM))


def load_custom() -> None:
    """One's own styles, from the settings, into every line-style list."""
    from ..settings import app_settings
    try:
        data = json.loads(app_settings().value(CUSTOM_KEY, "") or "{}")
    except (TypeError, ValueError):
        data = {}
    for name in list(CUSTOM):
        remove_style(name)
    for name, steps in (data or {}).items():
        try:
            add_style(str(name), [float(step) for step in steps])
        except (TypeError, ValueError):
            continue


def apply(style, name: str) -> None:
    """Give *style* the line style *name*. One's own goes with its dashes,
    so the markup is drawn the same wherever it is opened."""
    style.line_style = name
    style.dash_array = tuple(CUSTOM[name]) if name in CUSTOM else ()
