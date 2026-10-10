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


class _Nothing:
    value = None


# -- New / Edit Name ------------------------------------------------------------------------------
class NameDialog(QDialog):
    """New Name / Edit Name: the name, its scope, a comment, what it refers to."""

    def __init__(self, wb, parent=None, dn=None, refers_to: str = ""):
        super().__init__(parent)
        self.wb = wb
        self.setWindowTitle("Edit Name" if dn is not None else "New Name")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(dn.name if dn is not None else "")
        form.addRow("Name:", self.name)
        self.scope = QComboBox()
        self.scope.addItem("Workbook", None)
        for sheet in wb.sheets:
            self.scope.addItem(sheet.name, sheet.id)
        if dn is not None and dn.sheet is not None:
            self.scope.setCurrentIndex(max(0, self.scope.findData(dn.sheet)))
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
           replacing=None) -> Optional[str]:
    """Define (or redefine) a name as one undo step; the problem, if any."""
    item = tables.item

    def change(wb):
        if replacing is not None:
            old_scope = wb.sheet_by_id(replacing.sheet) if replacing.sheet else None
            wb.remove_name(replacing.name, old_scope)
        wb.define_name(name, refers_to, scope, comment, home=scope or item.sheet)
    return change_names(tables, "Define name", change)


def delete(tables, dn) -> Optional[str]:
    def change(wb):
        wb.remove_name(dn.name, wb.sheet_by_id(dn.sheet) if dn.sheet else None)
    return change_names(tables, "Delete name", change)


# -- the Name Manager -----------------------------------------------------------------------------
class NameManagerDialog(QDialog):
    COLUMNS = ("Name", "Value", "Refers To", "Scope", "Comment")

    def __init__(self, tables, parent=None):
        super().__init__(parent)
        self.tables = tables
        self.setWindowTitle("Name Manager")
        self.resize(720, 360)
        layout = QVBoxLayout(self)
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

    def names(self) -> list:
        return sorted(self.wb.names.values(), key=lambda dn: (dn.name.lower(), dn.sheet or 0))

    def refresh(self) -> None:
        names = self.names()
        self.table.setRowCount(len(names))
        for i, dn in enumerate(names):
            scope = self.wb.sheet_by_id(dn.sheet).name if dn.sheet and self.wb.sheet_by_id(dn.sheet) \
                else "Workbook"
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
        dialog = NameDialog(self.wb, self, dn, here)
        window = self.tables.view.window
        if not getattr(window, "interactive_prompts", True):
            window._last_name_dialog = dialog
            return
        if dialog.exec() == QDialog.Accepted:
            self.apply_editor(dialog, dn)

    def apply_editor(self, dialog: NameDialog, dn=None) -> Optional[str]:
        name, refers, scope, comment = dialog.values()
        problem = define(self.tables, name, refers, scope, comment, replacing=dn)
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


def name_manager(tables) -> None:
    if tables.item is None:
        return
    dialog = NameManagerDialog(tables, tables.view)
    window = tables.view.window
    if not getattr(window, "interactive_prompts", True):
        window._last_data_dialog = dialog
        return
    dialog.exec()


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


def names_menu(tables, menu) -> None:
    """The Name Box's drop-down: every name, to go to."""
    item = tables.item
    if item is None:
        return
    names = sorted(item.sheet.workbook.names.values(), key=lambda dn: dn.name.lower())
    if not names:
        action = menu.addAction("(no names yet)")
        action.setEnabled(False)
    for dn in names:
        menu.addAction(dn.name, lambda n=dn.name: go_to_name(tables, n))

