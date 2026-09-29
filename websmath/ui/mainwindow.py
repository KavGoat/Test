"""Main window: menus, toolbox, the worksheet view."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QDockWidget, QFileDialog, QFormLayout,
                               QGridLayout, QInputDialog, QLabel, QListWidget, QMainWindow,
                               QMessageBox, QPushButton, QSpinBox, QToolBox, QVBoxLayout, QWidget)

from ..engine.catalog import FUNCTIONS, UNIT_CATALOG
from ..engine.model import Matrix, Program, Row
from ..io.smfile import load_sm, save_sm
from ..worksheet import Worksheet
from .worksheet_view import WorksheetView


class MainWindow(QMainWindow):
    def __init__(self, path: Optional[str] = None):
        super().__init__()
        self.path: Optional[Path] = None
        self.view = WorksheetView(Worksheet())
        self.setCentralWidget(self.view)
        self.view.modified.connect(lambda: self.setWindowModified(True))
        self._menus()
        self._toolbox()
        self.resize(1200, 800)
        self._title()
        if path:
            self.open_path(path)

    # -- menus ------------------------------------------------------------------------
    def _act(self, menu, text, slot, shortcut=None, checkable=False, checked=False):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.setCheckable(checkable)
        if checkable:
            a.setChecked(checked)
            a.toggled.connect(slot)
        else:
            a.triggered.connect(slot)
        menu.addAction(a)
        return a

    def _menus(self) -> None:
        mb = self.menuBar()
        f = mb.addMenu("File")
        self._act(f, "New", self.new, "Ctrl+N")
        self._act(f, "Open...", self.open, "Ctrl+O")
        self._act(f, "Save", self.save, "Ctrl+S")
        self._act(f, "Save as...", self.save_as, "Ctrl+Shift+S")
        f.addSeparator()
        self._act(f, "Exit", self.close)
        e = mb.addMenu("Edit")
        self._act(e, "Undo", self.view.undo)
        self._act(e, "Redo", self.view.redo)
        e.addSeparator()
        self._act(e, "Select all", self.view.select_all)
        self._act(e, "Delete regions", self._delete_selected)
        v = mb.addMenu("View")
        self._act(v, "Grid", self._toggle_grid, checkable=True, checked=True)
        i = mb.addMenu("Insert")
        self._act(i, "Text region", self._insert_text, '"')
        self._act(i, "Matrix...", self._insert_matrix, "Ctrl+M")
        self._act(i, "Function...", self._insert_function, "Ctrl+E")
        self._act(i, "Unit...", self._insert_unit, "Ctrl+U")
        c = mb.addMenu("Calculation")
        self._act(c, "Recalculate", lambda: self.view.recalculate(force=True), "F9")
        self._act(c, "Auto calculation", self._toggle_auto, checkable=True, checked=True)
        c.addSeparator()
        self._act(c, "Decimal places...", self._decimals)
        self._act(c, "Exponential threshold...", self._threshold)
        self._act(c, "Significant figures mode", self._sigfig, checkable=True, checked=False)
        self._act(c, "Trailing zeros", self._trailing, checkable=True, checked=False)
        h = mb.addMenu("Help")
        self._act(h, "About WebSMath", self._about)

    def _toolbox(self) -> None:
        dock = QDockWidget("Toolbox", self)
        box = QToolBox()

        def pad(buttons, cols=5):
            w = QWidget()
            g = QGridLayout(w)
            g.setSpacing(2)
            for k, (label, action) in enumerate(buttons):
                b = QPushButton(label)
                b.setFixedSize(34, 22)
                b.setFocusPolicy(Qt.NoFocus)
                b.clicked.connect(action)
                g.addWidget(b, k // cols, k % cols)
            return w

        typed = lambda s: (lambda: self._type(s))
        box.addItem(pad([(s, typed(s)) for s in ["7", "8", "9", "+", "π", "4", "5", "6", "-", "∞",
                                                  "1", "2", "3", "*", "i", "0", ".", "!", "/", "^",
                                                  ":", "=", "(", "|", "\\"]]), "Arithmetic")
        box.addItem(pad([(s, typed(s)) for s in ["≡", "≠", "<", ">", "≤", "≥", "¬", "∧", "∨", "⊕"]]),
                    "Boolean")
        box.addItem(pad([("if", lambda: self._program("if")), ("for", lambda: self._program("for")),
                         ("while", lambda: self._program("while")), ("line", lambda: self._program("line")),
                         ("try", typed("try(")), ("break", typed("break")),
                         ("continue", typed("continue"))], 4), "Programming")
        box.addItem(pad([(s, typed(s + "(")) for s in ["sin", "cos", "tan", "cot", "ln", "log", "exp",
                                                        "sqrt", "abs", "max", "min", "sum", "det",
                                                        "transpose", "el"]], 4), "Functions")
        box.addItem(pad([(g, typed(g)) for g in "αβγδεζηθικλμνξοπρστυφχψω"], 6), "Symbols (α-ω)")
        box.setFixedWidth(6 * 36 + 12)
        dock.setWidget(box)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetClosable)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def _type(self, s: str) -> None:
        self.view.setFocus()
        self.view._key_to_region(s)

    def _program(self, name: str) -> None:
        """Insert a programming block from the toolbox (for/while/line/if)."""
        v = self.view
        item = v.focused_item
        if item is None:
            item = v.new_region(v.scene_.cross.x(), v.scene_.cross.y())
            v.focus_item(item)
        ed = item.editor
        ed._push_undo()
        if name == "for":
            box = Program("for", Row(), Row(), Row())
        elif name == "while":
            box = Program("while", Row(), Row())
        elif name == "if":
            box = Program("if", Row(), Row(), Row())
        else:
            box = Program("line", Row(), Row())
        ed._insert_box(box, into=0)
        v._after_edit(item)
        v.setFocus()

    # -- file ------------------------------------------------------------------------------
    def _title(self) -> None:
        name = self.path.name if self.path else "Worksheet1"
        self.setWindowTitle(f"{name}[*] - WebSMath")

    def new(self) -> None:
        self.view.worksheet = Worksheet()
        self.view.scene_.worksheet = self.view.worksheet
        self.view.reload()
        self.path = None
        self._title()

    def open(self) -> None:
        fn, _ = QFileDialog.getOpenFileName(self, "Open", "", "SMath worksheets (*.sm);;All files (*)")
        if fn:
            self.open_path(fn)

    def open_path(self, fn: str) -> None:
        ws = load_sm(fn)
        self.view.worksheet = ws
        self.view.scene_.worksheet = ws
        self.view.reload()
        self.path = Path(fn)
        self._title()
        self.setWindowModified(False)

    def save(self) -> None:
        if self.path is None:
            self.save_as()
            return
        save_sm(self.view.worksheet, self.path)
        self.setWindowModified(False)

    def save_as(self) -> None:
        fn, _ = QFileDialog.getSaveFileName(self, "Save as", "", "SMath worksheets (*.sm)")
        if fn:
            if not fn.endswith(".sm"):
                fn += ".sm"
            self.path = Path(fn)
            self.save()
            self._title()

    # -- commands -------------------------------------------------------------------------------
    def _delete_selected(self) -> None:
        for it in list(self.view.selected):
            self.view.delete_region(it)
        self.view.selected = []
        self.view.recalculate()

    def _toggle_grid(self, on: bool) -> None:
        self.view.scene_.show_grid = on
        self.view.scene_.update()

    def _toggle_auto(self, on: bool) -> None:
        self.view.worksheet.auto_calculation = on
        if on:
            self.view.recalculate()

    def _decimals(self) -> None:
        f = self.view.worksheet.format
        n, ok = QInputDialog.getInt(self, "Decimal places", "Decimal places:", f.decimals, 0, 15)
        if ok:
            f.decimals = n
            self.view.recalculate(force=True)

    def _threshold(self) -> None:
        f = self.view.worksheet.format
        n, ok = QInputDialog.getInt(self, "Exponential threshold", "Exponential threshold:", f.threshold, 1, 15)
        if ok:
            f.threshold = n
            self.view.recalculate(force=True)

    def _sigfig(self, on: bool) -> None:
        self.view.worksheet.format.significant = on
        self.view.recalculate(force=True)

    def _trailing(self, on: bool) -> None:
        self.view.worksheet.format.trailing_zeros = on
        self.view.recalculate(force=True)

    def _insert_text(self) -> None:
        v = self.view
        item = v.new_region(v.scene_.cross.x(), v.scene_.cross.y(), text_region=True)
        v.focus_item(item)

    def _insert_matrix(self) -> None:
        d = QDialog(self)
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
            return
        v = self.view
        item = v.focused_item or v.new_region(v.scene_.cross.x(), v.scene_.cross.y())
        v.focus_item(item)
        item.editor._push_undo()
        item.editor._insert_box(Matrix(rows.value(), cols.value()), into=0)
        v._after_edit(item)

    def _pick(self, title: str, entries: list) -> Optional[str]:
        d = QDialog(self)
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

    def _insert_function(self) -> None:
        entries = sorted({(n, d) for n, _, _, d in FUNCTIONS}, key=lambda x: x[0].lower())
        name = self._pick("Insert function", entries)
        if name:
            self._type(name + "(")

    def _insert_unit(self) -> None:
        entries = sorted(((n, f"{t} ({c})") for n, (c, t) in UNIT_CATALOG.items()), key=lambda x: x[0].lower())
        name = self._pick("Insert unit", entries)
        if name:
            self._type("'" + name)

    def _about(self) -> None:
        QMessageBox.about(self, "WebSMath", "WebSMath - a Python replica of the SMath Studio Cloud worksheet.")

    def closeEvent(self, e) -> None:
        e.accept()
