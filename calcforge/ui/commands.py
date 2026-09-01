"""Undo/redo commands built on whole-page snapshots.

Snapshots keep the implementation honest: any edit, however deep inside an
item, is captured by serialising the page before and after the gesture.
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtGui import QUndoCommand


class PageEditCommand(QUndoCommand):
    """Restore a page's markup list to its state before or after an edit."""

    def __init__(self, scene, before: list[dict], after: list[dict], text: str,
                 on_apply: Optional[Callable] = None):
        super().__init__(text)
        self.scene = scene
        self.before = before
        self.after = after
        self.on_apply = on_apply
        self._skip_first_redo = True

    def _apply(self, data: list[dict]) -> None:
        selected = {item.uid for item in self.scene.selectedItems()
                    if hasattr(item, "uid")}
        self.scene.load_items(data)
        for item in self.scene.markups():
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
        self.before = self.view.scene().serialize_items()
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is not None:
            return False
        after = self.view.scene().serialize_items()
        if after != self.before:
            self.view.push_command(PageEditCommand(
                self.view.scene(), self.before, after, self.text,
                on_apply=self.view.after_undo))
        return False
