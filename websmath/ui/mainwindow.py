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
from ..engine.model import Matrix
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
        """Menus as on SMath Cloud (File, Edit, View, Insert, Calculation, Help)."""
        v = self.view
        mb = self.menuBar()
        f = mb.addMenu("File")
        self._act(f, "New Worksheet", self.new, "Ctrl+N")
        self._act(f, "Open...", self.open, "Ctrl+O")
        f.addSeparator()
        self._act(f, "Save", self.save, "Ctrl+S")
        self._act(f, "Save as...", self.save_as, "Ctrl+Shift+S")
        self._act(f, "Download as PDF...", self.export_pdf)
        f.addSeparator()
        self._act(f, "Print", self.print_sheet, "Ctrl+P")
        f.addSeparator()
        self._act(f, "Properties...", self.properties)
        f.addSeparator()
        self._act(f, "Exit", self.close)
        e = mb.addMenu("Edit")
        self._act(e, "Undo", v.undo, "Ctrl+Z")
        self._act(e, "Redo", v.redo, "Ctrl+Y")
        e.addSeparator()
        self._act(e, "Cut", v.cut, "Ctrl+X")
        self._act(e, "Copy", v.copy, "Ctrl+C")
        self._act(e, "Paste", v.paste, "Ctrl+V")
        e.addSeparator()
        self._act(e, "Delete", v.delete_selection)
        e.addSeparator()
        self._act(e, "Select all", v.select_all, "Ctrl+A")
        vm = mb.addMenu("View")
        self._act(vm, "Grid", self._toggle_grid, checkable=True, checked=True)
        vm.addSeparator()
        self._act(vm, "Dynamic assistance", self._toggle_assist, checkable=True, checked=True)
        i = mb.addMenu("Insert")
        self._act(i, "Matrix...", self._insert_matrix, "Ctrl+M")
        self._act(i, "Function...", self._insert_function, "Ctrl+E")
        self._act(i, "Unit...", self._insert_unit, "Ctrl+W")
        self._act(i, "Constants...", self._show_constants)
        i.addSeparator()
        self._act(i, "Plot - 2D", self._insert_plot, "Ctrl+2")
        self._act(i, "Area", self._insert_area)
        self._act(i, "Formula", self._insert_formula)
        self._act(i, "Separator", self._insert_separator)
        self._act(i, "Text region", self._insert_text)
        c = mb.addMenu("Calculation")
        self._act(c, "Solve", v.solve_selection)
        self._act(c, "Calculate", v.calculate_selection)
        self._act(c, "Invert", v.invert_selection)
        self._act(c, "Differentiate", v.differentiate_selection)
        self._act(c, "Determinant", v.determinant_selection)
        c.addSeparator()
        self._act(c, "Auto calculation", self._toggle_auto, checkable=True, checked=True)
        c.addSeparator()
        self._act(c, "Recalculate page", lambda: v.recalculate(force=True), "F9")
        c.addSeparator()
        self._act(c, "Decimal places...", self._decimals)
        self._act(c, "Exponential threshold...", self._threshold)
        self._act(c, "Significant figures mode", self._sigfig, checkable=True, checked=False)
        self._act(c, "Trailing zeros", self._trailing, checkable=True, checked=False)
        h = mb.addMenu("Help")
        self._act(h, "About WebSMath", self._about)
        self._format_toolbar()

    def _format_toolbar(self) -> None:
        """The editor toolbar's format controls: font size, colours, border,
        bold/italic/underline (Ctrl+B/I/U), function and unit dialogs."""
        from PySide6.QtWidgets import QComboBox

        tb = self.addToolBar("Format")
        tb.setMovable(False)
        size = QComboBox()
        size.addItems(["7", "8", "10", "12", "14", "16", "18", "20", "24", "28", "32", "36", "42", "48", "54", "72"])
        size.setCurrentText("10")
        size.setFocusPolicy(Qt.NoFocus)
        size.activated.connect(lambda _: self.view.format_selection(font_size=float(size.currentText())))
        tb.addWidget(size)
        self._size_box = size
        tb.addAction(self._mk("B", lambda: self.view.format_selection(toggle="bold"), "Ctrl+B", "Bold"))
        tb.addAction(self._mk("I", lambda: self.view.format_selection(toggle="italic"), "Ctrl+I", "Italic"))
        tb.addAction(self._mk("U", lambda: self.view.format_selection(toggle="underline"), "Ctrl+U", "Underline"))
        tb.addAction(self._mk("A", lambda: self._pick_color("color"), None, "Text color"))
        tb.addAction(self._mk("▦", lambda: self._pick_color("bg_color"), None, "Background color"))
        tb.addAction(self._mk("□", lambda: self.view.format_selection(toggle="border"), None, "Border on/off"))
        tb.addSeparator()
        tb.addAction(self._mk("fx", self._insert_function, None, "Function"))
        tb.addAction(self._mk("m", self._insert_unit, None, "Unit"))
        tb.addAction(self._mk("⟳", lambda: self.view.recalculate(force=True), None, "Recalculate page"))

    def _mk(self, text, slot, shortcut, tip):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.setToolTip(tip)
        a.triggered.connect(slot)
        return a

    def _pick_color(self, attr: str) -> None:
        from PySide6.QtWidgets import QColorDialog

        c = QColorDialog.getColor(parent=self)
        if c.isValid():
            self.view.format_selection(**{attr: c.name()})

    def _toolbox(self) -> None:
        dock = QDockWidget("Toolbox", self)
        box = QToolBox()

        def pad(buttons, cols=5, tips=False):
            w = QWidget()
            g = QGridLayout(w)
            g.setSpacing(2)
            g.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            for k, entry in enumerate(buttons):
                label, action = entry[0], entry[1]
                b = QPushButton(label)
                if tips:
                    b.setToolTip(entry[2])
                b.setFixedSize(40, 22)
                b.setFocusPolicy(Qt.NoFocus)
                b.clicked.connect(action)
                g.addWidget(b, k // cols, k % cols)
            return w

        typed = lambda s: (lambda: self._type(s))
        struct = lambda n: (lambda: self._program(n))
        # the SMath Cloud toolbox, section by section (tooltips as on the site)
        box.addItem(pad([
            ("∞", typed("∞"), "Positive infinity"), ("±", typed("±"), "Operator 'plus/minus'"),
            ("x²", typed("^"), "Raise to power (^)"), ("⌫", lambda: self._named("BACK"), "Backspace"),
            ("+", typed("+"), "Addition (+)"), ("( )", typed("("), "Parenthesis"),
            ("|x|", typed("abs("), "Absolute value"), ("−", typed("-"), "Subtraction (-)"),
            ("√", typed("\\"), "Square root (\\)"), ("ⁿ√", struct("nthroot"), "Nth root (Ctrl+\\)"),
            ("·", typed("*"), "Multiplication (*)"), ("/", typed("/"), "Division (/)"),
            (":=", typed(":"), "Definition (:)"), ("=", typed("="), "Evaluate numerically ( = )"),
            ("π", typed("π"), "π"), ("i", typed("i"), "Imaginary unit"),
        ], tips=True), "Arithmetic")
        box.addItem(pad([
            ("[ ]", self._insert_matrix, "Matrix (Ctrl+M)"), ("|M|", typed("det("), "Determinant"),
            ("Mᵀ", typed("transpose("), "Matrix transpose (Ctrl+1)"), ("×", typed("†"), "Cross product (Ctrl+8)"),
            ("vec", typed("vectorize("), "Vectorize function"), ("a..b", struct("range"), "Range"),
            ("a,b..", struct("range3"), "Range with second value"), ("v₁", typed("["), "Vector element ([)"),
            ("alg", typed("alg("), "Algebraic addition to matrix"), ("min", typed("minor("), "Minor"),
        ], tips=True), "Matrices")
        box.addItem(pad([
            ("≡", typed("≡"), "Boolean 'equal to' (Ctrl+=)"), ("≠", typed("≠"), "Boolean 'not equal to' (Ctrl+3)"),
            ("<", typed("<"), "Boolean 'less than'"), (">", typed(">"), "Boolean 'greater than'"),
            ("≤", typed("≤"), "Boolean 'less than or equal to' (Ctrl+9)"),
            ("≥", typed("≥"), "Boolean 'greater than or equal to' (Ctrl+0)"),
            ("≈", typed("≈"), "Boolean 'approximately equal'"), ("≉", typed("≉"), "Boolean 'approximately not equal'"),
            ("∧", typed("&"), "Boolean 'and' (&)"), ("∨", typed("|"), "Boolean 'or' (|)"),
            ("¬", typed("¬"), "Boolean 'not'"), ("⊕", typed("⊕"), "Boolean 'exclusive or (xor)'"),
        ], tips=True), "Boolean")
        box.addItem(pad([
            ("log", typed("log(,"), "Logarithm"), ("sign", typed("sign("), "Algebraic sign"),
            ("sin", typed("sin("), "Sine"), ("cos", typed("cos("), "Cosine"),
            ("Σ", struct("sum"), "Summation"), ("Π", struct("product"), "Iterated product"),
            ("ln", typed("ln("), "Natural logarithm"), ("arg", typed("arg("), "Principal argument"),
            ("tan", typed("tan("), "Tangent"), ("cot", typed("cot("), "Cotangent"),
            ("d/dx", struct("diff"), "Derivative"), ("∫", struct("int"), "Definite integral"),
            ("exp", typed("exp("), "Exponent"), ("{", struct("sys"), "System of values or equations"),
        ], cols=4, tips=True), "Functions")
        box.addItem(pad([
            ("2D", self._insert_plot, "Plot - 2D"), ("move", lambda: self._plot_tool("move"), "Move"),
            ("zoom", lambda: self._plot_tool("scale"), "Scale"), ("pts", lambda: self._plot_render(True), "Graph by points"),
            ("lines", lambda: self._plot_render(False), "Graph by lines"),
            ("⟳", lambda: self.view.recalculate(force=True), "Refresh"),
        ], cols=4, tips=True), "Plot")
        box.addItem(pad([
            ("if", struct("if"), "If statement"), ("for", struct("for"), "For loop"),
            ("try", struct("try"), "Try/on error statement"), ("line", struct("line"), "Add line (])"),
            ("while", struct("while"), "While loop"), ("cont", typed("continue"), "continue"),
            ("brk", typed("break"), "break"),
        ], cols=4, tips=True), "Programming")
        box.addItem(pad([(g, typed(g), g) for g in "αβγδεζηθικλμνξοπρστυφχψω"], cols=6, tips=True), "Symbols (α-ω)")
        box.setFixedWidth(5 * 42 + 16)
        dock.setWidget(box)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetClosable)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def _type(self, s: str) -> None:
        self.view.setFocus()
        self.view._key_to_region(s)

    def _program(self, name: str) -> None:
        """Insert a toolbox structure (for(,, while(, sum(,,, ...)."""
        v = self.view
        item = v.focused_item
        if item is None or item.region.kind == "text":
            item = v.new_region(v.scene_.cross.x(), v.scene_.cross.y())
            v.focus_item(item)
        item.editor.insert_structure(name)
        v._after_edit(item)
        v.setFocus()

    def _named(self, key: str) -> None:
        self.view.setFocus()
        self.view._named_key(key)

    def _plot_tool(self, tool: str) -> None:
        self.view.plot_tool = tool

    def _plot_render(self, points: bool) -> None:
        item = self.view.focused_item
        if item is not None and item.region.plot is not None:
            item.region.plot.points = points
            item.relayout()

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
    def _toggle_assist(self, on: bool) -> None:
        self.view.dynamic_assistance = on
        if not on:
            self.view.hide_suggestions()

    def _insert_formula(self) -> None:
        v = self.view
        v.focus_item(None)
        item = v.new_region(v.scene_.cross.x(), v.scene_.cross.y())
        v.focus_item(item)
        v.setFocus()

    def _insert_separator(self) -> None:
        v = self.view
        v.focus_item(None)
        v.insert_separator(v.scene_.cross.y())

    def _insert_area(self) -> None:
        v = self.view
        v.focus_item(None)
        v.insert_area(v.scene_.cross.y())

    def print_sheet(self) -> None:
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter

        printer = QPrinter(QPrinter.HighResolution)
        if QPrintDialog(printer, self).exec() == QDialog.Accepted:
            self.view.render_pages(printer)

    def export_pdf(self) -> None:
        fn, _ = QFileDialog.getSaveFileName(self, "Download as PDF", "", "PDF (*.pdf)")
        if fn:
            from PySide6.QtGui import QPdfWriter

            if not fn.endswith(".pdf"):
                fn += ".pdf"
            self.view.render_pages(QPdfWriter(fn))

    def properties(self) -> None:
        from PySide6.QtWidgets import QLineEdit, QPlainTextEdit

        meta = self.view.worksheet.metadata
        d = QDialog(self)
        d.setWindowTitle("Properties")
        form = QFormLayout(d)
        fields = {}
        for key in ("title", "author", "company", "keywords"):
            w = QLineEdit(meta.get(key, ""))
            form.addRow(key.capitalize(), w)
            fields[key] = w
        desc = QPlainTextEdit(meta.get("description", ""))
        form.addRow("Description", desc)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        form.addRow(bb)
        if d.exec() == QDialog.Accepted:
            for k, w in fields.items():
                meta[k] = w.text()
            meta["description"] = desc.toPlainText()
            self.setWindowModified(True)

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

    def _insert_plot(self) -> None:
        v = self.view
        v.focus_item(None)
        item = v.new_plot(v.scene_.cross.x(), v.scene_.cross.y())
        v.focus_item(item)
        v.setFocus()

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

    def _show_constants(self) -> None:
        """Table of every constant SMath defines; double-click inserts one."""
        from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

        from ..engine.constants import constants

        rows = constants()
        d = QDialog(self)
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
        t.cellDoubleClicked.connect(lambda r, _c: (d.accept(), self._type(rows[r].typed)))
        lay.addWidget(t)
        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.rejected.connect(d.reject)
        lay.addWidget(box)
        d.resize(760, 560)
        self._constants_dialog = d
        d.exec()

    def _about(self) -> None:
        QMessageBox.about(self, "WebSMath", "WebSMath - a Python replica of the SMath Studio Cloud worksheet.")

    def closeEvent(self, e) -> None:
        e.accept()
