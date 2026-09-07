"""Undo/redo commands built on whole-page snapshots.

Snapshots keep the implementation honest: any edit, however deep inside an
item, is captured by serialising the page before and after the gesture.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from PySide6.QtGui import QUndoCommand

# A command id of -1 tells Qt never to merge. Anything else lets two commands
# of the same id be offered to one another.
NO_MERGE = -1
RUN_OF_EDITS = 0x9E51

# How long a pause ends a run of small edits. Dragging a slider from 100 to 50
# is one change of mind and should be one undo; coming back to it a moment
# later is another.
MERGE_PAUSE = 0.9


class PageEditCommand(QUndoCommand):
    """Restore one page's markup list to its state before or after an edit."""

    def __init__(self, frame, before: list[dict], after: list[dict], text: str,
                 on_apply: Optional[Callable] = None, coalesce: bool = False):
        super().__init__(text)
        self.frame = frame
        self.before = before
        self.after = after
        self.on_apply = on_apply
        self.coalesce = coalesce
        self.stamp = time.monotonic()
        self._skip_first_redo = True

    def id(self) -> int:
        """Only edits that asked to be run together are offered the chance."""
        return RUN_OF_EDITS if self.coalesce else NO_MERGE

    def mergeWith(self, other) -> bool:
        """Swallow the next step of the same drag, keeping where it started.

        A slider sends a value for every pixel it passes. Recording each one
        turns a single drag into fifty undo steps, and getting back to where
        you were means pressing Ctrl+Z until your finger aches. So a run of
        the same kind of edit, on the same page, with no real pause in it,
        becomes one step: the state before the drag, and the state after it.
        """
        if not isinstance(other, PageEditCommand) or not other.coalesce:
            return False
        if other.frame is not self.frame or other.text() != self.text():
            return False
        if other.stamp - self.stamp > MERGE_PAUSE:
            return False
        self.after = other.after
        self.stamp = other.stamp
        return True

    def _apply(self, data: list[dict]) -> None:
        selected = {item.uid for item in self.frame.markups() if item.isSelected()}
        self.frame.load_items(data)
        for item in self.frame.markups():
            if item.uid in selected:
                item.setSelected(True)
        if self.on_apply is not None:
            self.on_apply()

    def redo(self) -> None:
        # The first redo happens as the command is pushed, when the edit has
        # already been applied by whoever made it — nothing to re-apply.
        if self._skip_first_redo:
            self._skip_first_redo = False
            return
        self._apply(self.after)

    def undo(self) -> None:
        self._apply(self.before)


class DocumentStructureCommand(QUndoCommand):
    """Page insertions, deletions and reordering."""

    def __init__(self, before: dict, after: dict, text: str, restore: Callable[[dict], None]):
        super().__init__(text)
        self.before = before
        self.after = after
        self.restore = restore
        self._skip_first_redo = True

    def redo(self) -> None:
        if self._skip_first_redo:
            self._skip_first_redo = False
            return
        self.restore(self.after)

    def undo(self) -> None:
        self.restore(self.before)


class SnapshotGuard:
    """Context manager that pushes a :class:`PageEditCommand` when work changes.

    ``with SnapshotGuard(view, "Move markup"): ...`` — the snapshot before the
    block is compared with the one after, and nothing is pushed when they match.
    """

    def __init__(self, view, text: str):
        self.view = view
        self.text = text
        self.before: list[dict] = []

    def __enter__(self) -> "SnapshotGuard":
        self.before = self.view.frame().serialize_items()
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is not None:
            return False
        frame = self.view.frame()
        after = frame.serialize_items()
        if after != self.before:
            self.view.push_command(PageEditCommand(
                frame, self.before, after, self.text,
                on_apply=self.view.after_undo))
        return False
