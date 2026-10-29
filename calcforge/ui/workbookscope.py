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
        for item in frame.built_markups():
            if isinstance(item, SheetRunItem) and item.sheet is not None \
                    and item.sheet.book == book_id:
                out.append(item)
    return out


def run_of_sheet(window, sheet):
    """The spreadsheet pages' item (SheetRunItem) of *sheet*, or None."""
    return next((r for r in runs_of(window, sheet.book) if r.sheet is sheet), None) \
        if sheet is not None and sheet.book is not None else None


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
        for markup in frame.built_markups():
            if getattr(markup, "uid", None) == uid and book_of(getattr(markup, "sheet", None)):
                return markup.sheet
    return None


def section_of_book(window, book_id: str):
    """The workbook *book_id* is, as laid out in the document (a Section)."""
    from .sheetpages import sections
    return next((s for s in sections(window.document) if s.book == book_id), None)


def open_names(window, book_id: str) -> None:
    """The Name Manager on workbook *book_id*: its sheet in view opened
    for its cells first when none of its sheets is (the Name Manager works
    on the open sheet's names, as Excel's on the active workbook's)."""
    tables = window.view.tables
    if tables.item is None or getattr(tables.item.sheet, "book", None) != book_id:
        runs = runs_of(window, book_id)
        shown = [r for r in runs if r.parentItem() is not None and
                 window.document.index_of(r.parentItem().page) == window.current_index]
        if not runs:
            return
        tables.open((shown or runs)[0])
    from .names import name_manager
    name_manager(tables, key=book_id)


def add_panel_section(panel, sheet) -> None:
    """The Properties panel's Workbook section (the user, 2026-10-24: "a
    better property panel for workbook and work sheets"): the workbook as
    Thumbnails and the tabs show it, its name for the equations, the file it
    came from, its sheets and pages, Self-contained, its names (the Name
    Manager on it) and Print for all its sheets. An imported workbook and
    one made here alike."""
    import os

    from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QWidget

    book = book_of(sheet)
    if book is None:
        return
    window = panel.window
    section = section_of_book(window, book.id)
    form = panel._group("Workbook")
    if section is not None:
        title = QLabel(section.name)
        title.setObjectName("workbookTitle")
        title.setToolTip("The workbook as Thumbnails and the sheet tabs show it")
        form.addRow("Workbook:", title)
    name = QLabel(book.name)
    name.setObjectName("workbookName")
    name.setToolTip("How equations name this workbook, when it isn't self-contained: "
                    "Book.Name dials in to one of its Excel names")
    form.addRow("Name:", name)
    if book.file and os.path.splitext(book.file)[1]:
        source = QLabel(book.file)
        source.setObjectName("workbookFile")
        source.setToolTip("The Excel file it was brought in from")
        form.addRow("From:", source)
    if section is not None:
        count = len(section.runs)
        sheets = QLabel(f"{count} sheet{'s' if count != 1 else ''} · {section.page_range()}")
        sheets.setObjectName("workbookSheets")
        form.addRow("Sheets:", sheets)
    tick = QCheckBox("Self-contained")
    tick.setObjectName("workbookSelfContained")
    tick.setChecked(book.self_contained)
    from .xlsximport import SELF_CONTAINED_SAYS
    tick.setToolTip(SELF_CONTAINED_SAYS + " Untick to let equations dial in to its Excel names.")

    def toggled(on, book_id=book.id):
        if not set_self_contained(window, book_id, on):
            tick.blockSignals(True)
            tick.setChecked(not on)
            tick.blockSignals(False)
    tick.toggled.connect(toggled)
    form.addRow("", tick)

    # its names: how many, and the Name Manager on them
    wb = sheet.workbook
    ids = {s.id for s in wb.sheets if s.book == book.id}
    count = sum(1 for dn in wb.names.values()
                if not dn.variable and (dn.book == book.id or dn.sheet in ids))
    row = QWidget()
    line = QHBoxLayout(row)
    line.setContentsMargins(0, 0, 0, 0)
    names = QLabel(f"{count} name{'s' if count != 1 else ''}")
    names.setObjectName("workbookNameCount")
    line.addWidget(names)
    manage = QPushButton("Name Manager…")
    manage.setObjectName("workbookNames")
    manage.setToolTip("This workbook's names, its own and its sheets' (Ctrl+F3 on its cells)")
    manage.clicked.connect(lambda _c=False, book_id=book.id: open_names(window, book_id))
    line.addWidget(manage)
    line.addStretch(1)
    form.addRow("Names:", row)

    if section is not None:
        # Print, for every sheet of it, ticked when all of them print (a
        # sheet's own Print is on its tab and in its Worksheet section)
        from .sheetpages import sheet_prints
        printing = [sheet_prints(window.document, uid) for uid in section.runs]
        some = sum(printing)
        prints = QCheckBox("Print" if some in (0, len(printing)) else
                           f"Print ({some} of {len(printing)} sheets do)")
        prints.setObjectName("workbookPrint")
        prints.setToolTip("Ticked, every sheet of this workbook prints and exports; unticked, "
                          "none does (their cells are still read)")
        prints.setChecked(all(printing))

        def print_all(on, chosen=section.pages):
            window.set_pages_printable(list(chosen), bool(on))
            _refresh(window)
        prints.toggled.connect(print_all)
        form.addRow("", prints)


def add_sheet_rows(panel, form, item) -> None:
    """The Worksheet section's rows after its name and size: where its
    pages are, and Print for its pages (as its tab's Print)."""
    from PySide6.QtWidgets import QCheckBox, QLabel

    from .sheetpages import run_pages, sheet_prints
    window = panel.window
    document = window.document
    pages = run_pages(document, item.uid)
    if not pages:
        return
    numbers = document.printed_numbers()
    shown = [numbers[i] for i in pages if numbers[i]]
    where = QLabel("doesn't print" if not shown else
                   f"page {shown[0]}" if shown[0] == shown[-1] else
                   f"pages {shown[0]}–{shown[-1]}")
    where.setObjectName("sheetPages")
    form.addRow("Pages:", where)
    prints = QCheckBox("Print")
    prints.setObjectName("sheetPrint")
    prints.setToolTip("Ticked, this sheet's pages print and export; unticked (Don't Print) "
                      "they are left out. Its cells are still read by equations and other "
                      "sheets.")
    prints.setChecked(sheet_prints(document, item.uid))

    def toggled(on, uid=item.uid):
        from .sheetpages import set_sheet_printing
        set_sheet_printing(window, uid, on)
        _refresh(window)
    prints.toggled.connect(toggled)
    form.addRow("", prints)


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
