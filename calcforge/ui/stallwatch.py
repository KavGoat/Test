"""Help ▸ Record slow-downs: what the window was doing whenever it stopped
answering for a moment, written to a file that can be sent back.

A slow scroll on somebody else's computer can't be measured from here: their
graphics card, their screen's scaling and their drawings all differ. So the
window keeps a heartbeat while this is on, and a watcher thread notes the
main thread's Python stack whenever the heartbeat is late by more than a
frame or so. A stall with no CalcForge code on the stack was Qt drawing.
"""
from __future__ import annotations

import collections
import datetime
import os
import sys
import threading
import time
import traceback
from typing import Optional

from PySide6.QtCore import QTimer

LATE = 0.06          # seconds without a heartbeat that count as a stall


class StallWatch:
    def __init__(self, path: str):
        self.path = path
        self.stalls: collections.Counter = collections.Counter()
        self.worst: dict = {}
        self.count = 0
        self.started = time.perf_counter()
        self._last = time.perf_counter()
        self._stop = threading.Event()
        self._main = threading.get_ident()
        self._beat = QTimer()
        self._beat.setInterval(5)
        self._beat.timeout.connect(self._tick)
        self._beat.start()
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()

    def _tick(self) -> None:
        self._last = time.perf_counter()

    def _watch(self) -> None:
        noted = None
        while not self._stop.wait(0.01):
            late = time.perf_counter() - self._last
            if late <= LATE or noted == self._last:
                continue
            noted = self._last
            frame = sys._current_frames().get(self._main)
            stack = traceback.extract_stack(frame) if frame is not None else []
            # the event loop's own frame (app.main) is always there: below it
            # is what was actually running; nothing below it was Qt's own work
            frames = [f for f in stack if not (f.name == "main" and
                                               f.filename.replace("\\", "/").endswith("calcforge/app.py"))]
            mine = [f for f in frames if "calcforge" in f.filename.replace("\\", "/")] or frames[-3:]
            where = " < ".join(f"{os.path.basename(f.filename)}:{f.name}:{f.lineno}"
                               for f in reversed(mine[-8:])) or "Qt drawing (no CalcForge code running)"
            self.stalls[where] += 1
            self.count += 1
            # how long it went on for, once it is over
            while not self._stop.is_set() and self._last == noted:
                time.sleep(0.005)
            self.worst[where] = max(self.worst.get(where, 0.0), time.perf_counter() - noted)

    def stop(self) -> str:
        self._stop.set()
        self._beat.stop()
        self._thread.join(timeout=1)
        seconds = time.perf_counter() - self.started
        lines = [f"CalcForge slow-downs, {datetime.datetime.now():%Y-%m-%d %H:%M}, "
                 f"{seconds:.0f} s recorded, {self.count} stalls over {LATE * 1000:.0f} ms", ""]
        for where, n in self.stalls.most_common():
            lines.append(f"{n:4d} x  up to {self.worst.get(where, 0) * 1000:6.0f} ms  {where}")
        text = "\n".join(lines) + "\n"
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as out:
                out.write(text + "\n")
        except OSError:
            pass
        return text


_running: Optional[StallWatch] = None


def toggle(window, on: bool) -> None:
    """Start recording, or stop and say where the record went."""
    global _running
    from ..app import crash_log_path
    path = os.path.join(os.path.dirname(crash_log_path()), "slowdowns.log")
    if on and _running is None:
        _running = StallWatch(path)
        window.status_hint.setText("Recording slow-downs: do what was slow, then stop it in Help")
    elif not on and _running is not None:
        text, _running = _running.stop(), None
        window.status_hint.setText(f"Slow-downs written to {path}")
        if getattr(window, "interactive_prompts", True):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(window, "Slow-downs", f"Written to\n{path}\n\n{text[:1500]}")
