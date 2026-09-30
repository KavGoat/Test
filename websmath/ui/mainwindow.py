"""Main window: menus, toolbox, the worksheet view."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QIcon, QKeySequence
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QDockWidget, QFileDialog, QFormLayout, QFrame,
                               QGridLayout, QHBoxLayout, QInputDialog, QLabel, QListWidget, QMainWindow, QMdiArea,
                               QMessageBox, QPushButton, QScrollArea, QSpinBox, QToolButton, QVBoxLayout,
                               QWidget)

from ..engine.catalog import FUNCTIONS, UNIT_CATALOG
from ..engine.model import Matrix
from ..io.smfile import load_sm, save_sm
from ..worksheet import Worksheet
from .worksheet_view import WorksheetView


ICONS = Path(__file__).with_name("icons") / "desktop"


def icon(name: str) -> QIcon:
    return QIcon(str(ICONS / f"{name}.png"))


class _Header(QFrame):
    """Blue gradient bar with the section title and a [+]/[-] box."""

    def __init__(self, title: str, on_click):
        super().__init__()
        self.setObjectName("hdr")
        self.setStyleSheet("#hdr{border:1px solid #8db2e3;background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                           "stop:0 #e3efff,stop:0.5 #c4ddff,stop:1 #adcfff);}"
                           "QLabel{background:transparent;border:0;}")
        self.setFixedHeight(18)
        self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 0, 3, 0)
        self.label = QLabel(title)
        self.label.setStyleSheet("font-weight:bold;color:#15428b;font-family:'Tahoma','Segoe UI';font-size:11px;")
        self.box = QLabel("−")
        self.box.setAlignment(Qt.AlignCenter)
        self.box.setFixedSize(11, 11)
        self.box.setStyleSheet("QLabel{border:1px solid #6f8fbf;background:#ffffff;color:#15428b;"
                               "font-size:10px;font-weight:bold;}")
        lay.addWidget(self.label)
        lay.addStretch(1)
        lay.addWidget(self.box)
        self._click = on_click

    def mousePressEvent(self, e) -> None:
        self._click()


class PanelSection(QWidget):
    """One section of the desktop side panel: a blue header with the title
    and a [+]/[-] box that folds the buttons away."""

    def __init__(self, title: str, buttons: list, cols: int = 6, collapsed: bool = False,
                 wide: bool = False, extra: Optional[QWidget] = None):
        super().__init__()
        self.title = title
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 1)
        lay.setSpacing(0)
        self.header = _Header(title, self.toggle)
        lay.addWidget(self.header)
        self.body = QWidget()
        self.body.setStyleSheet("QWidget{background:#ffffff;}"
                                "QToolButton{border:1px solid transparent;background:transparent;"
                                "color:#000000;font-size:13px;padding:0;}"
                                "QToolButton:hover{border:1px solid #316ac5;background:#c1d2ee;}"
                                "QToolButton:pressed{background:#98b5e2;}"
                                "QToolButton:disabled{color:#a0a0a0;}")
        g = QGridLayout(self.body)
        g.setContentsMargins(2, 2, 2, 2)
        g.setSpacing(1)
        g.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.buttons = []
        for k, entry in enumerate(buttons):
            label, action, tip = entry[0], entry[1], entry[2]
            b = QToolButton()
            b.setText(label)
            b.setToolTip(tip)
            b.setFocusPolicy(Qt.NoFocus)
            b.setMinimumSize(QSize(23, 21))
            b.setFixedHeight(21)
            if action is None:
                b.setEnabled(False)
            else:
                b.clicked.connect(action)
            g.addWidget(b, k // cols, k % cols)
            self.buttons.append(b)
        if extra is not None:
            g.addWidget(extra, (len(buttons) + cols - 1) // cols, 0, 1, cols)
        lay.addWidget(self.body)
        self.set_collapsed(collapsed)

    def set_collapsed(self, on: bool) -> None:
        self._collapsed = on
        self.body.setVisible(not on)
        self.header.box.setText("+" if on else "−")

    def toggle(self) -> None:
        self.set_collapsed(not self._collapsed)


class SidePanel(QScrollArea):
    """The desktop's right-hand side panel (View > Show/hide side panel)."""

    def __init__(self, sections: list):
        super().__init__()
        inner = QWidget()
        inner.setStyleSheet("background:#ffffff;")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.sections = sections
        for sec in sections:
            lay.addWidget(sec)
        lay.addStretch(1)
        self.setWidget(inner)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFixedWidth(172)
        self.setFrameShape(QFrame.StyledPanel)


class MainWindow(QMainWindow):
    """SMath Studio desktop's window: menus (File, Edit, View, Insert,
    Calculation, Tools, Pages, Help), the icon toolbar, worksheets as pages
    in one window, the side panel on the right and the status bar."""

    def __init__(self, path: Optional[str] = None):
        super().__init__()
        self.setWindowIcon(QIcon(str(ICONS / "smath.ico")))
        self.mdi = QMdiArea()
        self.mdi.setViewMode(QMdiArea.SubWindowView)
        self.mdi.setBackground(QColor("#ababab"))
        self.mdi.subWindowActivated.connect(self._activated)
        self.setCentralWidget(self.mdi)
        self._pages = 0
        self._build_status()
        self.new_page()
        self._menus()
        self._toolbar()
        self._side_panel()
        self.resize(1200, 820)
        if path:
            self.open_path(path)

    # -- documents (the Pages menu) -----------------------------------------------------------
    @property
    def view(self) -> WorksheetView:
        sub = self.mdi.activeSubWindow() or (self.mdi.subWindowList() or [None])[-1]
        return sub.widget() if sub is not None else self.new_page()

    def new_page(self, worksheet: Optional[Worksheet] = None) -> WorksheetView:
        self._pages += 1
        v = WorksheetView(worksheet or Worksheet())
        v.path = None
        v.page_name = f"Page{self._pages}"
        v.modified.connect(lambda v=v: self._mark_modified(v))
        v.status.connect(lambda text, v=v: self._status_text(text, v))
        v.pages_changed.connect(lambda cur, n, v=v: self._page_label(cur, n, v))
        v.zoom_changed.connect(lambda z, v=v: self._zoom_shown(z, v))
        v.checked.connect(lambda rep, v=v: self._check_shown(rep, v))
        sub = self.mdi.addSubWindow(v)
        sub.setWindowIcon(icon("document"))
        sub.setAttribute(Qt.WA_DeleteOnClose)
        self._set_sub_title(v)
        sub.showMaximized()
        self.mdi.setActiveSubWindow(sub)
        if worksheet is not None:
            v.reload()
        v._grow_scene()
        return v

    def _set_sub_title(self, v) -> None:
        name = v.path.name if v.path else v.page_name
        v.parentWidget().setWindowTitle(f"{name}[*]")
        v.parentWidget().setWindowModified(getattr(v, "dirty", False))
        self._title()

    def _mark_modified(self, v) -> None:
        v.dirty = True
        self._set_sub_title(v)

    def _activated(self, sub) -> None:
        if sub is None:
            return
        v = sub.widget()
        self._title()
        self._page_label(v.page_at_view(), v.scene_.page_count(), v)
        self._zoom_shown(v.zoom, v)
        if hasattr(self, "_mode_actions"):
            for key, a in self._mode_actions.items():
                a.setChecked(v.scene_.page_mode == key)

    def close_page(self) -> None:
        sub = self.mdi.activeSubWindow()
        if sub is not None:
            sub.close()
        if not self.mdi.subWindowList():
            self.new_page()

    def _fill_pages_menu(self) -> None:
        m = self._pages_menu
        m.clear()
        self._act(m, "New Worksheet", lambda: self.new_page(), "Ctrl+N", icon_name="filenew")
        self._act(m, "Close", self.close_page, "Ctrl+F4", icon_name="close")
        m.addSeparator()
        for k, sub in enumerate(self.mdi.subWindowList()):
            v = sub.widget()
            a = m.addAction(f"&{k + 1} {v.path.name if v.path else v.page_name}")
            a.setCheckable(True)
            a.setChecked(sub is self.mdi.activeSubWindow())
            a.triggered.connect(lambda _=False, s=sub: self.mdi.setActiveSubWindow(s))

    # -- menus ------------------------------------------------------------------------------
    def _act(self, menu, text, slot, shortcut=None, checkable=False, checked=False, icon_name=None,
             enabled=True):
        a = QAction(text, self)
        if icon_name:
            a.setIcon(icon(icon_name))
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.setCheckable(checkable)
        if checkable:
            a.setChecked(checked)
            a.toggled.connect(slot)
        else:
            a.triggered.connect(slot)
        a.setEnabled(enabled)
        menu.addAction(a)
        return a

    def _v(self, name: str, *args):
        """A slot that calls a method of the active worksheet view."""
        return lambda *_: getattr(self.view, name)(*args)

    def _menus(self) -> None:
        """Menus of SMath Studio desktop."""
        mb = self.menuBar()
        f = mb.addMenu("&File")
        self._act(f, "New", lambda: self.new_page(), "Ctrl+N", icon_name="filenew")
        self._act(f, "Open...", self.open, "Ctrl+O", icon_name="fileopen")
        self._recent_menu = f.addMenu("Recent Files")
        self._recent_menu.aboutToShow.connect(self._fill_recent)
        f.addSeparator()
        self._act(f, "Save", self.save, "Ctrl+S", icon_name="filesave")
        self._act(f, "Save as...", self.save_as, "Ctrl+Shift+S", icon_name="filesaveas")
        exp = f.addMenu("Export")
        self._act(exp, "PDF document...", self.export_pdf)
        f.addSeparator()
        self._act(f, "Print Preview", self.print_preview)
        self._act(f, "Print...", self.print_sheet, "Ctrl+P", icon_name="fileprint")
        f.addSeparator()
        self._act(f, "Properties...", self.properties)
        f.addSeparator()
        self._act(f, "Exit", self.close, "Alt+F4", icon_name="exit")

        e = mb.addMenu("&Edit")
        self._act(e, "Undo", self._v("undo"), "Ctrl+Z", icon_name="undo")
        self._act(e, "Redo", self._v("redo"), "Ctrl+Y", icon_name="redo")
        e.addSeparator()
        self._act(e, "Cut", self._v("cut"), "Ctrl+X", icon_name="editcut")
        self._act(e, "Copy", self._v("copy"), "Ctrl+C", icon_name="editcopy")
        self._act(e, "Paste", self._v("paste"), "Ctrl+V", icon_name="editpaste")
        self._act(e, "Delete", self._v("delete_selection"), "Del")
        e.addSeparator()
        self._act(e, "Select all", self._v("select_all"), "Ctrl+A")
        e.addSeparator()
        self._act(e, "Align horizontally", lambda: self._align("h"), icon_name="alignh")
        self._act(e, "Align vertically", lambda: self._align("v"), icon_name="alignv")

        vm = mb.addMenu("&View")
        self._act(vm, "Grid", self._toggle_grid, checkable=True, checked=True)
        self._act(vm, "Dynamic assistance", self._toggle_assist, checkable=True, checked=True)
        self._panel_action = self._act(vm, "Show/hide side panel", self._toggle_panel, "F2",
                                       checkable=True, checked=True, icon_name="sidepanel")
        self._act(vm, "Fullscreen", self._fullscreen, "F11", checkable=True)
        vm.addSeparator()
        self._mode_actions = {}
        group = QActionGroup(self)
        for key, title, ic in (("pages", "Pages", "view_pages"), ("bounds", "Printing bounds", "view_bounds"),
                               ("none", "None", "view_none")):
            a = self._act(vm, title, lambda on, k=key: on and self._page_mode(k), checkable=True,
                          checked=key == "pages", icon_name=ic)
            group.addAction(a)
            self._mode_actions[key] = a
        vm.addSeparator()
        zm = vm.addMenu("Zoom")
        zm.setIcon(icon("viewmag"))
        for z in (50, 75, 100, 125, 150, 200):
            self._act(zm, f"{z}%", lambda _=False, z=z: self.view.set_zoom(z / 100))
        self._act(zm, "Zoom in", lambda: self.view.set_zoom(self.view.zoom * 1.1), "Ctrl++", icon_name="viewmagMore")
        self._act(zm, "Zoom out", lambda: self.view.set_zoom(self.view.zoom / 1.1), "Ctrl+-", icon_name="viewmagLess")

        i = mb.addMenu("&Insert")
        self._act(i, "Matrix...", self._insert_matrix, "Ctrl+M")
        self._act(i, "Function...", self._insert_function, "Ctrl+E", icon_name="funct")
        self._act(i, "Unit...", self._insert_unit, "Ctrl+W", icon_name="funnel1")
        self._act(i, "Constants...", self._show_constants, "Ctrl+K", icon_name="handbook")
        i.addSeparator()
        pl = i.addMenu("Plot")
        self._act(pl, "2D", self._insert_plot, "@")
        i.addSeparator()
        self._act(i, "Text region", self._insert_text, '"')
        self._act(i, "Area", self._insert_area)
        self._act(i, "Separator", self._insert_separator)

        c = mb.addMenu("&Calculation")
        self._act(c, "Solve", self._v("solve_selection"))
        self._act(c, "Calculate", self._v("calculate_selection"))
        self._act(c, "Differentiate", self._v("differentiate_selection"))
        self._act(c, "Invert", self._v("invert_selection"))
        self._act(c, "Determinant", self._v("determinant_selection"))
        c.addSeparator()
        self._act(c, "Disable evaluation", self._disable_evaluation)
        c.addSeparator()
        self._act(c, "Auto calculation", self._toggle_auto, checkable=True, checked=True)
        self._act(c, "Recalculate page", lambda: self.view.recalculate(force=True), "F9", icon_name="reload")
        self._act(c, "Interrupt processing", lambda: None, "Pause", icon_name="stop", enabled=False)

        t = mb.addMenu("&Tools")
        self._act(t, "Double-check results...", self.double_check, "Ctrl+Shift+D")
        self._act(t, "Automatic double-check", self._toggle_check, checkable=True, checked=True)
        t.addSeparator()
        self._act(t, "Options...", self.options, icon_name="configure")

        self._pages_menu = mb.addMenu("&Pages")
        self._pages_menu.aboutToShow.connect(self._fill_pages_menu)
        self._fill_pages_menu()

        h = mb.addMenu("&Help")
        self._act(h, "Contents", self._help, "F1", icon_name="handbook")
        h.addSeparator()
        self._act(h, "About WebSMath", self._about, icon_name="info")

    def _toolbar(self) -> None:
        """The desktop toolbar, with SMath Studio's own icons."""
        from PySide6.QtWidgets import QComboBox

        tb = self.addToolBar("Standard")
        tb.setMovable(False)
        tb.setIconSize(QSize(16, 16))
        tb.setStyleSheet("QToolBar{spacing:1px;padding:1px;}")

        def btn(ic, tip, slot, enabled=True):
            a = QAction(icon(ic), tip, self)
            a.triggered.connect(slot)
            a.setEnabled(enabled)
            tb.addAction(a)
            return a

        btn("filenew", "New (Ctrl+N)", lambda: self.new_page())
        btn("fileopen", "Open (Ctrl+O)", self.open)
        btn("filesave", "Save (Ctrl+S)", self.save)
        btn("fileprint", "Print (Ctrl+P)", self.print_sheet)
        tb.addSeparator()
        btn("editcut", "Cut (Ctrl+X)", self._v("cut"))
        btn("editcopy", "Copy (Ctrl+C)", self._v("copy"))
        btn("editpaste", "Paste (Ctrl+V)", self._v("paste"))
        tb.addSeparator()
        btn("undo", "Undo (Ctrl+Z)", self._v("undo"))
        btn("redo", "Redo (Ctrl+Y)", self._v("redo"))
        tb.addSeparator()
        from PySide6.QtWidgets import QFontComboBox

        fam = QFontComboBox()
        fam.setCurrentFont(QFont("Arial"))
        fam.setFixedWidth(150)
        fam.setFocusPolicy(Qt.ClickFocus)
        fam.activated.connect(lambda _: self.view.format_selection(font_family=fam.currentFont().family()))
        tb.addWidget(fam)
        self._family_box = fam
        size = QComboBox()
        size.setEditable(True)
        size.addItems(["7", "8", "9", "10", "11", "12", "14", "16", "18", "20", "22", "24", "26", "28", "36", "48", "72"])
        size.setCurrentText("10")
        size.setFixedWidth(52)
        size.setFocusPolicy(Qt.ClickFocus)
        size.activated.connect(lambda _: self.view.format_selection(font_size=float(size.currentText())))
        tb.addWidget(size)
        self._size_box = size
        btn("bold", "Bold (Ctrl+B)", lambda: self.view.format_selection(toggle="bold"))
        btn("italic", "Italic (Ctrl+I)", lambda: self.view.format_selection(toggle="italic"))
        btn("underline", "Underline (Ctrl+U)", lambda: self.view.format_selection(toggle="underline"))
        tb.addSeparator()
        btn("textcolor", "Text color", lambda: self._pick_color("color"))
        btn("bgcolor", "Background color", lambda: self._pick_color("bg_color"))
        btn("borderoutline", "Border on/off", lambda: self.view.format_selection(toggle="border"))
        tb.addSeparator()
        btn("alignh", "Align horizontally", lambda: self._align("h"))
        btn("alignv", "Align vertically", lambda: self._align("v"))
        tb.addSeparator()
        btn("funct", "Insert function (Ctrl+E)", self._insert_function)
        btn("funnel1", "Insert unit (Ctrl+W)", self._insert_unit)
        btn("handbook", "Constants (Ctrl+K)", self._show_constants)
        tb.addSeparator()
        btn("reload", "Recalculate page (F9)", lambda: self.view.recalculate(force=True))
        btn("stop", "Interrupt processing", lambda: None, enabled=False)
        tb.addSeparator()
        self._panel_btn = btn("sidepanel", "Show/hide side panel (F2)", lambda: self._panel_action.toggle())
        tb.addSeparator()
        # the desktop's debugger buttons (not replicated)
        btn("pause", "Break", lambda: None, enabled=False)
        btn("next", "Continue", lambda: None, enabled=False)
        btn("step_into", "Step into", lambda: None, enabled=False)
        # bold / italic / underline shortcuts, as SMath (no toolbar buttons)
        for key, attr in (("Ctrl+B", "bold"), ("Ctrl+I", "italic"), ("Ctrl+U", "underline")):
            a = QAction(self)
            a.setShortcut(QKeySequence(key))
            a.triggered.connect(lambda _=False, attr=attr: self.view.format_selection(toggle=attr))
            self.addAction(a)

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

    # -- status bar ----------------------------------------------------------------------------
    def _build_status(self) -> None:
        from PySide6.QtWidgets import QComboBox

        sb = self.statusBar()
        self._page_lbl = QLabel("Page 1 of 1")
        self._page_lbl.setMinimumWidth(90)
        self._state_lbl = QLabel("Ready")
        sb.addWidget(self._page_lbl)
        sb.addWidget(self._state_lbl, 1)
        self._check_lbl = QLabel("")
        self._check_lbl.setToolTip("Every result is recalculated independently after each change "
                                   "(Tools > Double-check results)")
        sb.addWidget(self._check_lbl)
        mode = QToolButton()
        mode.setIcon(icon("view_pages"))
        mode.setAutoRaise(True)
        mode.setPopupMode(QToolButton.InstantPopup)
        mode.setToolTip("Page view")
        self._mode_btn = mode
        sb.addPermanentWidget(mode)
        mag = QLabel()
        mag.setPixmap(icon("viewmag").pixmap(16, 16))
        sb.addPermanentWidget(mag)
        zoom = QComboBox()
        zoom.setEditable(True)
        zoom.addItems(["50%", "75%", "100%", "125%", "150%", "200%", "300%", "400%"])
        zoom.setCurrentText("100%")
        zoom.setFixedWidth(68)
        zoom.setFocusPolicy(Qt.ClickFocus)
        zoom.activated.connect(lambda _: self._zoom_from_box())
        zoom.lineEdit().returnPressed.connect(self._zoom_from_box)
        self._zoom_box = zoom
        sb.addPermanentWidget(zoom)

    def _zoom_from_box(self) -> None:
        try:
            z = float(self._zoom_box.currentText().strip().rstrip("%")) / 100
        except ValueError:
            return
        self.view.set_zoom(z)

    def _zoom_shown(self, z: float, v=None) -> None:
        if v is None or v is self.view:
            self._zoom_box.setCurrentText(f"{round(z * 100)}%")

    def _page_label(self, cur: int, n: int, v=None) -> None:
        if v is None or v is self.view:
            self._page_lbl.setText(f"Page {min(cur, n)} of {n}")

    def _status_text(self, text: str, v=None) -> None:
        self._state_lbl.setText(text or "Ready")

    def _check_shown(self, rep, v=None) -> None:
        if v is not None and v is not self.view:
            return
        self._check_lbl.setText(("✔ " if rep.ok else "⚠ ") + rep.summary())
        self._check_lbl.setStyleSheet("color:#207020;" if rep.ok else "color:#c05000;font-weight:bold;")

    def _toggle_check(self, on: bool) -> None:
        for sub in self.mdi.subWindowList():
            sub.widget().double_check_enabled = on
        if not on:
            self._check_lbl.setText("")

    def double_check(self) -> None:
        """Tools > Double-check results: recalculate everything independently
        and list any result that disagrees."""
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

        rep = self.view.run_double_check()
        if rep is None:
            return
        d = QDialog(self)
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
        self._check_dialog = d
        d.exec()

    # -- side panel ------------------------------------------------------------------------------
    def _side_panel(self) -> None:
        typed = lambda s: (lambda: self._type(s))
        struct = lambda n: (lambda: self._program(n))
        secs = [
            PanelSection("Arithmetic", [
                ("∞", typed("∞"), "Positive infinity"), ("π", typed("π"), "Number 'Pi'"),
                ("i", typed("i"), "Imaginary unit"), ("±", typed("±"), "Plus/minus"),
                ("xₙ", typed("["), "Vector element ([)"), ("←", lambda: self._named("BACK"), "Backspace"),
                ("7", typed("7"), "7"), ("8", typed("8"), "8"), ("9", typed("9"), "9"),
                ("+", typed("+"), "Addition (+)"), ("( )", typed("("), "Brackets"),
                ("xʸ", typed("^"), "Power (^)"),
                ("4", typed("4"), "4"), ("5", typed("5"), "5"), ("6", typed("6"), "6"),
                ("−", typed("-"), "Subtraction (-)"), ("√", typed("\\"), "Square root (\\)"),
                ("ⁿ√", struct("nthroot"), "N-th root (Ctrl+\\)"),
                ("1", typed("1"), "1"), ("2", typed("2"), "2"), ("3", typed("3"), "3"),
                ("×", typed("*"), "Multiplication (*)"), (",", typed(","), "Arguments separator"),
                ("→", None, "Symbolic evaluation (not available)"),
                (".", typed("."), "Decimal symbol"), ("0", typed("0"), "0"), ("!", typed("!"), "Factorial (!)"),
                ("/", typed("/"), "Division (/)"), ("≔", typed(":"), "Definition (:)"),
                ("=", typed("="), "Numeric evaluation (=)"),
            ]),
            PanelSection("Matrices", [
                ("[⋮]", self._insert_matrix, "Insert matrix (Ctrl+M)"), ("|M|", typed("det("), "Determinant"),
                ("Mᵀ", typed("transpose("), "Matrix transpose (Ctrl+1)"),
                ("Aᵢⱼ", typed("alg("), "Algebraic addition to matrix"), ("Mᵢⱼ", typed("minor("), "Minor"),
                ("×", typed("†"), "Cross product (Ctrl+8)"),
                ("v⃗", typed("vectorize("), "Vectorize"), ("a..b", struct("range"), "Range"),
                ("a,b..", struct("range3"), "Range with step"), ("vᵢ", typed("["), "Element (Ctrl+[)"),
                ("M⁻¹", typed("invert("), "Inverse"), ("tr", typed("tr("), "Trace"),
            ]),
            PanelSection("Boolean", [
                ("=", typed("≡"), "Boolean equality (Ctrl+=)"), ("<", typed("<"), "Less than"),
                (">", typed(">"), "Greater than"), ("≤", typed("≤"), "Less than or equal (Ctrl+9)"),
                ("≥", typed("≥"), "Greater than or equal (Ctrl+0)"), ("≠", typed("≠"), "Not equal (Ctrl+3)"),
                ("¬", typed("¬"), "Not"), ("∧", typed("&"), "And (&)"), ("∨", typed("|"), "Or (|)"),
                ("⊕", typed("⊕"), "Exclusive or"),
            ]),
            PanelSection("Functions", [
                ("log", typed("log("), "Logarithm"), ("sign", typed("sign("), "Sign"),
                ("sin", typed("sin("), "Sine"), ("cos", typed("cos("), "Cosine"),
                ("Σ", struct("sum"), "Summation"), ("Π", struct("product"), "Product"),
                ("ln", typed("ln("), "Natural logarithm"), ("arg", typed("arg("), "Argument"),
                ("tan", typed("tan("), "Tangent"), ("cot", typed("cot("), "Cotangent"),
                ("∫", struct("int"), "Definite integral"), ("d/dx", struct("diff"), "Derivative"),
                ("exp", typed("exp("), "Exponent"), ("{", struct("sys"), "System"),
            ], cols=6),
            PanelSection("Plot", [
                ("2D", self._insert_plot, "Plot - 2D (@)"), ("✥", lambda: self._plot_tool("move"), "Move"),
                ("⤢", lambda: self._plot_tool("scale"), "Scale"), ("⁘", lambda: self._plot_render(True), "Points"),
                ("∿", lambda: self._plot_render(False), "Lines"),
                ("⟳", lambda: self.view.recalculate(force=True), "Refresh"),
            ], collapsed=True),
            PanelSection("Programming", [
                ("if", struct("if"), "If"), ("for", struct("for"), "For loop"),
                ("try", struct("try"), "Try/on error"), ("line", struct("line"), "Add line (])"),
                ("while", struct("while"), "While loop"), ("cont.", typed("continue"), "continue"),
                ("break", typed("break"), "break"),
            ], cols=4),
            PanelSection("Constants", [
                ("g", typed("'g.e"), "'g.e - gravitational acceleration"), ("c", typed("'c"), "'c - speed of light"),
                ("h", typed("'h"), "'h - Planck constant"), ("k", typed("'k"), "'k - Boltzmann constant"),
                ("Nᴀ", typed("'N.A"), "'N.A - Avogadro's number"), ("R", typed("'R.m"), "'R.m - gas constant"),
                ("ε₀", typed("'ε.0"), "'ε.0 - vacuum permittivity"), ("μ₀", typed("'μ.0"), "'μ.0 - magnetic constant"),
                ("e⁻", typed("'e"), "'e - elementary charge"), ("mₑ", typed("'m.e"), "'m.e - electron mass"),
                ("mₚ", typed("'m.p"), "'m.p - proton mass"), ("u", typed("'u"), "'u - atomic mass unit"),
            ], extra=self._constants_button()),
        ]
        self.panel = SidePanel(secs)
        dock = QDockWidget("", self)
        dock.setTitleBarWidget(QWidget())
        dock.setWidget(self.panel)
        dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self._dock = dock

    def _constants_button(self) -> QWidget:
        b = QPushButton("Table of all constants...")
        b.setFocusPolicy(Qt.NoFocus)
        b.clicked.connect(self._show_constants)
        return b

    def _toggle_panel(self, on: bool) -> None:
        self._dock.setVisible(on)

    def _fullscreen(self, on: bool) -> None:
        self.showFullScreen() if on else self.showNormal()

    def _page_mode(self, mode: str) -> None:
        self.view.set_page_mode(mode)
        self._mode_btn.setIcon(icon({"pages": "view_pages", "bounds": "view_bounds", "none": "view_none"}[mode]))

    def _align(self, how: str) -> None:
        """Edit > Align: line up the selected regions on the first one's left
        edge (vertically) or top (horizontally)."""
        v = self.view
        items = sorted(v.selected, key=lambda it: (it.region.y, it.region.x))
        if len(items) < 2:
            return
        first = items[0]
        for it in items[1:]:
            if how == "v":
                it.region.x = first.region.x
            else:
                it.region.y = first.region.y
            v.place(it)
        v.worksheet.invalidate_order()
        v.recalculate()
        v.modified.emit()

    def _disable_evaluation(self) -> None:
        v = self.view
        items = list(v.selected) or ([v.focused_item] if v.focused_item else [])
        for it in items:
            it.region.enabled = not it.region.enabled
            v.worksheet.update_after_edit(it.region)
        v.refresh()
        v.modified.emit()

    def _help(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(__file__).parents[1] / "README.md")))

    def options(self) -> None:
        """Tools > Options: the worksheet's calculation settings and the
        interface (as the desktop's two tabs)."""
        from PySide6.QtWidgets import QCheckBox, QComboBox, QTabWidget

        v = self.view
        f = v.worksheet.format
        d = QDialog(self)
        d.setWindowTitle("Options")
        lay = QVBoxLayout(d)
        tabs = QTabWidget()
        calc = QWidget()
        form = QFormLayout(calc)
        dec, thr = QSpinBox(), QSpinBox()
        dec.setRange(0, 15)
        dec.setValue(f.decimals)
        thr.setRange(1, 15)
        thr.setValue(f.threshold)
        sig, tz = QCheckBox(), QCheckBox()
        sig.setChecked(f.significant)
        tz.setChecked(f.trailing_zeros)
        frac = QComboBox()
        frac.addItems(["Decimal", "Fraction", "Auto"])
        frac.setCurrentIndex(["decimal", "fraction", "auto"].index(f.fractions))
        rnd = QComboBox()
        rnd.addItems(["Half to even", "Away from zero"])
        rnd.setCurrentIndex(0 if f.half_even else 1)
        auto = QCheckBox()
        auto.setChecked(v.worksheet.auto_calculation)
        eng = QCheckBox()
        eng.setChecked(f.engineering)
        eng.setToolTip("kN, kPa/MPa, kN/m, kN·m, mm⁴ chosen by size (off: SMath's N, Pa, J, m⁴)")
        form.addRow("Decimal places", dec)
        form.addRow("Significant figures mode", sig)
        form.addRow("Trailing zeros", tz)
        form.addRow("Exponential threshold", thr)
        form.addRow("Fractions", frac)
        form.addRow("Rounding", rnd)
        form.addRow("Auto calculation", auto)
        form.addRow("Engineering units", eng)
        tabs.addTab(calc, "Calculation")
        ui = QWidget()
        form2 = QFormLayout(ui)
        fs = QSpinBox()
        fs.setRange(6, 72)
        fs.setValue(10)
        grid = QCheckBox()
        grid.setChecked(v.scene_.show_grid)
        assist = QCheckBox()
        assist.setChecked(v.dynamic_assistance)
        form2.addRow("Font size (new regions)", fs)
        form2.addRow("Grid", grid)
        form2.addRow("Dynamic assistance", assist)
        tabs.addTab(ui, "Interface")
        lay.addWidget(tabs)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        lay.addWidget(bb)
        self._options_dialog = d
        if d.exec() != QDialog.Accepted:
            return
        f.decimals, f.threshold = dec.value(), thr.value()
        f.significant, f.trailing_zeros = sig.isChecked(), tz.isChecked()
        f.fractions = ["decimal", "fraction", "auto"][frac.currentIndex()]
        f.half_even = rnd.currentIndex() == 0
        f.engineering = eng.isChecked()
        v.worksheet.auto_calculation = auto.isChecked()
        v.scene_.show_grid = grid.isChecked()
        v.dynamic_assistance = assist.isChecked()
        v.default_font_size = float(fs.value())
        v.recalculate(force=True)
        v.scene_.update()

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
    @property
    def path(self) -> Optional[Path]:
        return self.view.path

    def _title(self) -> None:
        sub = self.mdi.activeSubWindow() if hasattr(self, "mdi") else None
        name = ""
        if sub is not None:
            v = sub.widget()
            name = f" - [{v.path.name if v.path else v.page_name}{'*' if getattr(v, 'dirty', False) else ''}]"
        self.setWindowTitle("WebSMath")  # Qt adds " - [page]" for the maximized page

    def new(self) -> None:
        self.new_page()

    def open(self) -> None:
        fn, _ = QFileDialog.getOpenFileName(self, "Open", "", "SMath worksheets (*.sm);;All files (*)")
        if fn:
            self.open_path(fn)

    def open_path(self, fn: str) -> None:
        ws = load_sm(fn)
        cur = self.mdi.activeSubWindow()
        v = cur.widget() if cur is not None else None
        # an untouched empty page is replaced, as the desktop does
        if v is not None and not v.worksheet.regions and v.path is None and not getattr(v, "dirty", False):
            v.worksheet = ws
            v.scene_.worksheet = ws
            v.reload()
        else:
            v = self.new_page(ws)
        v.path = Path(fn)
        v.dirty = False
        self._set_sub_title(v)
        self._remember(fn)

    def save(self) -> None:
        v = self.view
        if v.path is None:
            self.save_as()
            return
        save_sm(v.worksheet, v.path)
        v.dirty = False
        self._set_sub_title(v)

    def save_as(self) -> None:
        fn, _ = QFileDialog.getSaveFileName(self, "Save as", "", "SMath worksheets (*.sm)")
        if fn:
            if not fn.endswith(".sm"):
                fn += ".sm"
            self.view.path = Path(fn)
            self.save()
            self._remember(fn)

    def _remember(self, fn: str) -> None:
        from PySide6.QtCore import QSettings

        st = QSettings("WebSMath", "WebSMath")
        files = [f for f in (st.value("recent") or []) if f != fn]
        st.setValue("recent", [fn] + files[:9])

    def _fill_recent(self) -> None:
        from PySide6.QtCore import QSettings

        m = self._recent_menu
        m.clear()
        files = QSettings("WebSMath", "WebSMath").value("recent") or []
        if not files:
            a = m.addAction("No Files")
            a.setEnabled(False)
        for k, fn in enumerate(files):
            m.addAction(f"&{k + 1} {fn}").triggered.connect(lambda _=False, fn=fn: self.open_path(fn))

    def print_preview(self) -> None:
        from PySide6.QtPrintSupport import QPrintPreviewDialog, QPrinter

        printer = QPrinter(QPrinter.HighResolution)
        dlg = QPrintPreviewDialog(printer, self)
        dlg.paintRequested.connect(self.view.render_pages)
        dlg.exec()

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
            self._mark_modified(self.view)

    def _delete_selected(self) -> None:
        for it in list(self.view.selected):
            self.view.delete_region(it)
        self.view.selected = []
        self.view.recalculate()

    def _toggle_grid(self, on: bool) -> None:
        for sub in self.mdi.subWindowList():
            sub.widget().scene_.show_grid = on
            sub.widget().scene_.update()

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
        QMessageBox.about(self, "About WebSMath",
                          "WebSMath - a Python replica of SMath Studio (desktop layout, SMath Cloud behaviour).")

    def closeEvent(self, e) -> None:
        e.accept()
