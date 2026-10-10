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


class _Layout:
    """Just what pagination reads of a sheet's record — its sizes, what is
    filled and its page options — so its pages are counted without
    calculating it (that is done once, when it is on its pages)."""

    def __init__(self, data: dict):
        self.page = data.get("page") or {}
        self.widths = {int(k): float(v) for k, v in data.get("widths", {}).items()}
        self.heights = {int(k): float(v) for k, v in data.get("heights", {}).items()}
        self.hidden_rows = set(data.get("hidden_rows", [])) | set(data.get("filtered_rows", []))
        self.hidden_cols = set(data.get("hidden_cols", []))
        self.default_width = float(data.get("default_width", 48.0))
        self.default_height = float(data.get("default_height", 15.0))
        filled = [(e[0], e[1]) for e in data.get("cells", []) if e[2]]
        self._area = (min(r for r, _ in filled), min(c for _, c in filled),
                      max(r for r, _ in filled), max(c for _, c in filled)) if filled else None

    def width(self, col: int) -> float:
        return 0.0 if col in self.hidden_cols else self.widths.get(col, self.default_width)

    def height(self, row: int) -> float:
        return 0.0 if row in self.hidden_rows else self.heights.get(row, self.default_height)

    def data_area(self):
        return self._area


def _pages_needed(data: dict, setup: PageSetup) -> int:
    from ..sheet.pagination import paginate
    return max(1, paginate(_Layout(data), setup).pages)


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


class SheetChooser:
    """The worksheets of a workbook with more than one, each with a tick —
    all ticked to start — to bring in only some."""

    def __init__(self, parent, imported):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                                       QListWidget, QListWidgetItem, QPushButton, QVBoxLayout)
        self.dialog = dialog = QDialog(parent)
        dialog.setWindowTitle("Import Excel workbook")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Bring in these worksheets:"))
        self.list = QListWidget()
        for sheet in imported.sheets:
            count = len(sheet.data.get("cells", []))
            note = f"{count:,} cell{'s' * (count != 1)}" + (", hidden in Excel" if sheet.hidden else "")
            entry = QListWidgetItem(f"{sheet.name}    ({note})")
            entry.setData(Qt.UserRole, sheet.name)
            entry.setFlags(entry.flags() | Qt.ItemIsUserCheckable)
            entry.setCheckState(Qt.Checked)
            self.list.addItem(entry)
        layout.addWidget(self.list)
        row = QHBoxLayout()
        for label, state in (("Select all", Qt.Checked), ("Clear", Qt.Unchecked)):
            button = QPushButton(label)
            button.clicked.connect(lambda _=False, s=state: self._tick_all(s))
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(dialog.accept)
        self.buttons.rejected.connect(dialog.reject)
        layout.addWidget(self.buttons)
        self.list.itemChanged.connect(lambda _i: self._enable())

    def _tick_all(self, state) -> None:
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(state)

    def _enable(self) -> None:
        from PySide6.QtWidgets import QDialogButtonBox
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(bool(self.chosen()))

    def chosen(self) -> list:
        from PySide6.QtCore import Qt
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked]


def choose_sheets(window, imported) -> bool:
    """Which worksheets of a workbook with more than one to bring in; the
    rest are left out (``keep_only``). False when the reader cancels."""
    from ..sheet.xlsx import keep_only

    names = [s.name for s in imported.sheets]
    if len(names) < 2:
        return True
    pick = getattr(window, "choose_workbook_sheets", None)    # a test's stand-in for the dialog
    if pick is not None:
        chosen = pick(names)
    elif not getattr(window, "interactive_prompts", True):
        chosen = names
    else:
        chooser = SheetChooser(window, imported)
        if not chooser.dialog.exec():
            return False
        chosen = chooser.chosen()
    if not chosen:
        return False
    keep_only(imported, chosen)
    return True


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
    if not choose_sheets(window, imported):
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
    """File ▸ Open of an .xlsx: a new document of the worksheets chosen.
    Returns the document and what was read, or (None, None) when the reader
    cancelled the choice."""
    from ..core.document import Document
    from ..sheet.xlsx import read_workbook

    imported = read_workbook(path)
    if not choose_sheets(window, imported):
        return None, None
    document = Document()
    import os
    document.title = os.path.splitext(os.path.basename(path))[0]
    base = document.pages[0].setup if document.pages else PageSetup()
    document.pages = pages_for(imported, base)
    document.modified = False
    return document, imported
