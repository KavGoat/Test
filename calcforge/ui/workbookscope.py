"""Whether an imported Excel workbook is self-contained, changed after it
came in (the user's answers, 2026-10-19): from its sheet tab's right-click
menu (Self-contained, a tick) and from the Properties panel's Workbook
section, as one undo step, saved with the document.

Self-contained, a workbook is closed as a self-contained calculation block
is: its Excel names are for its own cells, and the equations read it only by
its CalcForge variables and as Sheet.H44 (xlsximport.SELF_CONTAINED_SAYS).
Unticked, its Excel names can be dialled in to as well (Sheet.Name), never
read bare, so they never clash with the document's (OPEN_SAYS).
"""
from __future__ import annotations

from typing import Optional


def book_of(sheet):
    """The imported workbook *sheet* is part of, or None."""
    if sheet is None or getattr(sheet, "book", None) is None:
        return None
    return sheet.workbook.books.get(sheet.book)


def runs_of(window, book_id: str) -> list:
    """The sheet runs (one per worksheet) of an imported workbook."""
    from ..items.sheetpage import SheetRunItem
    out = []
    for frame in getattr(window.view.scene(), "frames", []) or []:
        for item in frame.markups():
            if isinstance(item, SheetRunItem) and item.sheet is not None \
                    and item.sheet.book == book_id:
                out.append(item)
    return out


def set_self_contained(window, book_id: str, on: bool) -> bool:
    """Makes the workbook self-contained (or not) as one undo step. False
    when nothing changed."""
    runs = runs_of(window, book_id)
    if not runs:
        return False
    wb = runs[0].sheet.workbook
    book = wb.books.get(book_id)
    if book is None or book.self_contained == bool(on):
        return False
    view = window.view
    frames = []
    for item in runs:
        if item.parentItem() not in frames:
            frames.append(item.parentItem())
    view.begin_snapshot(frames)
    wb.set_self_contained(book_id, bool(on))
    view.commit_snapshot("Self-contained" if on else "Not self-contained")
    for item in runs:
        item.update()
    from .xlsximport import OPEN_SAYS, SELF_CONTAINED_SAYS
    window.status_hint.setText(f"{book.name}: " + (SELF_CONTAINED_SAYS if on else OPEN_SAYS))
    _refresh(window)
    return True


def _refresh(window) -> None:
    panel = getattr(window, "properties_panel", None)
    if panel is not None:
        panel.show_items(window.selected_items())
    variables = getattr(window, "variables_panel", None)
    if variables is not None and hasattr(variables, "refresh"):
        variables.refresh()


def open_sheet(window):
    """The imported workbook's sheet the Properties panel speaks for: the
    one open for its cells, else the spreadsheet page in view."""
    tables = getattr(window.view, "tables", None)
    item = getattr(tables, "item", None) if tables is not None else None
    if item is not None and book_of(item.sheet) is not None:
        return item.sheet
    pages = window.document.pages
    index = getattr(window, "current_index", 0)
    if not 0 <= index < len(pages) or pages[index].sheet is None:
        return None
    uid = pages[index].sheet
    for frame in getattr(window.view.scene(), "frames", []) or []:
        for markup in frame.markups():
            if getattr(markup, "uid", None) == uid and book_of(getattr(markup, "sheet", None)):
                return markup.sheet
    return None


def add_panel_section(panel, sheet) -> None:
    """The Properties panel's Workbook section: the workbook's name for the
    equations and its Self-contained tick."""
    from PySide6.QtWidgets import QCheckBox, QLabel

    book = book_of(sheet)
    if book is None:
        return
    form = panel._group("Workbook")
    name = QLabel(book.name)
    name.setObjectName("workbookName")
    name.setToolTip("How equations name this workbook, when it isn't self-contained: "
                    "Book.Name dials in to one of its Excel names")
    form.addRow("Name:", name)
    if book.file:
        form.addRow("From:", QLabel(book.file))
    tick = QCheckBox("Self-contained")
    tick.setObjectName("workbookSelfContained")
    tick.setChecked(book.self_contained)
    from .xlsximport import SELF_CONTAINED_SAYS
    tick.setToolTip(SELF_CONTAINED_SAYS + " Untick to let equations dial in to its Excel names.")
    window = panel.window

    def toggled(on, book_id=book.id):
        if not set_self_contained(window, book_id, on):
            tick.blockSignals(True)
            tick.setChecked(not on)
            tick.blockSignals(False)
    tick.toggled.connect(toggled)
    form.addRow("", tick)


def tab_action(menu, sheet, window) -> Optional[object]:
    """The sheet tab menu's Self-contained tick, for a sheet of an imported
    workbook."""
    book = book_of(sheet)
    if book is None:
        return None
    act = menu.addAction("Self-contained")
    act.setCheckable(True)
    act.setChecked(book.self_contained)
    from .xlsximport import SELF_CONTAINED_SAYS
    act.setToolTip(SELF_CONTAINED_SAYS + " Untick to let equations dial in to its Excel names.")
    act.triggered.connect(lambda on, book_id=book.id: set_self_contained(window, book_id, on))
    return act
