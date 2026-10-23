"""Excel workbooks in the window (spreadsheet phase 6): File ▸ Open of an
.xlsx, and Insert ▸ Excel workbook…, bring each worksheet in as a run of
spreadsheet pages (sheet/xlsx.py) — cells only, nothing written back.

What could not come across (charts, pictures, a print scale…) and any cell
whose formula here gives another answer than Excel last showed are said
when it opens.

A workbook comes in as one (docs/SPREADSHEET_DESIGN.md, the user's answers
of 2026-10-19): its sheets share its names. Self-contained (the default, a
tick in the chooser) it is closed, as a self-contained calculation block is
(the user, 2026-10-24): its Excel names are for its own cells, and the
equations read it only by its CalcForge variables (a cell named in the
Variable box) and by sheet and cell (Sheet.H44). Unticked, its Excel names
can be dialled in to as well — Sheet.Name or Book.Name from an equation,
=Sheet!Name from a cell — but never read bare, as a spreadsheet's own names
aren't (the user: "un self contained workbook variable names (like
spreadsheet names) should not be accessible from outside unless I dial in").
"""
from __future__ import annotations

from typing import Optional

from ..core.document import LANDSCAPE, PORTRAIT, Page, PageSetup

# an Excel template (.xltx, .xltm) is a workbook too, opened as one (a user's
# Equivalent Static calculation came as one)
EXCEL_FILTER = "Excel workbooks (*.xlsx *.xlsm *.xltx *.xltm)"
OPEN_FILTER = ("Documents and Excel workbooks (*.pdf *.xlsx *.xlsm *.xltx *.xltm);;"
               "PDF documents (*.pdf);;" + EXCEL_FILTER + ";;All files (*)")


# what a workbook's Self-contained tick means, said the same way everywhere:
# a CalcForge variable (a cell named in its Variable box, read bare by the
# equations) is not an Excel name (the workbook's own, from its Name Manager)
SELF_CONTAINED_SAYS = ("Self-contained: its Excel names are for its own cells. Equations below "
                       "read a cell you name as a variable (right-click ▸ Variable), or any cell "
                       "as Sheet.H44.")
OPEN_SAYS = ("Not self-contained: equations below can also dial in to its Excel names, "
             "Sheet.Name (never bare); cells too, =Sheet!Name.")


def is_workbook(path: str) -> bool:
    return str(path).lower().endswith((".xlsx", ".xlsm", ".xltx", ".xltm"))


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


def _drawing_records(sheet, document=None) -> list:
    """The worksheet's charts as chart markups, and its pictures as image
    markups (their pictures kept in *document*), each held to the cell
    Excel anchors it at (the run puts it there once laid out:
    items/sheetpage.py)."""
    from PySide6.QtCore import QRectF

    from ..items.chart import ChartItem
    from ..items.media import ImageItem

    out = []
    for found in getattr(sheet, "charts", None) or ():
        chart = ChartItem(found["spec"])
        record = chart.serialize()
        record["w"], record["h"] = found["w"], found["h"]
        record["cell_anchor"] = list(found["anchor"])
        out.append(record)
    if document is not None:
        for found in getattr(sheet, "pictures", None) or ():
            key = document.add_asset(found["data"], found["suffix"])
            picture = ImageItem(key, QRectF(0, 0, found["w"], found["h"]))
            record = picture.serialize()
            record["cell_anchor"] = list(found["anchor"])
            out.append(record)
    return out


def pages_for(imported, base: PageSetup, document=None) -> list:
    """The pages of an imported workbook: each worksheet a run of
    spreadsheet pages, its cells, charts and pictures on the run's first
    page (the pictures kept in *document*)."""
    from ..items.sheetpage import SheetRunItem

    pages = []
    silent = getattr(imported, "no_print", None) or set()
    for sheet in imported.sheets:
        setup = _setup_for(sheet, base)
        item = SheetRunItem()
        record = item.serialize()
        record["table"] = sheet.data
        count = _pages_needed(sheet.data, setup)
        for k in range(count):
            page = Page(PageSetup.from_dict(setup.to_dict()))
            page.sheet = item.uid
            page.printable = sheet.name not in silent     # Don't Print, chosen on import
            if k == 0:
                page._pending_items = [record] + _drawing_records(sheet, document)
            pages.append(page)
    return pages


def _taken(document) -> set:
    from ..sheet.docbook import book_for
    return {s.name for s in book_for(document).workbook.sheets}


def book_name_for(document, path: str, imported) -> str:
    """The workbook's name for the equations, unique in the document."""
    from ..sheet.docbook import book_for, sheet_ident
    from ..sheet.xlsx import workbook_ident

    taken = {sheet_ident(s.name) for s in imported.sheets}
    if document is not None:
        wb = book_for(document).workbook
        taken |= {sheet_ident(s.name) for s in wb.sheets}
        taken |= {b.name for b in wb.books.values()}
    return workbook_ident(path, taken)


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
    book = (imported.sheets[0].data.get("book") if imported.sheets else None) or {}
    if book.get("name"):
        if book.get("self_contained", True):
            lines.append(SELF_CONTAINED_SAYS)
        else:
            lines.append(OPEN_SAYS)
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
    # (how its names are read is said; on its own it needs no message box)
    worth = [line for line in text.splitlines()[1:] if not line.startswith(("Self-contained:", "Its names"))]
    if getattr(window, "interactive_prompts", True) and worth:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(window, "Excel workbook", text)


class _SheetRow:
    """A worksheet's row in the chooser: its tick (bring it in) and its
    Print / Don't Print, read as the list's rows were before the Print
    column came (``item(i).checkState()``, ``.text()``)."""

    def __init__(self, item):
        self.item = item

    def checkState(self):
        return self.item.checkState(0)

    def setCheckState(self, state) -> None:
        self.item.setCheckState(0, state)

    def text(self) -> str:
        return self.item.text(0)

    def data(self, role):
        return self.item.data(0, role)

    def prints(self) -> bool:
        from PySide6.QtCore import Qt
        return self.item.checkState(1) == Qt.Checked

    def set_prints(self, on: bool) -> None:
        from PySide6.QtCore import Qt
        self.item.setCheckState(1, Qt.Checked if on else Qt.Unchecked)


class _SheetList:
    """The chooser's worksheets: a two-column list (the worksheet, ticked
    to bring it in; and Print, ticked while it is to print)."""

    def __init__(self, tree):
        self.tree = tree

    def count(self) -> int:
        return self.tree.topLevelItemCount()

    def item(self, row: int) -> _SheetRow:
        return _SheetRow(self.tree.topLevelItem(row))


class SheetChooser:
    """The worksheets of a workbook, each with a tick — all ticked to start —
    to bring in only some, and each with Print or Don't Print (Print to
    start; the user, 2026-10-21: "on import of Excel let me select print or
    not print a sheet individually"); and whether the workbook is
    self-contained (closed even to dialling in; ticked to start)."""

    KEEP, OPEN = "self-contained", "open"
    PRINT, NO_PRINT = "Print", "Don't Print"

    def __init__(self, parent, imported, book_name: str = "Workbook"):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView,
                                       QLabel, QPushButton, QTreeWidget, QTreeWidgetItem,
                                       QVBoxLayout)
        self.imported = imported
        self.dialog = dialog = QDialog(parent)
        dialog.setWindowTitle("Import Excel workbook")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Bring in these worksheets, and whether each prints:"))
        self.tree = tree = QTreeWidget()
        tree.setObjectName("workbookSheets")
        tree.setRootIsDecorated(False)
        tree.setUniformRowHeights(True)
        # by the keys too: arrows to a worksheet's tick or its Print, Space ticks it
        from PySide6.QtWidgets import QAbstractItemView
        tree.setSelectionBehavior(QAbstractItemView.SelectItems)
        tree.setColumnCount(2)
        tree.setHeaderLabels(["Worksheet", "Print"])
        tree.headerItem().setToolTip(1, "Print: its pages print and export. Don't Print: they "
                                        "come in, and their cells are read, but they are "
                                        "left out of printing and export")
        tree.header().setStretchLastSection(False)
        tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        # room for "Don't Print" and its tick, whichever it says
        tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
        tree.header().resizeSection(1, tree.fontMetrics().horizontalAdvance(self.NO_PRINT) + 48)
        for sheet in imported.sheets:
            count = len(sheet.data.get("cells", []))
            note = f"{count:,} cell{'s' * (count != 1)}" + (", hidden in Excel" if sheet.hidden else "")
            entry = QTreeWidgetItem([f"{sheet.name}    ({note})", self.PRINT])
            entry.setData(0, Qt.UserRole, sheet.name)
            entry.setFlags(entry.flags() | Qt.ItemIsUserCheckable)
            entry.setCheckState(0, Qt.Checked)
            entry.setCheckState(1, Qt.Checked)
            entry.setToolTip(1, "Ticked: Print. Unticked: Don't Print")
            tree.addTopLevelItem(entry)
        self.list = _SheetList(tree)
        layout.addWidget(tree)
        row = QHBoxLayout()
        for label, state in (("Select all", Qt.Checked), ("Clear", Qt.Unchecked)):
            button = QPushButton(label)
            button.clicked.connect(lambda _=False, s=state: self._tick_all(s))
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(dialog.reject)
        layout.addWidget(self.buttons)
        # a ticked sheet reading one left out: said before it is brought in
        from ..sheet.xlsx import sheet_links
        self.links = sheet_links(imported)
        self.warning = QLabel("")
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet("color: #c92a2a")
        self.warning.hide()
        layout.insertWidget(layout.count() - 1, self.warning)
        tree.itemChanged.connect(self._changed)
        self._scope_part(layout, book_name)
        dialog.resize(max(dialog.sizeHint().width(), 460), dialog.sizeHint().height())

    def _changed(self, item, column: int) -> None:
        """A tick changed: Print says Print or Don't Print, and a worksheet
        left out has its Print greyed (nothing of it comes in to print)."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPalette
        tree = self.tree
        was = tree.blockSignals(True)
        try:
            on = item.checkState(1) == Qt.Checked
            item.setText(1, self.PRINT if on else self.NO_PRINT)
            coming = item.checkState(0) == Qt.Checked
            item.setData(1, Qt.ForegroundRole, None if coming else
                         tree.palette().brush(QPalette.Disabled, QPalette.Text))
        finally:
            tree.blockSignals(was)
        if column == 0:
            self._enable()

    def no_print(self) -> list:
        """The worksheets chosen as Don't Print."""
        from PySide6.QtCore import Qt
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
                if not self.list.item(i).prints()]

    def set_prints(self, name: str, on: bool) -> None:
        """Print (or Don't Print) for the worksheet *name*."""
        from PySide6.QtCore import Qt
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == name:
                self.list.item(i).set_prints(on)

    def _scope_part(self, layout, book_name: str) -> None:
        """The Self-contained tick box, and under it what it means."""
        from PySide6.QtWidgets import QCheckBox, QLabel

        from ..sheet.xlsx import workbook_names
        self.book_name = book_name
        count = len(workbook_names(self.imported))
        self.self_contained = QCheckBox("Self-contained")
        self.self_contained.setChecked(True)
        self.self_contained.setToolTip(
            f"Its {count} Excel name{'s' * (count != 1)} are its own, for its cells. "
            f"{SELF_CONTAINED_SAYS[len('Self-contained: '):]} Untick to let equations dial in "
            "to its Excel names.")
        at = layout.count() - 1
        layout.insertWidget(at, self.self_contained)
        self.scope_note = QLabel("")
        self.scope_note.setWordWrap(True)
        layout.insertWidget(at + 1, self.scope_note)
        self.self_contained.toggled.connect(lambda _on: self._scope_shown())
        self._scope_shown()

    def _scope_shown(self) -> None:
        on = self.self_contained.isChecked()
        self.scope_note.setText(SELF_CONTAINED_SAYS if on else OPEN_SAYS)
        self.dialog.adjustSize()

    def scope(self) -> str:
        """KEEP (self-contained) or OPEN: what the reader chose."""
        return self.KEEP if self.self_contained.isChecked() else self.OPEN

    def _tick_all(self, state) -> None:
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(state)

    def _enable(self) -> None:
        from PySide6.QtWidgets import QDialogButtonBox
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(bool(self.chosen()))
        lines = self.missing()
        self.warning.setText(
            "\n".join(f"⚠ “{a}” reads “{b}”, which is not ticked." for a, b in lines)
            + ("\nFormulas reading a worksheet left out keep the values Excel last showed,"
               " and won't update." if lines else ""))
        self.warning.setVisible(bool(lines))

    def _accept(self) -> None:
        """OK with a ticked sheet reading one left out: asked first, with the
        choice of ticking those too."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QMessageBox
        lines = self.missing()
        if lines:
            box = QMessageBox(QMessageBox.Warning, "Import Excel workbook",
                              self.warning.text(), parent=self.dialog)
            tick = box.addButton("Tick those too", QMessageBox.AcceptRole)
            box.addButton("Bring in as chosen", QMessageBox.DestructiveRole)
            back = box.addButton(QMessageBox.Cancel)
            box.exec()
            if box.clickedButton() is back:
                return
            if box.clickedButton() is tick:
                while lines:                  # and whatever those read in turn
                    wanted = {b for _a, b in lines}
                    for i in range(self.list.count()):
                        if self.list.item(i).data(Qt.UserRole) in wanted:
                            self.list.item(i).setCheckState(Qt.Checked)
                    lines = self.missing()
        self.dialog.accept()

    def missing(self) -> list:
        """(ticked sheet, unticked sheet it reads) pairs."""
        chosen = self.chosen()
        return [(a, b) for a in chosen for b in sorted(self.links.get(a, ()))
                if b not in chosen]

    def chosen(self) -> list:
        from PySide6.QtCore import Qt
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked]


def choose_sheets(window, imported, path: str = "", document=None) -> bool:
    """Which worksheets of a workbook to bring in (the rest are left out,
    ``keep_only``) and whether it is self-contained: asked when it has more
    than one worksheet or any names. The workbook is then marked as one
    (``make_book``). False when the reader cancels."""
    import os

    from ..sheet.xlsx import keep_only, make_book, workbook_names

    names = [s.name for s in imported.sheets]
    book_name = book_name_for(document, path or "Workbook", imported)
    how = SheetChooser.KEEP
    pick = getattr(window, "choose_workbook_sheets", None)    # a test's stand-in for the dialog
    drive = getattr(window, "drive_workbook_chooser", None)   # a test's hand on the dialog
    chooser = None
    if pick is not None:
        chosen = pick(names) if len(names) > 1 else names
    elif drive is None and (not getattr(window, "interactive_prompts", True) or
                            (len(names) < 2 and not workbook_names(imported))):
        chosen = names
    else:
        chooser = SheetChooser(window, imported, book_name)
        if drive is not None:
            drive(chooser)
            accepted = chooser.dialog.result()
        else:
            accepted = chooser.dialog.exec()
        if not accepted:
            return False
        chosen = chooser.chosen()
        how = chooser.scope()
    if not chosen:
        return False
    keep_only(imported, chosen)
    # the worksheets chosen as Don't Print (pages_for): its pages come in not printing
    imported.no_print = set(chooser.no_print()) & set(chosen) if chooser is not None else set()
    make_book(imported, book_name, shown_file(document, os.path.basename(path or "")),
              how == SheetChooser.KEEP)
    return True


def shown_file(document, file: str) -> str:
    """The workbook's file name as shown, unique in the document: the same
    workbook brought in twice is "Loads" and "Loads (2)", as its sheets are
    (the user, 2026-10-23: "the workbook name was the same, sheets had a (2)")."""
    import os

    if document is None or not file:
        return file
    from ..sheet.docbook import book_for
    from .sheetpages import _book_shown, copy_name
    shown = {_book_shown(b.file, b.name).lower() for b in book_for(document).workbook.books.values()}
    stem, ext = os.path.splitext(file)
    if stem.lower() not in shown:
        return file
    return copy_name(stem, shown) + ext


def insert_workbook(window, path: Optional[str] = None, index: Optional[int] = None,
                    before: bool = False) -> bool:
    """Insert ▸ Excel workbook…: its worksheets as spreadsheet pages after (or
    *before*) the current page, one undo step."""
    from ..sheet.xlsx import read_workbook
    from .sheetpages import safe_target

    if path is None:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(window, "Insert Excel workbook", "", EXCEL_FILTER)
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
    if not choose_sheets(window, imported, path, window.document):
        return False
    document = window.document
    which = window.page_index(index)
    if before:
        # in front of the page, or of the whole spreadsheet run it is part of
        # (of the whole Excel workbook, on one of its sheets)
        target = which
        pages_now = document.pages
        while target > 0 and pages_now[target].sheet is not None \
                and pages_now[target - 1].sheet == pages_now[target].sheet:
            target -= 1
        from .sheetpages import section_of
        section = section_of(document, target)
        if section is not None and section.book is not None:
            target = section.first
    else:
        target = safe_target(document, which + 1)
    base = document.pages[which].setup
    pages = pages_for(imported, base, document)

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
    if not choose_sheets(window, imported, path, None):
        return None, None
    document = Document()
    import os
    document.title = os.path.splitext(os.path.basename(path))[0]
    base = document.pages[0].setup if document.pages else PageSetup()
    document.pages = pages_for(imported, base, document)
    document.modified = False
    return document, imported
