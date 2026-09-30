"""SMath's small dialogs: insert matrix, insert function, constants,
double-check — WebSMath's own (its ui/mainwindow.py), unchanged apart from
being functions of a parent window rather than methods of WebSMath's.

Each hands back what was chosen; the caller types it into the equation.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QHeaderView, QLabel,
                               QListWidget, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout)

# Set by tests to answer a dialog without showing it: {dialog name: answer}.
ANSWERS: dict = {}


def pick(parent, title: str, entries: list) -> Optional[str]:
    """A list to choose one from (Insert > Function)."""
    if title in ANSWERS:
        return ANSWERS[title]
    d = QDialog(parent)
    d.setWindowTitle(title)
    lay = QVBoxLayout(d)
    lst = QListWidget()
    for label, desc in entries:
        lst.addItem(label)
        lst.item(lst.count() - 1).setToolTip(desc)
    lay.addWidget(lst)
    info = QLabel()
    info.setWordWrap(True)
    lst.currentRowChanged.connect(lambda r: info.setText(entries[r][1] if r >= 0 else ""))
    lay.addWidget(info)
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    lst.itemDoubleClicked.connect(lambda _: d.accept())
    lay.addWidget(bb)
    d.resize(420, 480)
    if d.exec() != QDialog.Accepted or lst.currentRow() < 0:
        return None
    return entries[lst.currentRow()][0]


def function_to_insert(parent) -> Optional[str]:
    from ..calc.engine.catalog import FUNCTIONS
    entries = sorted({(n, d) for n, _, _, d in FUNCTIONS}, key=lambda x: x[0].lower())
    return pick(parent, "Insert function", entries)


def matrix_size(parent) -> Optional[tuple]:
    """Rows and columns for Insert > Matrix (3 × 3 to begin with)."""
    if "Insert matrix" in ANSWERS:
        return ANSWERS["Insert matrix"]
    d = QDialog(parent)
    d.setWindowTitle("Insert matrix")
    form = QFormLayout(d)
    rows, cols = QSpinBox(), QSpinBox()
    for s in (rows, cols):
        s.setRange(1, 100)
        s.setValue(3)
    form.addRow("Rows", rows)
    form.addRow("Columns", cols)
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    form.addRow(bb)
    if d.exec() != QDialog.Accepted:
        return None
    return rows.value(), cols.value()


def constant_to_insert(parent) -> Optional[str]:
    """Table of every constant SMath defines; double-click inserts one."""
    from ..calc.engine.constants import constants

    if "Constants" in ANSWERS:
        return ANSWERS["Constants"]
    rows = constants()
    chosen = []
    d = QDialog(parent)
    d.setWindowTitle("Constants")
    lay = QVBoxLayout(d)
    lay.addWidget(QLabel("Built-in operands are typed as shown; physical constants are typed "
                         "with an apostrophe, like units ('g.e). Double-click to insert."))
    t = QTableWidget(len(rows), 5)
    t.setHorizontalHeaderLabels(["Type", "Symbol", "Value", "Unit", "Description"])
    for k, c in enumerate(rows):
        for j, text in enumerate((c.typed, c.symbol, c.value, c.unit, c.description)):
            cell = QTableWidgetItem(text)
            cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
            t.setItem(k, j, cell)
    t.verticalHeader().hide()
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(True)
    t.setSelectionBehavior(QTableWidget.SelectRows)
    t.cellDoubleClicked.connect(lambda r, _c: (chosen.append(rows[r].typed), d.accept()))
    lay.addWidget(t)
    box = QDialogButtonBox(QDialogButtonBox.Close)
    box.rejected.connect(d.reject)
    lay.addWidget(box)
    d.resize(760, 560)
    d.exec()
    return chosen[0] if chosen else None


def show_double_check(parent, rep) -> None:
    """Tools > Double-check results: what the independent recalculation found."""
    if "Double-check" in ANSWERS:
        ANSWERS["Double-check"] = rep
        return
    d = QDialog(parent)
    d.setWindowTitle("Double-check")
    lay = QVBoxLayout(d)
    lay.addWidget(QLabel(
        rep.summary() + "\n\nEvery result was recalculated independently (exact fractions, separate unit "
        "arithmetic) and the shown number and unit were read back. Results using programs, matrices "
        "or solvers are not checked."))
    if rep.mismatches:
        t = QTableWidget(len(rep.mismatches), 3)
        t.setHorizontalHeaderLabels(["Region", "Double-check", "Shown"])
        for k, (r, what, exp, got) in enumerate(rep.mismatches):
            for j, text in enumerate((r.editor.root.text(), str(getattr(exp, "x", exp)), str(got))):
                t.setItem(k, j, QTableWidgetItem(text))
        lay.addWidget(t)
    bb = QDialogButtonBox(QDialogButtonBox.Close)
    bb.rejected.connect(d.reject)
    lay.addWidget(bb)
    d.exec()


def operator_to_insert(parent):
    """Insert > Operator: WebSMath's tree of operators by group; Insert (or a
    double-click) says which. Returns what to type, or ("struct", name)."""
    from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

    from .calcedit import OPERATORS

    if "Insert operator" in ANSWERS:
        return ANSWERS["Insert operator"]
    d = QDialog(parent)
    d.setWindowTitle("Insert Operator")
    d.resize(360, 420)
    lay = QVBoxLayout(d)
    tree = QTreeWidget()
    tree.setHeaderLabels(["Operator", "Description"])
    groups = {}
    for g, sym, desc, how in OPERATORS:
        node = groups.get(g)
        if node is None:
            node = groups[g] = QTreeWidgetItem(tree, [g])
            node.setExpanded(True)
        leaf = QTreeWidgetItem(node, [sym, desc])
        leaf.setData(0, Qt.UserRole, how)
    tree.resizeColumnToContents(0)
    lay.addWidget(tree)
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.button(QDialogButtonBox.Ok).setText("Insert")
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    lay.addWidget(bb)
    tree.itemDoubleClicked.connect(lambda it, _c: it.data(0, Qt.UserRole) and d.accept())
    if d.exec() == QDialog.Accepted and tree.currentItem() is not None:
        return tree.currentItem().data(0, Qt.UserRole)
    return None
