"""Excel workbooks in the window (spreadsheet phase 6): File ▸ Open of an
.xlsx, and Insert ▸ Excel workbook…, bring each worksheet in as a run of
spreadsheet pages (sheet/xlsx.py) — cells only, nothing written back.

What could not come across (charts, pictures, a print scale…) and any cell
whose formula here gives another answer than Excel last showed are said
when it opens.
"""
from __future__ import annotations

from typing import Optional

from ..core.document import LANDSCAPE, PORTRAIT, Page, PageSetup

OPEN_FILTER = ("Documents and Excel workbooks (*.pdf *.xlsx *.xlsm);;PDF documents (*.pdf);;"
               "Excel workbooks (*.xlsx *.xlsm);;All files (*)")


def is_workbook(path: str) -> bool:
    return str(path).lower().endswith((".xlsx", ".xlsm"))


def _setup_for(sheet, base: PageSetup) -> PageSetup:
    setup = PageSetup.from_dict(base.to_dict())
    if sheet.paper:
        setup.apply_size(sheet.paper)
    if sheet.orientation:
        setup.orientation = LANDSCAPE if sheet.orientation == "landscape" else PORTRAIT
    if sheet.margins_mm:
        setup.margin_left, setup.margin_top, setup.margin_right, setup.margin_bottom = (
            max(0.0, float(v)) for v in sheet.margins_mm)
    return setup


def _pages_needed(data: dict, setup: PageSetup) -> int:
    from ..sheet.pagination import paginate
    from ..sheet.store import load_sheet
    from ..sheet.workbook import Workbook

    wb = Workbook()
    wb.journal = False
    sheet = wb.add_sheet(data["name"])
    load_sheet(sheet, data)
    return max(1, paginate(sheet, setup).pages)


def pages_for(imported, base: PageSetup) -> list:
    """The pages of an imported workbook: each worksheet a run of
    spreadsheet pages, its cells on the run's first page."""
    from ..items.sheetpage import SheetRunItem

    pages = []
    for sheet in imported.sheets:
        setup = _setup_for(sheet, base)
        item = SheetRunItem()
        record = item.serialize()
        record["table"] = sheet.data
        count = _pages_needed(sheet.data, setup)
        for k in range(count):
            page = Page(PageSetup.from_dict(setup.to_dict()))
            page.sheet = item.uid
            if k == 0:
                page._pending_items = [record]
            pages.append(page)
    return pages


def _taken(document) -> set:
    from ..sheet.docbook import book_for
    return {s.name for s in book_for(document).workbook.sheets}


def report(window, imported) -> str:
    """What to tell the reader once the workbook is in: what was left out, and
    the cells whose formulas give another answer here than Excel showed."""
    from ..items.sheetpage import SheetRunItem

    runs = {}
    for frame in window.scene.frames:
        for item in frame.markups():
            if isinstance(item, SheetRunItem) and item.sheet is not None:
                runs[item.sheet.name] = item
    differ = []
    names_missing = set()
    from ..sheet.refs import col_letters
    from ..sheet.values import ErrorValue, Qty
    for sheet in imported.sheets:
        item = runs.get(sheet.name)
        if item is None:
            continue
        cells = item.sheet.cells
        for (r, c), excel in sheet.excel_values.items():
            cell = cells.get((r, c))
            mine = cell.value if cell is not None else None
            if isinstance(mine, Qty):
                mine = mine.value
            if isinstance(mine, ErrorValue):
                if mine.code == "#NAME?":
                    names_missing.add(f"{sheet.name}!{col_letters(c)}{r + 1}")
                if str(excel) == mine.code:
                    continue
                differ.append(f"{sheet.name}!{col_letters(c)}{r + 1}")
                continue
            if isinstance(excel, bool) or isinstance(mine, bool):
                same = excel == mine
            elif isinstance(excel, (int, float)) and isinstance(mine, (int, float)):
                same = abs(float(excel) - float(mine)) <= 1e-9 * max(1.0, abs(float(excel)))
            elif hasattr(excel, "year"):
                same = True              # a date as Excel's own type: shown by its format
            else:
                same = str(excel) == str(mine) or (excel in ("", None) and mine in (0.0, None))
            if not same:
                differ.append(f"{sheet.name}!{col_letters(c)}{r + 1}")
    lines = []
    count = len(imported.sheets)
    lines.append(f"{count} worksheet{'s' * (count != 1)} came in as spreadsheet pages.")
    hidden = [s.name for s in imported.sheets if s.hidden]
    if hidden:
        lines.append("Hidden in Excel (shown here): " + ", ".join(hidden) + ".")
    if imported.left_out:
        lines.append("Left out: " + "; ".join(imported.left_out) + ".")
    if differ:
        shown = ", ".join(differ[:8]) + (f" and {len(differ) - 8} more" if len(differ) > 8 else "")
        lines.append(f"{len(differ)} formula{'s' * (len(differ) != 1)} give another answer here "
                     f"than Excel last showed: {shown}.")
    if names_missing:
        lines.append("Functions or names CalcForge doesn't know: " +
                     ", ".join(sorted(names_missing)[:8]) + ".")
    window._last_import_report = lines
    return "\n".join(lines)


def _say(window, imported) -> None:
    text = report(window, imported)
    window.status_hint.setText(text.splitlines()[0] if text else "")
    if getattr(window, "interactive_prompts", True) and len(text.splitlines()) > 1:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(window, "Excel workbook", text)


def insert_workbook(window, path: Optional[str] = None, index: Optional[int] = None) -> bool:
    """Insert ▸ Excel workbook…: its worksheets as spreadsheet pages after the
    current page, one undo step."""
    from ..sheet.xlsx import read_workbook
    from .sheetpages import safe_target

    if path is None:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(window, "Insert Excel workbook", "",
                                              "Excel workbooks (*.xlsx *.xlsm)")
        if not path:
            return False
    try:
        imported = read_workbook(path, taken=_taken(window.document))
    except Exception as exc:  # noqa: BLE001
        from PySide6.QtWidgets import QMessageBox
        if getattr(window, "interactive_prompts", True):
            QMessageBox.critical(window, "Excel workbook", f"Could not read the workbook:\n{exc}")
        window.status_hint.setText(f"Could not read the workbook: {exc}")
        return False
    document = window.document
    which = window.page_index(index)
    target = safe_target(document, which + 1)
    base = document.pages[which].setup
    pages = pages_for(imported, base)

    def mutate():
        for offset, page in enumerate(pages):
            document.pages.insert(target + offset, page)
        window.current_index = target
    window._structural_change("Insert Excel workbook", mutate)
    _say(window, imported)
    return True


def open_workbook(window, path: str):
    """File ▸ Open of an .xlsx: a new document of its worksheets. Returns
    the document and what was read."""
    from ..core.document import Document
    from ..sheet.xlsx import read_workbook

    imported = read_workbook(path)
    document = Document()
    import os
    document.title = os.path.splitext(os.path.basename(path))[0]
    base = document.pages[0].setup if document.pages else PageSetup()
    document.pages = pages_for(imported, base)
    document.modified = False
    return document, imported
