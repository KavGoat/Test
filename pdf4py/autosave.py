"""Autosave: periodic backup of the working document."""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QTimer

AUTOSAVE_INTERVAL_MS = 120_000  # 2 minutes


class Autosave:

    def __init__(self, save_callback: Callable[[], None]) -> None:
        self._save = save_callback
        self._timer = QTimer()
        self._timer.setInterval(AUTOSAVE_INTERVAL_MS)
        self._timer.timeout.connect(self._on_tick)
        self._enabled = False
        self._has_path = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, on: bool) -> None:
        self._enabled = on
        if on and self._has_path:
            self._timer.start()
        else:
            self._timer.stop()

    def set_has_path(self, has_path: bool) -> None:
        self._has_path = has_path
        if self._enabled and has_path:
            self._timer.start()
        elif not has_path:
            self._timer.stop()

    def _on_tick(self) -> None:
        if self._enabled and self._has_path:
            self._save()

    def stop(self) -> None:
        self._timer.stop()
