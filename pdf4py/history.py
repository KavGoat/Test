"""Undo and redo.

Every edit is recorded as the pair of things that puts it back and puts it
there again, rather than as a copy of the document: a two hundred megabyte
drawing set cannot be snapshotted for each nudge of a markup. What a step
carries is only what it changed — an annotation's own keys, or one page held
aside in a scratch document.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

DEPTH = 200


@dataclass(frozen=True)
class Step:
    """One thing that was done, and how to take it back."""

    label: str
    undo: Callable[[], None]
    redo: Callable[[], None]


class History:
    def __init__(self, depth: int = DEPTH):
        self._depth = depth
        self._done: list[Step] = []
        self._undone: list[Step] = []

    def clear(self) -> None:
        self._done.clear()
        self._undone.clear()

    def record(self, step: Step) -> None:
        """Remember something that has already happened."""
        self._done.append(step)
        del self._done[:-self._depth]
        self._undone.clear()

    @property
    def can_undo(self) -> bool:
        return bool(self._done)

    @property
    def can_redo(self) -> bool:
        return bool(self._undone)

    @property
    def undo_label(self) -> str:
        return self._done[-1].label if self._done else ""

    @property
    def redo_label(self) -> str:
        return self._undone[-1].label if self._undone else ""

    def undo(self) -> Optional[str]:
        if not self._done:
            return None
        step = self._done.pop()
        step.undo()
        self._undone.append(step)
        return step.label

    def redo(self) -> Optional[str]:
        if not self._undone:
            return None
        step = self._undone.pop()
        step.redo()
        self._done.append(step)
        return step.label
