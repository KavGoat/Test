"""Excel's named ranges for tables and sheet pages: the Name Manager
(Ctrl+F3), Create from Selection (Ctrl+Shift+F3) and the Name Box.

A name is a cell, a block or a constant (W_total, Loads!$B$2:$B$9, g = 9.81)
that cell formulas and the document's equations use alike. Names are kept
with the sheet whose cells they name (a constant with the sheet it was made
on), so they are saved, undone and copied with it.
"""
from __future__ import annotations

import re
from typing import Callable, Optional

from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

from ..sheet.refs import col_letters, quote_sheet


def _frames(tables) -> list:
    """Every page holding a table or a spreadsheet: names live with sheets."""
    frames = []
    for other in tables._all_tables():
        frame = other.parentItem()
        if frame is not None and frame not in frames:
            frames.append(frame)
    return frames


def change_names(tables, label: str, change: Callable) -> Optional[str]:
    """Make a change to the names as one undo step; the problem, if any."""
    item = tables.item
    if item is None or item.sheet is None:
        return "No table is open"
    wb = item.sheet.workbook
    view = tables.view
    view.begin_snapshot(_frames(tables))
    try:
        change(wb)
    except ValueError as e:
        view.commit_snapshot(label)
        return str(e)
    except Exception as e:  # noqa: BLE001  (a formula that can't be read)
        view.commit_snapshot(label)
        return str(e)
    for other in tables._all_tables():
        other.update()
    view.commit_snapshot(label)
    from ..calc.docsheet import sheet_for
    sheet_for(view.window.document).recalculate()
    return None


def name_value(wb, dn) -> str:
    """What a name holds, shown as the Name Manager shows it."""
    from ..sheet import formula as F
    from ..sheet.evaluate import Ctx, RefValue, ev, result
    from ..sheet.numfmt import format_value
    from ..sheet.values import Array, SheetError

    try:
        tree = F.parse(dn.refers_to).tree
    except F.FormulaError:
        return "#NAME?"
    home = wb.sheet_by_id(dn.sheet) if dn.sheet else (wb.sheets[0] if wb.sheets else None)
    if home is None:
        return ""
    try:
        got = ev(tree, Ctx(wb, home, 0, 0))
    except SheetError as e:
        return e.error.code
    if isinstance(got, RefValue):
        got = got.value_at(0, 0) if got.single else got.to_array()
    elif not isinstance(got, Array):
        got = result(got)                      # a LAMBDA left uncalled: #CALC!, as in a cell
    if isinstance(got, Array):
        rows = [",".join(f'"{format_value(v).text}"' for v in row) for row in got.rows[:4]]
        more = "…" if got.height > 4 else ""
        return "{" + ";".join(rows) + more + "}"
    return format_value(got).text


def name_from_label(text) -> Optional[str]:
    """A heading as a name, as Excel makes it: "Load (kN)" -> Load_kN."""
    text = str(text or "").strip()
    if not text:
        return None
    name = re.sub(r"[^\w.]+", "_", text).strip("_")
    if not name:
        return None
    if name[0].isdigit():
        name = "_" + name
    from ..sheet.refs import is_cell_name
    if is_cell_name(name) or name.upper() in ("R", "C", "TRUE", "FALSE"):
        name += "_"
    return name


def _absolute(sheet_name: str, top: int, left: int, bottom: int, right: int) -> str:
    ref = f"{quote_sheet(sheet_name)}!${col_letters(left)}${top + 1}"
    if (top, left) != (bottom, right):
        ref += f":${col_letters(right)}${bottom + 1}"
    return ref


# -- Create from Selection ------------------------------------------------------------------------
def create_from_selection(tables, top_row=True, left_col=False, bottom_row=False,
                          right_col=False) -> list:
    """Names for the rows or columns of the selection, from its labels
    (Excel's Create from Selection). Returns the names made."""
    item = tables.item
    sheet = item.sheet
    t, l, b, r = tables.selection()
    made: list = []

    def label(row, col):
        cell = sheet.cells.get((row, col))
        return None if cell is None else cell.value

    plans = []
    if top_row or bottom_row:
        for col in range(l + (1 if left_col else 0), r + 1 - (1 if right_col else 0)):
            name = name_from_label(label(t if top_row else b, col))
            first = t + (1 if top_row else 0)
            last = b - (1 if bottom_row else 0)
            if name and first <= last:
                plans.append((name, _absolute(item.name, first, col, last, col)))
    if left_col or right_col:
        for row in range(t + (1 if top_row else 0), b + 1 - (1 if bottom_row else 0)):
            name = name_from_label(label(row, l if left_col else r))
            first = l + (1 if left_col else 0)
            last = r - (1 if right_col else 0)
            if name and first <= last:
                plans.append((name, _absolute(item.name, row, first, row, last)))

    def change(wb):
        for name, ref in plans:
            wb.define_name(name, ref)
            made.append(name)
    problem = change_names(tables, "Create names", change)
    if problem:
        tables.view.statusMessage.emit(problem)
    return made


class CreateFromSelectionDialog(QDialog):
    def __init__(self, parent=None, guess=(True, False, False, False)):
        super().__init__(parent)
        self.setWindowTitle("Create Names from Selection")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Create names from values in the:"))
        self.top = QCheckBox("Top row")
        self.left = QCheckBox("Left column")
        self.bottom = QCheckBox("Bottom row")
        self.right = QCheckBox("Right column")
        for box, on in zip((self.top, self.left, self.bottom, self.right), guess):
            box.setChecked(on)
            layout.addWidget(box)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def choice(self) -> dict:
        return {"top_row": self.top.isChecked(), "left_col": self.left.isChecked(),
                "bottom_row": self.bottom.isChecked(), "right_col": self.right.isChecked()}


def ask_create_from_selection(tables) -> None:
    item = tables.item
    if item is None:
        return
    t, l, b, r = tables.selection()
    # Excel's guess: text along the top makes the top row the labels
    text_top = any(isinstance((item.sheet.cells.get((t, c)) or _Nothing).value, str)
                   for c in range(l, r + 1))
    dialog = CreateFromSelectionDialog(tables.view, (text_top, not text_top, False, False))
    window = tables.view.window
    if not getattr(window, "interactive_prompts", True):
        window._last_data_dialog = dialog
        return
    if dialog.exec() == QDialog.Accepted:
        create_from_selection(tables, **dialog.choice())
    from .release import done_with
    done_with(dialog)


class _Nothing:
    value = None


# -- whose names: a workbook's, the tables', the CalcForge variables -------------------------------
#: The Name Manager's list beside the workbooks: names of the tables on
#: ordinary pages, and the document's CalcForge variables (cells named in
#: their Variable box), which a cell reads as CALC(name).
TABLES, VARIABLES = "tables", "variables"
TABLES_SHOWN, VARIABLES_SHOWN = "Tables on Pages", "CalcForge Variables"


def _home(wb, dn):
    """The sheet a name is kept with: the one it is local to, the one whose
    cells it names, else the one it was made on."""
    if dn.sheet is not None:
        return wb.sheet_by_id(dn.sheet)
    return wb._first_sheet_read(dn.refers_to) or \
        (wb.sheet_by_id(dn.home) if dn.home is not None else None)


def whose(wb, dn):
    """Whose list a name is on in the Name Manager: its workbook's Book.id,
    TABLES, or VARIABLES."""
    if dn.variable:
        return VARIABLES
    if dn.book is not None:
        return dn.book
    home = _home(wb, dn)
    if home is not None and home.book is not None:
        return home.book
    return TABLES


def scope_in_list(wb, dn) -> str:
    """The Name Manager's Scope, as Excel's: Workbook for a workbook's own
    name, the sheet's name for one local to a sheet; the tables' shared
    names are the Document's, and a CalcForge variable says where its cells
    are."""
    if dn.sheet is not None and wb.sheet_by_id(dn.sheet) is not None:
        return wb.sheet_by_id(dn.sheet).name
    if dn.variable:
        home = _home(wb, dn)
        return f"Document ({home.name})" if home is not None else "Document"
    return "Document" if whose(wb, dn) == TABLES else "Workbook"


def lists_of(window, wb) -> list:
    """The Name Manager's drop-down: (shown, key) for each workbook of the
    document in page order, then the tables on pages (when there are any),
    then the CalcForge variables."""
    from .sheetpages import sections
    out, seen = [], set()
    document = getattr(window, "document", None)
    for section in (sections(document) if document is not None else []):
        if section.book is not None and section.book not in seen:
            seen.add(section.book)
            out.append((section.name, section.book))
    for book in wb.books.values():
        if book.id not in seen and any(s.book == book.id for s in wb.sheets):
            seen.add(book.id)
            from .sheetpages import _book_shown
            out.append((_book_shown(book.file, book.name), book.id))
    if any(s.book is None for s in wb.sheets) or \
            any(whose(wb, dn) == TABLES for dn in wb.names.values()):
        out.append((TABLES_SHOWN, TABLES))
    out.append((VARIABLES_SHOWN, VARIABLES))
    return out


def sheets_of(wb, key) -> list:
    """The sheets a list's names may be local to."""
    if key == VARIABLES:
        return []
    if key == TABLES:
        return [s for s in wb.sheets if s.book is None]
    return [s for s in wb.sheets if s.book == key]


# -- New / Edit Name ------------------------------------------------------------------------------
class NameDialog(QDialog):
    """New Name / Edit Name: the name, its scope, a comment, what it refers
    to. Its Scope offers the workbook the Name Manager shows and that
    workbook's sheets only (*key*: Book.id, TABLES or VARIABLES; None: any
    sheet), as Excel's offers the workbook's own."""

    def __init__(self, wb, parent=None, dn=None, refers_to: str = "", key=None):
        super().__init__(parent)
        self.wb = wb
        self.key = key
        self.setWindowTitle("Edit Name" if dn is not None else "New Name")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(dn.name if dn is not None else "")
        form.addRow("Name:", self.name)
        self.scope = QComboBox()
        self.scope.addItem("Document" if key in (TABLES, VARIABLES) else "Workbook", None)
        for sheet in (wb.sheets if key is None else sheets_of(wb, key)):
            self.scope.addItem(sheet.name, sheet.id)
        if dn is not None and dn.sheet is not None:
            self.scope.setCurrentIndex(max(0, self.scope.findData(dn.sheet)))
        self.scope.setEnabled(self.scope.count() > 1)
        form.addRow("Scope:", self.scope)
        self.comment = QLineEdit(dn.comment if dn is not None else "")
        form.addRow("Comment:", self.comment)
        self.refers = QLineEdit("=" + (dn.refers_to if dn is not None else refers_to.lstrip("=")))
        form.addRow("Refers to:", self.refers)
        layout.addLayout(form)
        self.problem = QLabel("")
        self.problem.setStyleSheet("color: #c92a2a")
        layout.addWidget(self.problem)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._check)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple:
        sid = self.scope.currentData()
        sheet = self.wb.sheet_by_id(sid) if sid is not None else None
        return (self.name.text().strip(), self.refers.text().strip().lstrip("=").strip(),
                sheet, self.comment.text().strip())

    def _check(self) -> None:
        from ..sheet import formula as F
        from ..sheet.workbook import defined_name_problem

        name, refers, _sheet, _comment = self.values()
        problem = defined_name_problem(name)
        if problem is None and not refers:
            problem = "Say what the name refers to."
        if problem is None:
            try:
                F.parse(refers)
            except F.FormulaError as e:
                problem = str(e)
        if problem:
            self.problem.setText(problem)
            return
        self.accept()


def define(tables, name: str, refers_to: str, scope=None, comment: str = "",
           replacing=None, variable: Optional[bool] = None, home=None) -> Optional[str]:
    """Define (or redefine) a name as one undo step; the problem, if any.
    *variable*: a CalcForge variable (the cell's Variable box) or a
    spreadsheet's own name; None keeps what *replacing* was (a new name is
    the spreadsheet's). *home*: the sheet it is kept with, whose workbook it
    is a name of (the open sheet when not given)."""
    item = tables.item
    if variable is None:
        variable = bool(replacing is not None and replacing.variable)
    home = scope or home or item.sheet

    def change(wb):
        old = replacing
        if old is not None:
            if old.name != name:
                # renamed: every formula and equation using it follows, as
                # in Excel's Name Manager
                wb.rename_name(old, name)
                old = wb.names.get((name.lower(), old.key[1]), old)
            old_scope = wb.sheet_by_id(old.sheet) if old.sheet else None
            wb.remove_name(old.name, old_scope, old.book)
        wb.define_name(name, refers_to, scope, comment, home=home, variable=variable)
    return change_names(tables, "Define name", change)


def delete(tables, dn) -> Optional[str]:
    def change(wb):
        wb.remove_name(dn.name, wb.sheet_by_id(dn.sheet) if dn.sheet else None, dn.book)
    return change_names(tables, "Delete name", change)


def scope_text(wb, dn) -> str:
    """The Name Manager's Scope: a sheet's own name says the sheet; an
    imported workbook's says the workbook (and that it is self-contained:
    no dialling in); any other is the document's, Excel's Workbook."""
    if dn.sheet is not None and wb.sheet_by_id(dn.sheet) is not None:
        return wb.sheet_by_id(dn.sheet).name
    book = wb.books.get(dn.book) if dn.book else None
    if book is not None:
        return f"{book.name} (self-contained)" if book.self_contained else book.name
    return "Workbook (CalcForge variable)" if dn.variable else "Workbook"


# -- the Name Manager -----------------------------------------------------------------------------
class NameManagerDialog(QDialog):
    """Excel's Name Manager, one workbook at a time (the user, 2026-10-24:
    "name manager can you make it for each workbook and then inside shows
    each worksheet etc like excel. currently all in one"): the drop-down at
    the top picks the workbook — the open sheet's to start — or the tables
    on pages, or the document's CalcForge variables; the list is that
    workbook's names, its own (Scope: Workbook) and its sheets' (Scope: the
    sheet), with the CalcForge variables named on its cells. Two workbooks
    may each have a name Load: each list shows its own."""
    COLUMNS = ("Name", "Value", "Refers To", "Scope", "Comment")

    def __init__(self, tables, parent=None, key=None):
        super().__init__(parent)
        self.tables = tables
        self.setWindowTitle("Name Manager")
        self.resize(760, 380)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Workbook:"))
        self.whose = QComboBox()
        self.whose.setObjectName("nameManagerWorkbook")
        self.whose.setToolTip("Whose names to list: a workbook's (its own and its sheets'), "
                              "the tables on pages', or the CalcForge variables a cell reads "
                              "as CALC(name)")
        window = getattr(tables.view, "window", None)
        for shown, which in lists_of(window, self.wb):
            self.whose.addItem(shown, which)
        sheet = tables.item.sheet if tables.item is not None else None
        start = key if key is not None else (
            sheet.book if sheet is not None and sheet.book is not None else TABLES)
        self.whose.setCurrentIndex(max(0, self.whose.findData(start)))
        self.whose.currentIndexChanged.connect(lambda _i: self.refresh())
        top.addWidget(self.whose, 1)
        layout.addLayout(top)
        row = QHBoxLayout()
        self.new = QPushButton("New…")
        self.edit = QPushButton("Edit…")
        self.remove = QPushButton("Delete")
        for button in (self.new, self.edit, self.remove):
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        layout.addWidget(self.table, 1)
        self.problem = QLabel("")
        self.problem.setStyleSheet("color: #c92a2a")
        layout.addWidget(self.problem)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
        self.new.clicked.connect(lambda: self.open_editor(None))
        self.edit.clicked.connect(lambda: self.open_editor(self.chosen()))
        self.remove.clicked.connect(self.delete_chosen)
        self.table.doubleClicked.connect(lambda _i: self.open_editor(self.chosen()))
        self.refresh()

    @property
    def wb(self):
        return self.tables.item.sheet.workbook

    def key(self):
        """Whose names are listed: a Book.id, TABLES or VARIABLES."""
        which = self.whose.currentData() if hasattr(self, "whose") else None
        return which if which is not None else TABLES

    def names(self) -> list:
        key, wb = self.key(), self.wb
        if key == VARIABLES:
            chosen = [dn for dn in wb.names.values() if dn.variable]
        else:
            chosen = []
            for dn in wb.names.values():
                if dn.variable:
                    # a CalcForge variable named on this workbook's cells
                    home = _home(wb, dn)
                    mine = (home.book if home is not None else None) or TABLES
                    if home is not None and mine == key:
                        chosen.append(dn)
                elif whose(wb, dn) == key:
                    chosen.append(dn)
        return sorted(chosen, key=lambda dn: (dn.name.lower(), dn.sheet or 0))

    def refresh(self) -> None:
        names = self.names()
        self.table.setRowCount(len(names))
        for i, dn in enumerate(names):
            scope = "CalcForge variable" if dn.variable and self.key() != VARIABLES \
                else scope_in_list(self.wb, dn)
            for j, text in enumerate((dn.name, name_value(self.wb, dn), "=" + dn.refers_to,
                                      scope, dn.comment)):
                self.table.setItem(i, j, QTableWidgetItem(text))
        self.table.resizeColumnsToContents()
        self.edit.setEnabled(bool(names))
        self.remove.setEnabled(bool(names))

    def chosen(self):
        names = self.names()
        row = self.table.currentRow()
        return names[row] if 0 <= row < len(names) else None

    def open_editor(self, dn) -> None:
        if dn is None and self.sender() is self.edit:
            return
        t, l, b, r = self.tables.selection()
        here = _absolute(self.tables.item.name, t, l, b, r)
        key = self.key()
        if dn is not None and dn.variable:
            key = VARIABLES                         # its scope is the document's
        dialog = NameDialog(self.wb, self, dn, here, key)
        window = self.tables.view.window
        if not getattr(window, "interactive_prompts", True):
            window._last_name_dialog = dialog
            return
        if dialog.exec() == QDialog.Accepted:
            self.apply_editor(dialog, dn)
        from .release import done_with
        done_with(dialog)

    def apply_editor(self, dialog: NameDialog, dn=None) -> Optional[str]:
        name, refers, scope, comment = dialog.values()
        key = self.key()
        # a new name is the listed workbook's: kept with the open sheet when
        # it is one of that workbook's, else with the workbook's first sheet
        sheets = sheets_of(self.wb, key)
        open_sheet = self.tables.item.sheet
        home = open_sheet if open_sheet in sheets or not sheets else sheets[0]
        variable = None if dn is not None else key == VARIABLES
        problem = define(self.tables, name, refers, scope, comment, replacing=dn,
                         variable=variable, home=home)
        self.problem.setText(problem or "")
        self.refresh()
        return problem

    def delete_chosen(self) -> None:
        dn = self.chosen()
        if dn is None:
            return
        problem = delete(self.tables, dn)
        self.problem.setText(problem or "")
        self.refresh()


def name_manager(tables, key=None) -> None:
    """The Name Manager (Ctrl+F3), on the open sheet's workbook (or *key*'s)."""
    if tables.item is None:
        return
    dialog = NameManagerDialog(tables, tables.view, key)
    window = tables.view.window
    if not getattr(window, "interactive_prompts", True):
        window._last_data_dialog = dialog
        return
    dialog.exec()
    from .release import done_with
    done_with(dialog)


# -- the Name Box ---------------------------------------------------------------------------------
def go_to_name(tables, text: str) -> bool:
    """The Name Box: a defined name selects its cells (opening its table);
    a new name names the selection (Excel). True when it was a name."""
    from ..sheet import formula as F
    from ..sheet.evaluate import Ctx, RefValue, ev
    from ..sheet.refs import is_cell_name
    from ..sheet.workbook import defined_name_problem

    item = tables.item
    if item is None or not text or is_cell_name(text.replace("$", "")):
        return False
    wb = item.sheet.workbook
    dn = wb.find_name(text, item.sheet)
    if dn is not None:
        try:
            got = ev(F.parse(dn.refers_to).tree, Ctx(wb, item.sheet, 0, 0))
        except Exception:  # noqa: BLE001
            got = None
        if isinstance(got, RefValue):
            target = next((t for t in tables._all_tables() if t.sheet is got.sheet), None)
            if target is not None and target is not item:
                tables.open(target, (got.top, got.left))
            tables.select((got.top, got.left), (got.bottom, got.right), (got.top, got.left))
            tables.view.setFocus()
        return True
    if defined_name_problem(text) is None:
        t, l, b, r = tables.selection()
        problem = define(tables, text, _absolute(item.name, t, l, b, r))
        if problem:
            tables.view.statusMessage.emit(problem)
        tables.view.setFocus()
        return True
    return False


def in_reach(sheet, dn) -> bool:
    """Whether a formula on *sheet* reads *dn* by its name alone, or the
    Name Box there goes to it: the sheet's own names, its workbook's, the
    CalcForge variables — not another workbook's (its own) nor another
    sheet's."""
    if dn.sheet is not None:
        return dn.sheet == sheet.id
    if dn.variable:
        return True
    if dn.book is not None:
        return dn.book == sheet.book
    return sheet.book is None


def names_menu(tables, menu) -> None:
    """The Name Box's drop-down: the names of the open sheet's workbook (and
    its own), to go to — as Excel's lists the workbook's."""
    item = tables.item
    if item is None:
        return
    names = sorted((dn for dn in item.sheet.workbook.names.values() if in_reach(item.sheet, dn)),
                   key=lambda dn: dn.name.lower())
    if not names:
        action = menu.addAction("(no names yet)")
        action.setEnabled(False)
    for dn in names:
        menu.addAction(dn.name, lambda n=dn.name: go_to_name(tables, n))

