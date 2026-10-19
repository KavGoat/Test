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
                 on_apply: Optional[Callable] = None, coalesce: bool = False,
                 find_frame: Optional[Callable] = None,
                 selected_before: Optional[set] = None,
                 selected_after: Optional[set] = None):
        super().__init__(text)
        self.frame = frame
        # What was picked before the edit and after it, by markup id. An
        # undo picks again what was picked before (Revu: the markup a Delete,
        # Cut or Hide took away comes back selected), a redo what was picked
        # after (QA F-34). None: the edit did not say, and the selection in
        # hand is kept.
        self.selected_before = selected_before
        self.selected_after = selected_after
        # Undoing a page added or moved rebuilds every page's frame: the page
        # is found again by its id when the step is applied, or a redo after
        # it wrote into a frame no longer on the canvas (2026-10-10).
        self.page_uid = getattr(getattr(frame, "page", None), "uid", None)
        self.find_frame = find_frame
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
        # A field being typed into names its run (an object of its own, as
        # *coalesce*): every keystroke of it is the one edit, however slowly
        # it is typed (exercise round 1, F-06).
        if other.coalesce is not True or self.coalesce is not True:
            if other.coalesce is not self.coalesce:
                return False
        elif other.stamp - self.stamp > MERGE_PAUSE:
            return False
        self.after = other.after
        self.stamp = other.stamp
        self.selected_after = other.selected_after
        return True

    def _live_frame(self):
        if self.find_frame is not None and self.page_uid is not None:
            found = self.find_frame(self.page_uid)
            if found is not None:
                self.frame = found
        return self.frame

    def _apply(self, data: list[dict], wanted: Optional[set] = None) -> None:
        self._live_frame()
        selected = {item.uid for item in self.frame.markups() if item.isSelected()}
        if wanted is not None:
            # the whole canvas's selection: a step that changed two pages is
            # two of these, and each of them picks the same
            scene = self.frame.scene()
            if scene is not None:
                for item in scene.selectedItems():
                    if getattr(item, "uid", None) not in wanted:
                        item.setSelected(False)
            selected = wanted
        self.frame.load_items(data)
        for item in self.frame.markups():
            if item.uid in selected and item.isVisible():
                item.setSelected(True)
        if self.on_apply is not None:
            self.on_apply()

    def redo(self) -> None:
        # The first redo happens as the command is pushed, when the edit has
        # already been applied by whoever made it — nothing to re-apply.
        if self._skip_first_redo:
            self._skip_first_redo = False
            return
        self._apply(self.after, self.selected_after)

    def undo(self) -> None:
        self._apply(self.before, self.selected_before)


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


class ViewportsCommand(QUndoCommand):
    """A page's viewports added, changed or removed."""

    def __init__(self, page, before: list[dict], after: list[dict], text: str,
                 changed: Callable[[object], None], find_page: Optional[Callable] = None):
        super().__init__(text)
        self.page = page
        self.page_uid = getattr(page, "uid", None)
        self.find_page = find_page
        self.before = before
        self.after = after
        self.changed = changed

    def _apply(self, state: list[dict]) -> None:
        from ..core.document import Viewport
        if self.find_page is not None:
            # the page as it is now (undoing a page change makes new ones)
            self.page = self.find_page(self.page_uid) or self.page
        self.page.viewports = [Viewport.from_dict(v) for v in state]
        self.changed(self.page)

    def redo(self) -> None:
        self._apply(self.after)

    def undo(self) -> None:
        self._apply(self.before)


def on_the_canvas(scene):
    """(on_apply, find_frame) for a step on the pages of *scene*.

    They reach the pages through the canvas when the step is undone or
    redone, not through the view that recorded it: the document goes to
    another window with its canvas and history when its tab is dragged
    there, and the window it came from may have closed since (the user,
    2026-10-19). Every view showing the canvas is told (a document shown
    in two windows by File ▸ New Window)."""
    def after_undo():
        for view in list(scene.views()):
            if getattr(getattr(view, "window", None), "_closed_for_good", False):
                continue
            settle = getattr(view, "after_undo", None)
            if settle is not None:
                settle()

    def find_frame(page_uid):
        for frame in getattr(scene, "frames", ()) or ():
            if getattr(frame.page, "uid", None) == page_uid:
                return frame
        return None
    return after_undo, find_frame


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
            on_apply, find_frame = on_the_canvas(frame.scene())
            self.view.push_command(PageEditCommand(
                frame, self.before, after, self.text,
                on_apply=on_apply, find_frame=find_frame))
        return False
