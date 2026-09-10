"""Application settings with an explicit test/development override."""
from __future__ import annotations

import os

from PySide6.QtCore import QSettings

APP_NAME = "MarkForge"
ORGANISATION = "MarkForge"
SETTINGS_FILE_ENV = "MARKFORGE_SETTINGS_FILE"


def app_settings() -> QSettings:
    """Return MarkForge's persistent settings store.

    Qt's two-string QSettings constructor always selects the native plist on
    macOS, even after ``setDefaultFormat``.  The explicit file override keeps
    automated runs out of a person's real preferences on every platform.
    """
    filename = os.environ.get(SETTINGS_FILE_ENV)
    if filename:
        return QSettings(filename, QSettings.IniFormat)
    return QSettings(ORGANISATION, APP_NAME)
