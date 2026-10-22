"""Spreadsheet pages in the window: making them, growing them, and keeping
each run of them one sheet (items/sheetpage.py, docs/SPREADSHEET_DESIGN.md).

* A run of consecutive spreadsheet pages is one sheet with as many rows as
  it has (the user, 2026-10-17, replacing "pages left empty at its end are
  kept"): its pages follow its rows, its print area and its breaks, as
  Excel's page count does. A row added past the last page adds a page; a
  page left with no rows (and nothing drawn on it) goes, in the same undo
  step as the change.
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


# -- workbooks: sections of the document ----------------------------------------------------------
class Section:
    """A workbook laid out in the document: consecutive spreadsheet pages
    whose sheets are one Excel workbook brought in, or sheets made here next
    to each other (the user, 2026-10-21: "treat spreadsheet workbooks as a
    section"). Thumbnails shows it as one entry, and its sheets are the tabs
    under the canvas while it is in view."""

    def __init__(self, key: str, book: Optional[str]):
        self.key = key                    # its first sheet's run id
        self.book = book                  # the imported workbook (Book.id), or None
        self.name = "Workbook"
        self.runs: list = []              # run ids, in order
        self.pages: list = []             # page indexes, in order

    @property
    def first(self) -> int:
        return self.pages[0]

    @property
    def last(self) -> int:
        return self.pages[-1]

    #: its pages' numbers as printed (Document.printed_numbers), those that print
    printed: list = []

    def page_range(self) -> str:
        """"pages 2–10", or "page 3", numbered as printed; "doesn't print"."""
        if not self.printed:
            return "doesn't print"
        a, b = self.printed[0], self.printed[-1]
        return f"page {a}" if a == b else f"pages {a}–{b}"

    def label(self) -> str:
        """"Loads — pages 2–10"."""
        return f"{self.name} — {self.page_range()}"


def _run_record(document, uid: str):
    """(its sheet if on the canvas, else None; its record if still waiting
    to be, else None) for run *uid*."""
    from shiboken6 import isValid

    from ..items.sheetpage import SheetRunItem
    for page in document.pages:
        if page.sheet != uid:
            continue
        frame = page.frame
        if frame is not None and isValid(frame):
            for item in frame.markups():
                if isinstance(item, SheetRunItem) and item.uid == uid:
                    return item.sheet, (item._data if item.sheet is None else None)
        for record in getattr(page, "_pending_items", None) or ():
            if isinstance(record, dict) and record.get("type") == "sheet_run" \
                    and record.get("uid") == uid:
                return None, record.get("table") or {}
    return None, None


def run_book(document, uid: str) -> tuple:
    """(Book.id or None, the workbook's name as shown, the sheet's name) of
    run *uid*."""
    sheet, record = _run_record(document, uid)
    if sheet is not None:
        book_id = getattr(sheet, "book", None)
        found = sheet.workbook.books.get(book_id) if book_id else None
        shown = _book_shown(found.file, found.name) if found is not None else None
        return book_id, shown, sheet.name
    record = record or {}
    book = record.get("book") or {}
    shown = _book_shown(book.get("file") or "", book.get("name") or "") if book.get("id") \
        else None
    return book.get("id"), shown, record.get("name") or "Sheet"


def _book_shown(file: str, name: str) -> str:
    """A workbook's name as shown: its file's name (a copy's is "Loads (2)",
    workbook_copy), else its name for the equations."""
    import os
    return os.path.splitext(os.path.basename(file or ""))[0] or name or "Workbook"


def sections(document, fresh: bool = False) -> list:
    """The document's workbooks, in page order (kept until its pages or
    their sheets change; *fresh*: worked out again, a sheet renamed)."""
    pages = document.pages
    key = (tuple((i, id(p), p.sheet, id(p.frame)) for i, p in enumerate(pages)
                 if p.sheet is not None), tuple(p.printable for p in pages))
    cached = getattr(document, "_sections_cache", None)
    if not fresh and cached is not None and cached[0] == key and cached[1] == len(pages):
        return cached[2]
    out: list = []
    for run, indexes in runs(document):
        book, shown, sheet_name = run_book(document, run)
        last = out[-1] if out else None
        if last is not None and last.last == indexes[0] - 1 and last.book == book:
            last.runs.append(run)
            last.pages.extend(indexes)
        else:
            last = Section(run, book)
            last.runs.append(run)
            last.pages.extend(indexes)
            last.name = shown or sheet_name
            last._names = []
            out.append(last)
        last._names.append(sheet_name)
    numbers = document.printed_numbers()
    for section in out:
        if section.book is None and len(section.runs) > 1:
            section.name = "Workbook"      # sheets made here, side by side
        section.printed = [numbers[i] for i in section.pages if numbers[i]]
    document._sections_cache = (key, len(pages), out)
    return out


def section_of(document, index: int) -> Optional[Section]:
    """The workbook page *index* is a page of, or None."""
    for section in sections(document):
        if section.first <= index <= section.last:
            return section
    return None


def run_pages(document, uid: str) -> list:
    return [i for i, page in enumerate(document.pages) if page.sheet == uid]


def sheet_prints(document, uid: str) -> bool:
    """Whether sheet (run) *uid* prints: any of its pages does."""
    return any(document.pages[i].printable for i in run_pages(document, uid))


def set_sheet_printing(window, uid: str, on: bool) -> None:
    """Print / Don't Print for a sheet: all its pages, one undo step (the
    user, 2026-10-21). A sheet that doesn't print stays in the document —
    equations and other sheets still read its cells — but its pages are
    left out of Print, Export and the saved PDF's pages."""
    pages = run_pages(window.document, uid)
    if pages:
        window.set_pages_printable(pages, bool(on))


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
    """Runs whose pages don't match what their rows need: [(item, change)],
    more pages wanted (change > 0), or empty pages at the end to take away
    (change < 0: only pages with nothing drawn on them go)."""
    from ..items.sheetpage import SheetRunItem
    out = []
    for item in run_items(window.scene):
        if item.sheet is None:
            continue
        item.relayout()
        frames = item.run_frames()
        need = max(1, item.paging.pages)
        if need > len(frames):
            out.append((item, need - len(frames)))
            continue
        spare = 0
        for frame in reversed(frames[need:]):
            if any(not isinstance(m, SheetRunItem) for m in frame.markups()):
                break                   # something drawn on it: it stays
            spare += 1
        if spare:
            out.append((item, -spare))
    return out


def add_run_pages(window, short: list) -> None:
    """Give each run the pages its rows need (after its last page), or take
    away the empty ones it no longer needs (a negative count)."""
    document = window.document
    for item, extra in short:
        frames = item.run_frames()
        if not frames or not extra:
            continue
        if extra < 0:
            for frame in frames[extra:]:
                document.remove_page(document.index_of(frame.page))
            continue
        last = document.index_of(frames[-1].page)
        for k in range(extra):
            page = document.add_page(last + 1 + k)
            page.setup = PageSetup.from_dict(frames[0].page.setup.to_dict())
            page.sheet = item.uid
            # a sheet that doesn't print grows pages that don't either
            page.printable = frames[-1].page.printable
    window.rebuild_scenes()


# -- making them --------------------------------------------------------------------------------
# Excel's Normal margins: 0.7" left and right, 0.75" top and bottom
EXCEL_MARGINS_MM = (0.7 * 25.4, 0.75 * 25.4, 0.7 * 25.4, 0.75 * 25.4)


def insert_sheet_page(window, index: Optional[int] = None, before: bool = False,
                      new_sheet: bool = False) -> None:
    """A spreadsheet page beside page *index*: part of the run it touches,
    or a new sheet of its own (always, with *new_sheet*: after the run)."""
    document = window.document
    which = window.page_index(index)
    here = document.pages[which]
    if here.sheet is not None and not new_sheet:
        # on a run, it is one more page of it, at its end (the sheet grows
        # downwards; a page never goes in ahead of its first): a page's
        # worth of rows more, and the page they need
        from ..items.sheetpage import run_item_for
        from ..sheet.pagination import rows_of
        from . import sheetlayout
        item = run_item_for(here.frame) if here.frame is not None else None
        if item is not None and item.sheet is not None:
            frames = item.run_frames()
            rows = rows_of(item.sheet, frames[0].page.setup, len(frames) + 1)
            sheetlayout.change_options(window, item, "Insert spreadsheet page", rows=rows)
            return
        run = here.sheet
        pages = run_of(document, which)
        target = pages[-1] + 1
        setup = PageSetup.from_dict(document.pages[pages[0]].setup.to_dict())
        printable = document.pages[pages[-1]].printable
    else:
        run = None
        printable = True
        target = safe_target(document, which if before else which + 1)
        setup = PageSetup.from_dict(here.setup.to_dict())
        # a new sheet starts with Excel's Normal margins, so it falls onto
        # its pages as the same sheet would in Excel (its paper and turn are
        # the page's beside it)
        (setup.margin_left, setup.margin_top, setup.margin_right,
         setup.margin_bottom) = EXCEL_MARGINS_MM

    def mutate():
        page = document.add_page(target)
        page.setup = setup
        if run is not None:
            page.sheet = run
            page.printable = printable
        else:
            page.sheet, record = new_sheet_record(setup)
            page._pending_items = [record]
        window.current_index = target
    window._structural_change("Insert spreadsheet page", mutate)


def one_page_area(setup) -> list:
    """The cells that fit on one page at *setup*, from A1 — a new sheet's
    print area (the user, 2026-10-22: "default to a one-page-size print
    area on new sheet insert"), as [top, left, bottom, right]."""
    from ..sheet.pagination import paginate
    from .xlsximport import _Layout
    paging = paginate(_Layout({"cells": [], "page": {}}), setup)
    (a, b), (c0, c1) = paging.slices[0], paging.groups[0]
    return [0, 0, max(b, 0), max(c1, 0)]


def new_sheet_record(setup, book: Optional[dict] = None) -> tuple:
    """(run id, record) of a new, empty sheet: its print area one page of
    cells from A1 (Page Layout ▸ Print Area ▸ Clear Print Area takes it
    off), part of the imported workbook *book* when given."""
    from ..items.sheetpage import SheetRunItem
    item = SheetRunItem()
    record = item.serialize()
    area = one_page_area(setup)
    table = {"name": None, "cells": [], "styles": [{}],
             "page": {"print_area": area} if area else {}}
    if book is not None:
        table["book"] = dict(book)
    record["table"] = table
    return item.uid, record


def new_sheet_in(window, section: Section) -> None:
    """The sheet tabs' +: a new sheet at the end of the workbook in view —
    one of the Excel workbook's sheets when it is one (sharing its names),
    its paper the last sheet's, with Excel's Normal margins."""
    document = window.document
    target = section.last + 1
    setup = PageSetup.from_dict(document.pages[section.last].setup.to_dict())
    (setup.margin_left, setup.margin_top, setup.margin_right,
     setup.margin_bottom) = EXCEL_MARGINS_MM
    book = None
    if section.book is not None:
        from ..sheet.docbook import book_for
        found = book_for(document).workbook.books.get(section.book)
        book = found.to_dict() if found is not None else None

    def mutate():
        page = document.add_page(target)
        page.setup = setup
        page.sheet, record = new_sheet_record(setup, book)
        page._pending_items = [record]
        window.current_index = target
    window._structural_change("Insert spreadsheet page", mutate)


def why_not_moved(document, source: int, count: int, target: int) -> str:
    """What to say when a reorder is refused (move_allowed False)."""
    pages = list(document.pages)
    moving = pages[source:source + count]
    for page in moving:
        pages.remove(page)
    landing = max(0, min(int(target), len(pages)))
    pages[landing:landing] = moving
    if not book_kept_whole(document, pages):
        return ("An Excel workbook's sheets stay together: move the whole workbook "
                "(its entry in Thumbnails), and nothing goes between its sheets")
    return "A spreadsheet's pages move together, and nothing goes between them"


def safe_target(document, target: int) -> int:
    """Where a page can go in: never between two pages of one run (after
    the run instead)."""
    pages = document.pages
    while 0 < target < len(pages) and pages[target - 1].sheet is not None \
            and pages[target - 1].sheet == pages[target].sheet:
        target += 1
    # nor between two sheets of an Excel workbook: after the workbook
    for section in sections(document):
        if section.book is not None and section.first < target <= section.last:
            return section.last + 1
    return target


def copy_name(name: str, taken: set) -> str:
    """Excel's name for a copied sheet: "Loads (2)", then (3)…, not one of
    *taken* (lower case)."""
    n = 2
    while f"{name} ({n})".lower() in taken:
        n += 1
    return f"{name} ({n})"


def workbook_copy(document, section: Section) -> list:
    """Page records of a copy of the workbook *section*: every sheet with
    its cells, formats, names, print settings and Print / Don't Print, and
    the markups on its pages (the user, 2026-10-22: "Duplicate Page on a
    workbook ... should insert a whole new workbook"). Each sheet is named
    as Excel names a copy ("Loads (2)"), the copy's formulas and names read
    its own sheets, and the copy is a workbook of its own (an Excel
    workbook's copy as Self-contained as it is, sheets made here a
    self-contained one; its name for the equations unique, Loads_2) — so
    equations reading the original go on reading the original."""
    import uuid

    from ..sheet import formula as F
    from ..sheet.docbook import book_for
    from ..sheet.xlsx import workbook_ident
    wb = book_for(document).workbook
    entries = fresh_item_ids([document.pages[i].to_dict() for i in section.pages])
    taken = {sheet.name.lower() for sheet in wb.sheets}
    tables = [payload["table"] for entry in entries for payload in entry.get("items", [])
              if isinstance(payload, dict) and payload.get("type") == "sheet_run"
              and isinstance(payload.get("table"), dict)]
    renamed = {}
    for table in tables:
        old = table.get("name") or "Sheet"
        new = copy_name(old, taken)
        taken.add(new.lower())
        renamed[old] = new
        table["name"] = new
    import os

    from ..sheet.docbook import sheet_ident
    idents = {b.name for b in wb.books.values()}
    idents |= {sheet_ident(s.name) for s in wb.sheets} | {sheet_ident(n) for n in taken}
    shown = {_book_shown(b.file, b.name).lower() for b in wb.books.values()}
    shown |= {s.name.lower() for s in sections(document)}
    found = wb.books.get(section.book) if section.book is not None else None
    if found is not None:
        stem, ext = os.path.splitext(os.path.basename(found.file or ""))
        title = copy_name(stem or found.name, shown)
        file, own = title + (ext or ".xlsx"), found.self_contained
    else:
        # sheets made here: the copy a workbook of its own, so that its names
        # are its own and not the original's again
        title = copy_name(section.name, shown)
        file, own = title, True
    # the copy's file name says it is the copy (Loads (2).xlsx): it is how
    # the workbook is shown; its name for the equations is unique (Loads_2)
    book = {"id": "book-" + uuid.uuid4().hex[:12], "name": workbook_ident(file, idents),
            "file": file, "self_contained": own}

    def moved(text: str) -> str:
        for old, new in renamed.items():
            if old.lower() in text.lower():
                try:
                    text = F.rename_sheet_in(text, old, new)
                except F.FormulaError:
                    pass
        return text
    for table in tables:
        for cell in table.get("cells", []):
            if isinstance(cell[2], str) and cell[2].startswith("="):
                cell[2] = "=" + moved(cell[2][1:])
        for entry in table.get("names", []):
            entry[1] = moved(entry[1])
        table["book"] = dict(book)
    return entries


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
            # a page's rows go with it (a page across: its row of pages' rows)
            down = sorted({paging.page_of(k)[0] for k in gone if k < paging.pages}, reverse=True)
            for i in down:
                a, b = paging.slices[i]
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
    return book_kept_whole(document, pages)


def book_kept_whole(document, pages: list) -> bool:
    """Whether every Excel workbook's sheets are still side by side in
    *pages* (the document's pages in a new order): nothing goes between the
    sheets of a workbook brought in."""
    books = {}
    for section in sections(document):
        if section.book is not None:
            for run in section.runs:
                books[run] = section.book
    if not books:
        return True
    where: dict = {}
    for i, page in enumerate(pages):
        book = books.get(page.sheet) if page.sheet is not None else None
        if book is not None:
            where.setdefault(book, []).append(i)
    return all(spots[-1] - spots[0] + 1 == len(spots) for spots in where.values())


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


def duplicate_workbooks(window, wanted: list) -> bool:
    """Duplicate Page on a workbook (its entry, or any of its pages): a copy
    of the whole workbook as a new workbook right after it (workbook_copy),
    one undo step, and the copy gone to. False when none of *wanted* is a
    workbook's page (an ordinary page is duplicated as it always was)."""
    import os

    from ..core.document import Page
    document = window.document
    touched = [s for s in sections(document) if any(i in s.pages for i in wanted)]
    if not touched:
        return False
    copies = [(section.last + 1, workbook_copy(document, section)) for section in touched]

    def mutate():
        first = None
        for at, entries in reversed(copies):
            for offset, entry in enumerate(entries):
                page = Page.from_dict(entry)
                page.uid = os.urandom(8).hex()
                document.pages.insert(at + offset, page)
        shift = 0
        for at, entries in copies:
            if first is None:
                first = at + shift
            shift += len(entries)
        window.current_index = first
    names = ", ".join(s.name for s in touched)
    window._structural_change("Duplicate workbook", mutate)
    from .sheetview import is_on
    if is_on(window):
        window.go_to_page(window.current_index)       # the copy, shown
    window.status_hint.setText(f"Duplicated {names}: the copy follows it")
    return True
