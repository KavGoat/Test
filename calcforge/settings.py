"""Application settings with an explicit test/development override."""
from __future__ import annotations

import os

from PySide6.QtCore import QSettings

APP_NAME = "CalcForge"
ORGANISATION = "CalcForge"
SETTINGS_FILE_ENV = "CALCFORGE_SETTINGS_FILE"


def app_settings() -> QSettings:
    """Return CalcForge's persistent settings store.

    Qt's two-string QSettings constructor always selects the native plist on
    macOS, even after ``setDefaultFormat``.  The explicit file override keeps
    automated runs out of a person's real preferences on every platform.
    """
    filename = os.environ.get(SETTINGS_FILE_ENV)
    if filename:
        return QSettings(filename, QSettings.IniFormat)
    return QSettings(ORGANISATION, APP_NAME)


# -- bringing MarkForge's settings across (phase 8) -----------------------------------------

# Where MarkForge kept its settings, and an override for tests and tools so an
# automated run never reads a person's real MarkForge preferences.
MARKFORGE_NAME = "MarkForge"
MARKFORGE_SETTINGS_FILE_ENV = "CALCFORGE_MARKFORGE_SETTINGS_FILE"
MIGRATED_KEY = "migration/from_markforge"

# What comes across: the theme (dark mode), markup defaults, tool sets (My
# Tools is one of them), and the layout — toolbars, panels and the window.
MIGRATED_KEYS = ("theme", "markups/defaults", "toolsets/sets",
                 "window/geometry", "window/state", "window/maximised",
                 "window/markups_list")
MIGRATED_GROUPS = ("shortcuts", "toolbars", "panels")


def markforge_settings() -> QSettings:
    filename = os.environ.get(MARKFORGE_SETTINGS_FILE_ENV)
    if filename:
        return QSettings(filename, QSettings.IniFormat)
    return QSettings(MARKFORGE_NAME, MARKFORGE_NAME)


def migrate_from_markforge(source: QSettings | None = None,
                           target: QSettings | None = None) -> list:
    """Copy MarkForge's settings into CalcForge's, once, on first start.

    Only what the person set up is taken: shortcuts, tool sets and My Tools,
    toolbar and panel layout, dark mode and markup defaults. Anything CalcForge
    already has is kept, and it happens once — after that the two programs'
    settings go their own ways. Returns the keys copied.
    """
    target = target if target is not None else app_settings()
    if str(target.value(MIGRATED_KEY, "")) == "done":
        return []
    source = source if source is not None else markforge_settings()
    wanted = [key for key in source.allKeys()
              if key in MIGRATED_KEYS or key.split("/", 1)[0] in MIGRATED_GROUPS]
    copied = []
    for key in wanted:
        if target.contains(key):
            continue
        target.setValue(key, source.value(key))
        copied.append(key)
    target.setValue(MIGRATED_KEY, "done")
    target.sync()
    return sorted(copied)
