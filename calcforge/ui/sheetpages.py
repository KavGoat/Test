"""Spreadsheet pages in the window: making them, growing them, and keeping
each run of them one sheet (items/sheetpage.py, docs/SPREADSHEET_DESIGN.md).

* A run of consecutive spreadsheet pages is one sheet; typing past its last
  page adds one (in the same undo step as the typing), and pages left empty
  at its end are kept (the user's choice).
* No ordinary page goes into the middle of a run, and a reorder may not
  split one: a run moves as a whole.
* Paper and orientation are the run's, not a page's: turning one page turns
  them all, and the page breaks flow again.
* Deleting a page of a run takes its rows with it.
* Only markups go on a spreadsheet page: no equations, no tables.
"""
from __future__ import annotations

from typing import Optional

from ..core.document import LANDSCAPE, PORTRAIT, PageSetup


# -- finding runs -----------------------------------------------------------------------------
def runs(document) -> list:
    """Each run: (run id, [page indexes]), consecutive pages only."""
    out = []
    for index, page in enumerate(document.pages):
        run = getattr(page, "sheet", None)
        if run is None:
            continue
        if out and out[-1][0] == run and out[-1][1][-1] == index - 1:
            out[-1][1].append(index)
        else:
            out.append((run, [index]))
    return out


def run_of(document, index: int) -> list:
    """The page indexes of the run page *index* is in ([] for an ordinary page)."""
    for _run, pages in runs(document):
        if index in pages:
            return pages
    return []


def run_items(scene) -> list:
    from ..items.sheetpage import SheetRunItem
    out = []
    for frame in getattr(scene, "frames", []) or []:
        for item in frame.markups():
            if isinstance(item, SheetRunItem):
                out.append(item)
    return out


def is_sheet_frame(frame) -> bool:
    return getattr(getattr(frame, "page", None), "sheet", None) is not None


# -- keeping them in shape ---------------------------------------------------------------------
def settle(window) -> None:
    """After the pages were rebuilt: each run's cells on its first page, each
    page its slice of the grid, the canvas laid out again."""
    scene = window.scene
    if scene is None:
        return
    from ..items.sheetpage import SheetRunItem

    document = window.document
    found = {}
    for item in run_items(scene):
        found.setdefault(item.uid, item)
    claimed = set()
    for run, indexes in runs(document):
        frames = [document.pages[i].frame for i in indexes]
        item = found.get(run)
        if item is None or run in claimed or None in frames:
            # a copy of a sheet page, or its sheet gone: an ordinary page now
            for i in indexes:
                document.pages[i].sheet = None
                if document.pages[i].frame is not None:
                    document.pages[i].frame.set_sheet_rect(None)
            continue
        claimed.add(run)
        if item.parentItem() is not frames[0]:
            item.setParentItem(frames[0])
            item.setPos(0, 0)
        item._hold = False
    for item in run_items(scene):
        if item.uid not in claimed or item is not found.get(item.uid):
            # its pages were made ordinary (or it is a copy): nothing of a
            # sheet stays behind on an ordinary page
            item.setParentItem(None)
            if item.scene() is not None:
                item.scene().removeItem(item)
    for frame in scene.frames:
        if not is_sheet_frame(frame) and frame.sheet_rect is not None:
            frame.set_sheet_rect(None)
    for item in run_items(scene):
        if isinstance(item, SheetRunItem) and item.sheet is not None:
            item.relayout()
    scene.layout_pages()


def short_runs(window) -> list:
    """Runs whose cells need more pages than they have: [(item, extra)]."""
    out = []
    for item in run_items(window.scene):
        if item.sheet is None:
            continue
        if item.relayout():
            out.append((item, item.paging.pages - len(item.run_frames())))
    return out


def add_run_pages(window, short: list) -> None:
    """Give each run the pages its cells need (after its last page)."""
    document = window.document
    for item, extra in short:
        frames = item.run_frames()
        if not frames or extra <= 0:
            continue
        last = document.index_of(frames[-1].page)
        for k in range(extra):
            page = document.add_page(last + 1 + k)
            page.setup = PageSetup.from_dict(frames[0].page.setup.to_dict())
            page.sheet = item.uid
    window.rebuild_scenes()


# -- making them --------------------------------------------------------------------------------
def insert_sheet_page(window, index: Optional[int] = None, before: bool = False) -> None:
    """A spreadsheet page beside page *index*: part of the run it touches,
    or a new sheet of its own."""
    from ..items.sheetpage import SheetRunItem

    document = window.document
    which = window.page_index(index)
    here = document.pages[which]
    if here.sheet is not None:
        # on a run, it is one more page of it, at its end (the sheet grows
        # downwards; a page never goes in ahead of its first)
        run = here.sheet
        pages = run_of(document, which)
        target = pages[-1] + 1
        setup = PageSetup.from_dict(document.pages[pages[0]].setup.to_dict())
    else:
        run = None
        target = safe_target(document, which if before else which + 1)
        setup = PageSetup.from_dict(here.setup.to_dict())

    def mutate():
        page = document.add_page(target)
        page.setup = setup
        if run is not None:
            page.sheet = run
        else:
            item = SheetRunItem()
            page.sheet = item.uid
            page._pending_items = [item.serialize()]
        window.current_index = target
    window._structural_change("Insert spreadsheet page", mutate)


def safe_target(document, target: int) -> int:
    """Where a page can go in: never between two pages of one run (after
    the run instead)."""
    pages = document.pages
    while 0 < target < len(pages) and pages[target - 1].sheet is not None \
            and pages[target - 1].sheet == pages[target].sheet:
        target += 1
    return target


def fresh_item_ids(entries: list) -> list:
    """Copies of pages: every markup on them a new one, with its own uid (a
    table, an equation or a block is known by its uid, so a copy sharing it
    was the same table on two pages). A run of spreadsheet pages copied
    whole follows its cells' new uid."""
    import copy as _copy
    import uuid

    out = [_copy.deepcopy(entry) for entry in entries]
    renamed = {}
    for entry in out:
        for item in entry.get("items", []) or []:
            if isinstance(item, dict) and item.get("uid"):
                new = uuid.uuid4().hex
                renamed[item["uid"]] = new
                item["uid"] = new
    for entry in out:
        if entry.get("sheet") in renamed:
            entry["sheet"] = renamed[entry["sheet"]]
    return out


def plain_copy(entry: dict) -> dict:
    """A page copied or duplicated off a run is an ordinary page with the
    markups that were on it (one sheet is one run)."""
    entry = dict(entry)
    entry["sheet"] = None
    entry["items"] = [it for it in entry.get("items", []) if it.get("type") != "sheet_run"]
    return entry


# -- changing them ------------------------------------------------------------------------------
def before_delete(window, going: list) -> None:
    """Pages of runs about to go: their rows go with them, and a run whose
    first page goes keeps its cells on the page that is first now."""
    document = window.document
    going_set = set(going)
    for item in run_items(window.scene):
        frames = item.run_frames()
        indexes = [document.index_of(f.page) for f in frames]
        gone = [k for k, i in enumerate(indexes) if i in going_set]
        if not gone or len(gone) == len(frames):
            continue
        going_frames = {frames[k] for k in gone}
        anchors = {m: a for m, a in item.capture_anchors().items()
                   if m.parentItem() not in going_frames}
        item._anchors = anchors
        item._hold = True
        paging = item.paging
        sheet = item.sheet
        if paging is not None and sheet is not None:
            for k in sorted(gone, reverse=True):
                if k < len(paging.slices):
                    a, b = paging.slices[k]
                    sheet.workbook.delete_rows(sheet, a, b - a + 1)
            # the breaks the user put there go with the rows (shifted by the
            # workbook); the first page left starts at row 1 again
        keep = next(f for k, f in enumerate(frames) if k not in gone)
        if item.parentItem() is not keep:
            item.setParentItem(keep)
            item.setPos(0, 0)


def move_allowed(document, source: int, count: int, target: int) -> bool:
    """Whether a reorder leaves every run whole and nothing inside one."""
    pages = list(document.pages)
    moving = pages[source:source + count]
    for page in moving:
        pages.remove(page)
    landing = max(0, min(int(target), len(pages)))
    pages[landing:landing] = moving
    seen = {}
    for i, page in enumerate(pages):
        run = page.sheet
        if run is None:
            continue
        if run in seen and seen[run] != i - 1:
            return False
        seen[run] = i
    # and each run still has all its pages, in order
    before = [p for p in document.pages if p.sheet is not None]
    after = [p for p in pages if p.sheet is not None]
    for run in {p.sheet for p in before}:
        if [p for p in before if p.sheet == run] != [p for p in after if p.sheet == run]:
            return False
    return True


def turn_run(window, index: int) -> None:
    """Portrait ⇄ landscape for a whole run; the page breaks flow again."""
    document = window.document
    indexes = run_of(document, index)
    pages = [document.pages[i] for i in indexes]

    def mutate():
        for page in pages:
            setup = page.setup
            setup.orientation = PORTRAIT if setup.orientation == LANDSCAPE else LANDSCAPE
            (setup.margin_left, setup.margin_top, setup.margin_right, setup.margin_bottom) = (
                setup.margin_bottom, setup.margin_left, setup.margin_top, setup.margin_right)
        window.current_index = index
    window._structural_change("Rotate spreadsheet pages", mutate, preserve_view=True)


def with_runs(document, pages: list) -> list:
    """Pages, and every page of any run among them (paper is the run's)."""
    out = []
    for page in pages:
        idx = document.index_of(page)
        extra = [document.pages[i] for i in run_of(document, idx)] if page.sheet else [page]
        for p in extra:
            if p not in out:
                out.append(p)
    return out


def blocks_calc(frame) -> bool:
    """Equations and tables do not go on spreadsheet pages."""
    return is_sheet_frame(frame)
