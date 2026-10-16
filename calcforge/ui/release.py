"""Letting go of a document nobody is looking at any more.

A document closed in its tab, replaced by File ▸ New or Open, or left behind
when a split is turned off kept everything it had: its canvas (the scene, its
pages and every markup, table and equation on them), its undo history, the
squares its markups were drawn into, the tiles of its PDF, and the
calculation hooks it had last set. They were never shown again but kept being
worked on — a table on a closed page was still being drawn into its squares
— and a long session (or the test suite, at 2.4 GB a worker) ran out of
memory.

The windows know what they still show. Whatever they made that none of them
shows any more is let go of here: its timers stopped, its signals cut, its
items deleted with its scene, its history cleared, and the caches keyed by it
emptied — nothing a document still open needs.
"""
from __future__ import annotations

import warnings
import weakref
from contextlib import contextmanager

import shiboken6


#: What the windows made, weakly: a scene, an undo stack, a document. Only
#: these are ever let go of, so a scene somebody else built is left alone.
SCENES: "weakref.WeakSet" = weakref.WeakSet()
STACKS: "weakref.WeakSet" = weakref.WeakSet()
DOCUMENTS: "weakref.WeakSet" = weakref.WeakSet()


#: While a document is on its way from one window or pane to another it is
#: shown by neither: nothing is let go of until it has arrived.
_holding = [0]


@contextmanager
def holding():
    _holding[0] += 1
    try:
        yield
    finally:
        _holding[0] -= 1


def _valid(thing) -> bool:
    try:
        return thing is not None and shiboken6.isValid(thing)
    except Exception:                                   # noqa: BLE001
        return False


def release_scene(scene) -> None:
    """Take a canvas apart: nothing on it is drawn, timed or told again."""
    if not _valid(scene):
        return
    from ..io import pdftiles
    for signal, slot in ((pdftiles.TILES.tileReady, scene._part_of_a_page_arrived),
                         (pdftiles.TILES.sheetReady, scene._a_page_arrived)):
        try:
            signal.disconnect(slot)
        except (RuntimeError, TypeError):
            pass
    timer = getattr(scene, "_settling", None)
    if _valid(timer):
        timer.stop()
    scene._arrived = []
    for frame in list(getattr(scene, "frames", ())):
        if not _valid(frame):
            continue
        layer = getattr(frame, "layer", None)
        if layer is not None:
            for name in ("_settle", "_idle", "_mend"):
                timer = getattr(layer, name, None)
                if _valid(timer):
                    timer.stop()
            try:
                layer.release_all()
            except RuntimeError:
                pass
            layer.enabled = False
            layer.hot.clear()
        page = getattr(frame, "page", None)
        if page is not None and getattr(page, "frame", None) is frame:
            page.frame = None
    scene.frames = []
    try:
        scene.blockSignals(True)
        scene.clear()
    except RuntimeError:
        pass
    scene.deleteLater()


def release_stack(stack, windows=()) -> None:
    """An undo history nobody can reach: its commands (and the items they
    hold) go with it."""
    if not _valid(stack):
        return
    for window in windows:
        held = getattr(window, "_connected_undo_stacks", None)
        if held is None:
            continue
        if any(stack is seen for seen in held):
            with warnings.catch_warnings():
                # (a closing window has disconnected it already)
                warnings.simplefilter("ignore", RuntimeWarning)
                try:
                    stack.cleanChanged.disconnect(window._undo_clean_slot)
                except (RuntimeError, TypeError):
                    pass
            held[:] = [seen for seen in held if seen is not stack]
    stack.clear()
    stack.deleteLater()


def release_document(document, sources_in_use: set) -> None:
    """A document's calculation hooks and cached drawing, where they are
    only its own."""
    from ..calc.engine import evaluator, sym
    book = getattr(document, "_sheet_book", None)
    sheet = getattr(document, "_calc_sheet", None)
    worksheet = getattr(sheet, "worksheet", None)
    external = getattr(worksheet, "external", None)
    hooked = evaluator.EXTERNAL
    if hooked is not None and (hooked is book or hooked is external
                               or getattr(hooked, "document", None) is document):
        evaluator.EXTERNAL = None
    # the symbolic engine's "defined above" points at the worksheet that
    # evaluated last (calc/worksheet.py)
    cells = getattr(sym.defined_above, "__closure__", None) or ()
    mine = [held for held in (worksheet, sheet) if held is not None]
    if any(cell.cell_contents is held for cell in cells if _filled(cell)
           for held in mine):
        sym.defined_above = lambda: set()
    if book is not None:
        book.listeners.clear()
    if sheet is not None:
        sheet.listeners.clear()
    from ..io import pdftiles
    for source in {getattr(page, "pdf_key", None) for page in document.pages}:
        if source and source not in sources_in_use:
            pdftiles.TILES.forget(source)


def _filled(cell) -> bool:
    try:
        cell.cell_contents
    except ValueError:
        return False
    return True


def let_go(showing, every_window) -> None:
    """Release whatever the windows made that none of the *showing* windows
    shows now (*every_window* is told its undo stacks have gone)."""
    if _holding[0]:
        return
    documents, scenes, stacks = set(), set(), set()
    in_use_documents = []
    for window in showing:
        for document, scene, stack in window.shown_states():
            if document is not None and id(document) not in documents:
                documents.add(id(document))
                in_use_documents.append(document)
            if scene is not None:
                scenes.add(id(scene))
            if stack is not None:
                stacks.add(id(stack))
    sources = {getattr(page, "pdf_key", None)
               for document in in_use_documents for page in document.pages}
    for scene in list(SCENES):
        if id(scene) not in scenes:
            SCENES.discard(scene)
            release_scene(scene)
    for stack in list(STACKS):
        if id(stack) not in stacks:
            STACKS.discard(stack)
            release_stack(stack, every_window)
    for document in list(DOCUMENTS):
        if id(document) not in documents:
            DOCUMENTS.discard(document)
            release_document(document, sources)
