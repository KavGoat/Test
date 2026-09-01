"""The CalcForge main window."""
from __future__ import annotations

import json
import os
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (QAction, QActionGroup, QFont, QKeySequence, QUndoStack)
from PySide6.QtPrintSupport import QPrintDialog, QPrintPreviewDialog, QPrinter
from PySide6.QtWidgets import (QApplication, QComboBox, QDockWidget, QDoubleSpinBox,
                               QFileDialog, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QMainWindow, QMenu, QMessageBox,
                               QSpinBox, QStatusBar, QToolBar, QToolButton,
                               QVBoxLayout, QWidget)

from ..core.document import (PT_TO_MM, Document, Page, PageSetup)
from ..core.units import format_quantity
from ..io import export as export_io
from ..io import pdfio
from ..io import project as project_io
from ..items.base import MarkupItem, Style, build_item
from ..items.mathitem import MathItem
from ..items.measure import MeasureItem
from ..items.media import ImageItem
from ..items.shapes import PolyItem, RectItem
from ..items.tableitem import TableItem
from ..items.text import NoteItem, StampItem, TextItem, _TextBase
from . import dialogs
from .commands import DocumentStructureCommand
from .icons import icon
from .panels import (FunctionsPanel, MarkupsPanel, PagesPanel, ProblemsPanel,
                     PropertiesPanel, VariablesPanel)
from .scene import PageScene
from .shortcuts import COMMAND, INSERT, TOOL, ShortcutManager
from .tools import CATEGORIES, TOOL_MAP, TOOLS, tools_in
from .view import PageView
from .widgets import ColorButton

APP_NAME = "CalcForge"
CLIPBOARD_TAG = "application/x-calcforge-items"


def _command_id(method: str) -> str:
    """Binding id for a command method, e.g. split_calculation -> split_lines."""
    return {"recalculate": "recalculate", "fit_page": "fit_page",
            "fit_width": "fit_width", "split_calculation": "split_lines",
            "merge_calculations": "merge_lines", "show_problems": "problems",
            "renumber_counts": "renumber_counts"}.get(method, method)


class MainWindow(QMainWindow):
    """Everything the user sees: canvas, toolbars, panels and menus."""

    def __init__(self):
        super().__init__()
        self.document = Document()
        self.undo_stack = QUndoStack(self)
        self.undo_stack.setUndoLimit(200)
        self.current_index = 0
        self.default_style = Style()
        self.shortcuts = ShortcutManager(self)
        self._clipboard: list[dict] = []
        self._suspend_recalc = False

        self.setWindowTitle(APP_NAME)
        self.resize(1500, 960)
        self.setDockOptions(QMainWindow.AnimatedDocks | QMainWindow.AllowTabbedDocks)

        self.view = PageView(self)
        self._build_central()
        self._build_actions()
        self._build_toolbars()
        self._build_docks()
        self._build_menus()
        self._build_status()
        self._connect()
        self.apply_shortcuts()

        self.new_document(confirm=False)
        QTimer.singleShot(0, self.view.fit_page)

    # ==================================================================
    # construction
    # ==================================================================
    def _build_central(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.formula_bar = QWidget()
        bar = QHBoxLayout(self.formula_bar)
        bar.setContentsMargins(6, 3, 6, 3)
        bar.setSpacing(6)
        self.cell_ref = QLabel("—")
        self.cell_ref.setMinimumWidth(74)
        self.cell_ref.setAlignment(Qt.AlignCenter)
        self.cell_ref.setStyleSheet(
            "border:1px solid #c6ccd6; border-radius:3px; padding:2px 6px; background:#fff;")
        self.formula_edit = QLineEdit()
        self.formula_edit.setPlaceholderText(
            "Type a value, or a formula starting with =  (cells, ranges and your variables all work)")
        font = QFont("Cascadia Mono")
        font.setFamilies(["Cascadia Mono", "Consolas", "DejaVu Sans Mono", "monospace"])
        self.formula_edit.setFont(font)
        self.cell_value = QLabel("")
        self.cell_value.setMinimumWidth(150)
        self.cell_value.setStyleSheet("color:#3c5a86;")
        bar.addWidget(QLabel("Cell"))
        bar.addWidget(self.cell_ref)
        bar.addWidget(QLabel("ƒx"))
        bar.addWidget(self.formula_edit, 1)
        bar.addWidget(self.cell_value)
        self.formula_bar.setVisible(False)
        layout.addWidget(self.formula_bar)
        layout.addWidget(self.view, 1)
        self.setCentralWidget(central)

    def _act(self, key: str, text: str, slot, shortcut: str = "", icon_name: str = "",
             checkable: bool = False, tip: str = "") -> QAction:
        action = QAction(text, self)
        if icon_name:
            action.setIcon(icon(icon_name))
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.setCheckable(checkable)
        action.setToolTip(tip or text)
        action.setStatusTip(tip or text)
        if checkable:
            action.toggled.connect(slot)
        else:
            action.triggered.connect(slot)
        setattr(self, f"act_{key}", action)
        return action

    def _build_actions(self) -> None:
        self._act("new", "New", lambda: self.new_document(), "Ctrl+N", "new")
        self._act("open", "Open…", self.open_document, "Ctrl+O", "open")
        self._act("save", "Save", self.save_document, "Ctrl+S", "save")
        self._act("save_as", "Save as…", self.save_document_as, "Ctrl+Shift+S")
        self._act("insert_pdf", "Insert PDF pages…", self.insert_pdf, "Ctrl+I", "pdf")
        self._act("export_pdf", "Export to PDF…", self.export_pdf, "Ctrl+E", "pdf")
        self._act("export_png", "Export pages as images…", self.export_images)
        self._act("export_markups", "Export markups list…", self.export_markups)
        self._act("export_vars", "Export variables…", self.export_variables)
        self._act("print", "Print…", self.print_document, "Ctrl+P", "print")
        self._act("preview", "Print preview…", self.print_preview)
        self._act("quit", "Exit", self.close, "Ctrl+Q")

        self.act_undo = self.undo_stack.createUndoAction(self, "Undo")
        self.act_undo.setShortcut(QKeySequence.Undo)
        self.act_undo.setIcon(icon("undo"))
        self.act_redo = self.undo_stack.createRedoAction(self, "Redo")
        self.act_redo.setShortcut(QKeySequence.Redo)
        self.act_redo.setIcon(icon("redo"))

        self._act("cut", "Cut", self.cut_selection, "Ctrl+X")
        self._act("copy", "Copy", self.copy_selection, "Ctrl+C")
        self._act("paste", "Paste", self.paste_items, "Ctrl+V")
        self._act("duplicate", "Duplicate", self.duplicate_selection, "Ctrl+D")
        self._act("delete", "Delete", self.delete_selection, "", "delete")
        self._act("select_all", "Select all", self.select_all, "Ctrl+A")
        self._act("lock", "Lock / unlock", self.toggle_lock, "Ctrl+L")
        self._act("front", "Bring to front", lambda: self.reorder("front"), "Ctrl+Shift+]")
        self._act("back", "Send to back", lambda: self.reorder("back"), "Ctrl+Shift+[")
        self._act("forward", "Bring forward", lambda: self.reorder("forward"), "Ctrl+]")
        self._act("backward", "Send backward", lambda: self.reorder("backward"), "Ctrl+[")
        for key, label in (("left", "Align left"), ("hcenter", "Align centres"),
                           ("right", "Align right"), ("top", "Align top"),
                           ("vcenter", "Align middles"), ("bottom", "Align bottom")):
            self._act(f"align_{key}", label, lambda _=False, k=key: self.align_items(k))

        self._act("zoom_in", "Zoom in", self.view.zoom_in, "Ctrl++", "zoom_in")
        self._act("zoom_out", "Zoom out", self.view.zoom_out, "Ctrl+-", "zoom_out")
        self._act("fit_page", "Fit page", self.view.fit_page, "Ctrl+0", "fit")
        self._act("fit_width", "Fit width", self.view.fit_width, "Ctrl+1")
        self._act("zoom_sel", "Zoom to selection", self.view.zoom_to_selection, "Ctrl+2")
        self._act("prev_page", "Previous page", lambda: self.go_to_page(self.current_index - 1),
                  "PgUp")
        self._act("next_page", "Next page", lambda: self.go_to_page(self.current_index + 1),
                  "PgDown")

        self._act("add_page", "Add page", self.add_page)
        self._act("duplicate_page", "Duplicate page", self.duplicate_page)
        self._act("delete_page", "Delete page", self.delete_page)
        self._act("page_setup", "Page setup…", self.page_setup, "Ctrl+Shift+P", "page")
        self._act("scale", "Page scale…", self.calibrate_dialog, "", "calibrate")
        self._act("doc_props", "Document properties…", self.document_properties)

        self._act("grid", "Show grid", self.toggle_grid, "Ctrl+G", checkable=True)
        self._act("snap", "Snap to grid", self.toggle_snap, "", checkable=True)
        self._act("margins", "Show margins", self.toggle_margins, "", checkable=True)
        self.act_margins.setChecked(True)
        self._act("sticky", "Keep the tool active", self.toggle_sticky, "", checkable=True,
                  tip="Stay on the current tool after drawing instead of returning to Select")
        self._act("recalc", "Recalculate", self.recalculate, "F9", "recalc")
        self._act("split_lines", "Split into separate lines", self.split_calculation, "",
                  tip="Turn a multi-line calculation into one movable region per line")
        self._act("merge_lines", "Merge into one block", self.merge_calculations, "",
                  tip="Combine the selected calculations into a single region")

        self._act("shortcuts", "Keyboard shortcuts", self.show_shortcuts, "F1")
        self._act("edit_shortcuts", "Customise shortcuts…", self.edit_shortcuts)
        self._act("problems", "Show problems", self.show_problems)
        self._act("renumber_counts", "Renumber count markers", self.renumber_counts)
        self._act("about", f"About {APP_NAME}", self.show_about)
        self._act("sample", "Load the worked example", self.load_sample)

    def _build_toolbars(self) -> None:
        main_bar = QToolBar("Main")
        main_bar.setObjectName("toolbar_main")
        main_bar.setIconSize(QSize(22, 22))
        for action in (self.act_new, self.act_open, self.act_save, None,
                       self.act_insert_pdf, self.act_export_pdf, self.act_print, None,
                       self.act_undo, self.act_redo, None, self.act_recalc):
            main_bar.addSeparator() if action is None else main_bar.addAction(action)
        self.addToolBar(main_bar)

        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_actions: dict[str, QAction] = {}
        tool_bar = QToolBar("Tools")
        tool_bar.setObjectName("toolbar_tools")
        tool_bar.setIconSize(QSize(22, 22))
        for category in CATEGORIES:
            if category != CATEGORIES[0]:
                tool_bar.addSeparator()
            for tool in tools_in(category):
                action = QAction(icon(tool.icon), tool.label, self)
                action.setCheckable(True)
                action.setToolTip(f"{tool.label}"
                                  + (f"  ({tool.shortcut})" if tool.shortcut else "")
                                  + (f"\n{tool.hint}" if tool.hint else ""))
                if tool.shortcut and len(tool.shortcut) == 1:
                    action.setShortcut(QKeySequence(tool.shortcut))
                action.triggered.connect(lambda _checked=False, key=tool.key:
                                         self.select_tool(key))
                self.tool_group.addAction(action)
                tool_bar.addAction(action)
                self.tool_actions[tool.key] = action
        tool_bar.addSeparator()
        tool_bar.addAction(self.act_sticky)
        self.addToolBar(tool_bar)
        self.addToolBarBreak()

        style_bar = QToolBar("Style")
        style_bar.setObjectName("toolbar_style")
        style_bar.addWidget(QLabel(" Line "))
        self.stroke_button = ColorButton(self.default_style.stroke, True, "Line colour")
        self.stroke_button.colorChanged.connect(self._style_stroke)
        style_bar.addWidget(self.stroke_button)
        style_bar.addWidget(QLabel(" Fill "))
        self.fill_button = ColorButton("", True, "Fill colour")
        self.fill_button.colorChanged.connect(self._style_fill)
        style_bar.addWidget(self.fill_button)
        style_bar.addWidget(QLabel(" Width "))
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(0.0, 40.0)
        self.width_spin.setSingleStep(0.25)
        self.width_spin.setValue(self.default_style.width)
        self.width_spin.setSuffix(" pt")
        self.width_spin.valueChanged.connect(self._style_width)
        style_bar.addWidget(self.width_spin)
        style_bar.addWidget(QLabel(" Dash "))
        self.dash_combo = QComboBox()
        self.dash_combo.addItems(["solid", "dash", "dot", "dashdot", "dashdotdot"])
        self.dash_combo.currentTextChanged.connect(self._style_dash)
        style_bar.addWidget(self.dash_combo)
        style_bar.addWidget(QLabel(" Text "))
        self.font_spin = QDoubleSpinBox()
        self.font_spin.setRange(3.0, 96.0)
        self.font_spin.setValue(self.default_style.font_size)
        self.font_spin.setSuffix(" pt")
        self.font_spin.valueChanged.connect(self._style_font)
        style_bar.addWidget(self.font_spin)
        style_bar.addSeparator()
        self.stamp_combo = QComboBox()
        from ..items.text import STAMP_PRESETS
        self.stamp_combo.addItems(list(STAMP_PRESETS))
        self.stamp_combo.setEditable(True)
        self.stamp_combo.setToolTip("Text used by the stamp tool")
        self.stamp_combo.currentTextChanged.connect(
            lambda text: setattr(self.view, "stamp_text", text))
        style_bar.addWidget(QLabel(" Stamp "))
        style_bar.addWidget(self.stamp_combo)
        count_button = QToolButton()
        count_button.setText("Count subject…")
        count_button.clicked.connect(self.choose_count_subject)
        style_bar.addWidget(count_button)
        self.addToolBar(style_bar)

    def _dock(self, title: str, widget: QWidget, area: Qt.DockWidgetArea,
              name: str) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setWidget(widget)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea |
                             Qt.BottomDockWidgetArea)
        self.addDockWidget(area, dock)
        return dock

    def _build_docks(self) -> None:
        self.pages_panel = PagesPanel(self)
        self.dock_pages = self._dock("Pages", self.pages_panel, Qt.LeftDockWidgetArea,
                                     "dock_pages")
        self.properties_panel = PropertiesPanel(self)
        self.dock_properties = self._dock("Properties", self.properties_panel,
                                          Qt.RightDockWidgetArea, "dock_properties")
        self.variables_panel = VariablesPanel(self)
        self.dock_variables = self._dock("Variables", self.variables_panel,
                                         Qt.RightDockWidgetArea, "dock_variables")
        self.functions_panel = FunctionsPanel()
        self.dock_functions = self._dock("Functions", self.functions_panel,
                                         Qt.RightDockWidgetArea, "dock_functions")
        self.markups_panel = MarkupsPanel(self)
        self.dock_markups = self._dock("Markups", self.markups_panel,
                                       Qt.BottomDockWidgetArea, "dock_markups")
        self.problems_panel = ProblemsPanel(self)
        self.dock_problems = self._dock("Problems", self.problems_panel,
                                        Qt.BottomDockWidgetArea, "dock_problems")
        self.tabifyDockWidget(self.dock_markups, self.dock_problems)
        self.dock_markups.raise_()
        self.tabifyDockWidget(self.dock_variables, self.dock_functions)
        self.dock_variables.raise_()
        self.resizeDocks([self.dock_pages, self.dock_properties], [190, 320], Qt.Horizontal)
        # Without an explicit vertical split the properties form gets squeezed
        # into a couple of rows by whatever is stacked under it.
        self.resizeDocks([self.dock_properties, self.dock_variables], [560, 340], Qt.Vertical)
        self.resizeDocks([self.dock_markups], [190], Qt.Vertical)

    def _build_menus(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("&File")
        for action in (self.act_new, self.act_open, None, self.act_save, self.act_save_as,
                       None, self.act_insert_pdf, None, self.act_export_pdf,
                       self.act_export_png, self.act_export_markups, self.act_export_vars,
                       None, self.act_preview, self.act_print, None, self.act_quit):
            file_menu.addSeparator() if action is None else file_menu.addAction(action)

        edit_menu = bar.addMenu("&Edit")
        for action in (self.act_undo, self.act_redo, None, self.act_cut, self.act_copy,
                       self.act_paste, self.act_duplicate, self.act_delete, None,
                       self.act_select_all, self.act_lock):
            edit_menu.addSeparator() if action is None else edit_menu.addAction(action)
        order_menu = edit_menu.addMenu("Order")
        for action in (self.act_front, self.act_forward, self.act_backward, self.act_back):
            order_menu.addAction(action)
        align_menu = edit_menu.addMenu("Align")
        for key in ("left", "hcenter", "right", "top", "vcenter", "bottom"):
            align_menu.addAction(getattr(self, f"act_align_{key}"))

        view_menu = bar.addMenu("&View")
        for action in (self.act_zoom_in, self.act_zoom_out, self.act_fit_page,
                       self.act_fit_width, self.act_zoom_sel, None, self.act_grid,
                       self.act_snap, self.act_margins, None, self.act_prev_page,
                       self.act_next_page):
            view_menu.addSeparator() if action is None else view_menu.addAction(action)
        panels_menu = view_menu.addMenu("Panels")
        for dock in (self.dock_pages, self.dock_properties, self.dock_variables,
                     self.dock_functions, self.dock_markups, self.dock_problems):
            panels_menu.addAction(dock.toggleViewAction())

        page_menu = bar.addMenu("&Page")
        for action in (self.act_add_page, self.act_duplicate_page, self.act_delete_page,
                       None, self.act_page_setup, self.act_scale, None, self.act_doc_props):
            page_menu.addSeparator() if action is None else page_menu.addAction(action)

        insert_menu = bar.addMenu("&Insert")
        for tool in TOOLS:
            if tool.category in ("Calculate", "Annotate"):
                action = QAction(icon(tool.icon), tool.label, self)
                action.triggered.connect(lambda _c=False, key=tool.key: self.select_tool(key))
                insert_menu.addAction(action)
        insert_menu.addSeparator()
        insert_menu.addAction(self.act_insert_pdf)

        calc_menu = bar.addMenu("&Calculate")
        calc_menu.addAction(self.act_recalc)
        calc_menu.addSeparator()
        calc_menu.addAction(self.act_split_lines)
        calc_menu.addAction(self.act_merge_lines)
        calc_menu.addSeparator()
        calc_menu.addAction(self.act_problems)
        calc_menu.addAction(self.act_renumber_counts)
        calc_menu.addAction(self.act_export_vars)

        help_menu = bar.addMenu("&Help")
        help_menu.addAction(self.act_shortcuts)
        help_menu.addAction(self.act_edit_shortcuts)
        help_menu.addAction(self.act_sample)
        help_menu.addAction(self.act_about)

    def _build_status(self) -> None:
        status = QStatusBar()
        self.setStatusBar(status)
        self.status_hint = QLabel("Ready")
        status.addWidget(self.status_hint, 1)

        self.status_position = QLabel("")
        self.status_position.setMinimumWidth(190)
        status.addPermanentWidget(self.status_position)

        self.status_problems = QToolButton()
        self.status_problems.setAutoRaise(True)
        self.status_problems.setText("No problems")
        self.status_problems.setToolTip("Click to show everything that did not evaluate")
        self.status_problems.clicked.connect(self.show_problems)
        status.addPermanentWidget(self.status_problems)

        self.status_scale = QToolButton()
        self.status_scale.setText("Scale 1:1")
        self.status_scale.setAutoRaise(True)
        self.status_scale.setToolTip("Click to set the page scale")
        self.status_scale.clicked.connect(self.calibrate_dialog)
        status.addPermanentWidget(self.status_scale)

        self.page_spin = QSpinBox()
        self.page_spin.setRange(1, 1)
        self.page_spin.setPrefix("Page ")
        self.page_spin.valueChanged.connect(lambda value: self.go_to_page(value - 1))
        status.addPermanentWidget(self.page_spin)

        self.zoom_combo = QComboBox()
        self.zoom_combo.setEditable(True)
        self.zoom_combo.addItems(["25%", "50%", "75%", "100%", "125%", "150%", "200%",
                                  "400%", "Fit page", "Fit width"])
        self.zoom_combo.setCurrentText("100%")
        self.zoom_combo.activated.connect(self._zoom_chosen)
        status.addPermanentWidget(self.zoom_combo)

    def _connect(self) -> None:
        self.view.statusMessage.connect(self.status_hint.setText)
        self.view.cursorMoved.connect(self._show_position)
        self.view.zoomChanged.connect(self._show_zoom)
        self.view.selectionChanged.connect(self.refresh_selection)
        self.view.toolFinished.connect(self.select_tool)
        self.view.cellChanged.connect(self.refresh_formula_bar)
        self.view.documentEdited.connect(self.mark_modified)
        self.pages_panel.pageSelected.connect(self.go_to_page)
        self.pages_panel.pagesReordered.connect(self.move_page)
        self.markups_panel.markupActivated.connect(self.reveal_markup)
        self.problems_panel.problemActivated.connect(self.reveal_markup)
        self.variables_panel.insertRequested.connect(self.insert_into_math)
        self.functions_panel.insertRequested.connect(self.insert_into_math)
        self.formula_edit.returnPressed.connect(self.commit_formula_bar)
        self.undo_stack.cleanChanged.connect(lambda _clean: self.update_title())

    # ==================================================================
    # document lifecycle
    # ==================================================================
    def new_document(self, confirm: bool = True) -> None:
        if confirm and not self.confirm_discard():
            return
        self.document = Document()
        self.undo_stack.clear()
        self.current_index = 0
        self.rebuild_scenes()
        self.select_tool("select")
        self.view.fit_page()
        self.update_title()

    def rebuild_scenes(self) -> None:
        """(Re)create a scene for every page and show the current one."""
        for page in self.document.pages:
            scene = PageScene(page, self.document)
            page.scene = scene
            scene.load_items(page._pending_items)
            page._pending_items = []
            scene.itemsChanged.connect(self.refresh_lists)
        self.current_index = max(0, min(self.current_index, len(self.document.pages) - 1))
        self.view.setScene(self.document.pages[self.current_index].scene)
        self.recalculate()
        self.page_spin.blockSignals(True)
        self.page_spin.setRange(1, len(self.document.pages))
        self.page_spin.setValue(self.current_index + 1)
        self.page_spin.blockSignals(False)
        self.pages_panel.rebuild(self.document, self.current_index)
        self.refresh_lists()
        self.refresh_scale_label()

    def open_document(self) -> None:
        if not self.confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open document", "", project_io.FILTER)
        if not path:
            return
        try:
            project_io.load_document(self.document, path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Open document", f"Could not open the file:\n{exc}")
            return
        self.undo_stack.clear()
        self.current_index = 0
        self.rebuild_scenes()
        self.view.fit_page()
        self.update_title()

    def save_document(self) -> bool:
        if not self.document.path:
            return self.save_document_as()
        try:
            project_io.save_document(self.document, self.document.path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Save", f"Could not save:\n{exc}")
            return False
        self.undo_stack.setClean()
        self.update_title()
        self.status_hint.setText(f"Saved {self.document.path}")
        return True

    def save_document_as(self) -> bool:
        suggested = self.document.path or f"{self.document.title or 'calculation'}.cfx"
        path, _ = QFileDialog.getSaveFileName(self, "Save document as", suggested,
                                              project_io.FILTER)
        if not path:
            return False
        self.document.path = path
        if self.document.title in ("", "Untitled"):
            self.document.title = project_io.describe(path)
        return self.save_document()

    def confirm_discard(self) -> bool:
        if self.undo_stack.isClean() and not self.document.modified:
            return True
        answer = QMessageBox.question(
            self, APP_NAME, "This document has unsaved changes.\nSave before continuing?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if answer == QMessageBox.Cancel:
            return False
        if answer == QMessageBox.Save:
            return self.save_document()
        return True

    def closeEvent(self, event) -> None:
        if not self.confirm_discard():
            event.ignore()
            return
        self.view.deactivate_table()
        try:
            self.undo_stack.cleanChanged.disconnect()
        except (RuntimeError, TypeError):
            pass
        event.accept()

    def update_title(self) -> None:
        name = os.path.basename(self.document.path) if self.document.path else "Untitled"
        try:
            dirty = "" if self.undo_stack.isClean() else " •"
        except RuntimeError:            # the window is being torn down
            return
        self.setWindowTitle(f"{name}{dirty} — {APP_NAME}")

    def mark_modified(self) -> None:
        self.document.modified = True
        self.refresh_lists()
        self.pages_panel.refresh_current(self.document, self.current_index)

    # ==================================================================
    # pages
    # ==================================================================
    def current_page(self) -> Page:
        return self.document.pages[self.current_index]

    def go_to_page(self, index: int) -> None:
        if not 0 <= index < len(self.document.pages) or index == self.current_index:
            return
        self.view.deactivate_table()
        self.current_index = index
        self.view.setScene(self.document.pages[index].scene)
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(index + 1)
        self.page_spin.blockSignals(False)
        self.pages_panel.list.blockSignals(True)
        self.pages_panel.list.setCurrentRow(index)
        self.pages_panel.list.blockSignals(False)
        self.refresh_scale_label()
        self.refresh_selection()

    def _structure_snapshot(self) -> dict:
        return {"pages": [page.to_dict() for page in self.document.pages],
                "current": self.current_index}

    def _restore_structure(self, snapshot: dict) -> None:
        self.document.pages = [Page.from_dict(entry) for entry in snapshot["pages"]]
        self.current_index = snapshot.get("current", 0)
        self.rebuild_scenes()
        self.update_title()

    def _structural_change(self, description: str, mutate) -> None:
        before = self._structure_snapshot()
        mutate()
        self.rebuild_scenes()
        after = self._structure_snapshot()
        self.undo_stack.push(DocumentStructureCommand(before, after, description,
                                                      self._restore_structure))
        self.mark_modified()

    def add_page(self) -> None:
        target = self.current_index + 1

        def mutate():
            self.document.add_page(target)
            self.current_index = target
        self._structural_change("Add page", mutate)

    def duplicate_page(self) -> None:
        source = self.current_page().to_dict()
        target = self.current_index + 1

        def mutate():
            copy = Page.from_dict(source)
            copy.uid = os.urandom(8).hex()
            self.document.pages.insert(target, copy)
            self.current_index = target
        self._structural_change("Duplicate page", mutate)

    def delete_page(self) -> None:
        if len(self.document.pages) <= 1:
            QMessageBox.information(self, "Delete page", "A document needs at least one page.")
            return
        if QMessageBox.question(self, "Delete page",
                                f"Delete page {self.current_index + 1}?") != QMessageBox.Yes:
            return
        index = self.current_index

        def mutate():
            self.document.remove_page(index)
            self.current_index = max(0, index - 1)
        self._structural_change("Delete page", mutate)

    def move_page(self, source: int, target: int) -> None:
        def mutate():
            self.document.move_page(source, target)
            self.current_index = target
        self._structural_change("Reorder pages", mutate)

    def page_setup(self) -> None:
        dialog = dialogs.PageSetupDialog(self.current_page().setup, self,
                                         len(self.document.pages) > 1)
        if dialog.exec() != dialogs.QDialog.Accepted:
            return
        setup = dialog.result_setup()
        pages = self.document.pages if dialog.apply_all.isChecked() else [self.current_page()]

        def mutate():
            for page in pages:
                page.setup = PageSetup.from_dict(setup.to_dict())
        self._structural_change("Page setup", mutate)
        self.view.fit_page()

    def insert_pdf(self) -> None:
        dialog = dialogs.PdfImportDialog(self, self.current_page().setup)
        if dialog.exec() != dialogs.QDialog.Accepted:
            return
        path, indices, fit, dpi = dialog.selection()
        if not path or not indices:
            QMessageBox.information(self, "Insert PDF", "No pages were selected.")
            return
        target = self.current_index + 1

        def mutate():
            pdfio.import_pages(self.document, path, indices, fit, dpi, at=target)
            self.current_index = target
        try:
            self._structural_change(f"Insert {len(indices)} PDF page(s)", mutate)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Insert PDF", str(exc))
            return
        self.view.fit_page()
        self.status_hint.setText(f"Inserted {len(indices)} page(s) from "
                                 f"{os.path.basename(path)}")

    # ==================================================================
    # scale
    # ==================================================================
    def calibrate_scale(self, measured_pt: float) -> None:
        dialog = dialogs.ScaleDialog(self.current_page().scale, measured_pt, self)
        if dialog.exec() != dialogs.QDialog.Accepted:
            return
        scale = dialog.result_scale()
        if scale is None:
            return
        self.current_page().scale = scale
        self.refresh_scale_label()
        self.current_page().scene.refresh_items()
        self.mark_modified()

    def calibrate_dialog(self) -> None:
        dialog = dialogs.ScaleDialog(self.current_page().scale, None, self)
        if dialog.exec() != dialogs.QDialog.Accepted:
            return
        scale = dialog.result_scale()
        if scale is None:
            return
        self.current_page().scale = scale
        self.refresh_scale_label()
        self.current_page().scene.refresh_items()
        self.mark_modified()

    def set_area_unit(self, unit: str) -> None:
        if unit:
            self.current_page().scale.area_unit = unit
            self.current_page().scene.refresh_items()
            self.mark_modified()

    def refresh_scale_label(self) -> None:
        scale = self.current_page().scale
        self.status_scale.setText(f"Scale {scale.label}")
        self.status_scale.setToolTip(
            f"1 page point = {format_quantity(scale.length_per_pt, 5)}\nClick to change")

    # ==================================================================
    # tools & style
    # ==================================================================
    # ==================================================================
    # keyboard
    # ==================================================================
    COMMAND_ACTIONS = {
        "recalculate": "act_recalc", "fit_page": "act_fit_page",
        "fit_width": "act_fit_width", "split_calculation": "act_split_lines",
        "merge_calculations": "act_merge_lines", "show_problems": "act_problems",
        "renumber_counts": "act_renumber_counts",
    }

    def apply_shortcuts(self) -> None:
        """Push the current bindings onto the actions that can carry them.

        A single printable character is handled by the canvas rather than by a
        QAction, so that typing only does something when the canvas has focus
        and nothing is selected.
        """
        for tool_key, action in self.tool_actions.items():
            sequence = self.shortcuts.sequence(f"tool.{tool_key}")
            action.setShortcut(QKeySequence(sequence) if len(sequence) > 1
                               else QKeySequence())
            tool = TOOL_MAP[tool_key]
            hint = f"  ({sequence})" if sequence else ""
            action.setToolTip(f"{tool.label}{hint}"
                              + (f"\n{tool.hint}" if tool.hint else ""))
        for method, attribute in self.COMMAND_ACTIONS.items():
            action = getattr(self, attribute, None)
            sequence = self.shortcuts.sequence(f"command.{_command_id(method)}")
            if action is not None and sequence:
                action.setShortcut(QKeySequence(sequence))

    def run_typed_binding(self, text: str, modifiers, position: QPointF) -> bool:
        """Act on a bare keystroke over the canvas; False if nothing is bound."""
        binding = self.shortcuts.match_typed(text, modifiers)
        if binding is None:
            return False
        if binding.kind == INSERT:
            self._insert_at(binding.payload, position)
            return True
        if binding.kind == TOOL:
            self.select_tool(binding.payload)
            return True
        if binding.kind == COMMAND:
            method = getattr(self, binding.payload, None)
            if callable(method):
                method()
                return True
        return False

    def edit_shortcuts(self) -> None:
        dialog = dialogs.ShortcutManagerDialog(self.shortcuts, self)
        if dialog.exec() == dialogs.QDialog.Accepted:
            dialog.apply()
            self.shortcuts.save()
            self.apply_shortcuts()
            self.status_hint.setText("Shortcuts updated")

    def renumber_counts(self) -> None:
        """Close the gaps left in each count subject after deletions."""
        from ..items.measure import CountItem
        from .scene import reading_order

        self.view.begin_snapshot()
        counters: dict[str, int] = {}
        for page in self.document.pages:
            if page.scene is None:
                continue
            for item in reading_order(page.scene.markups()):
                if isinstance(item, CountItem):
                    counters[item.subject] = counters.get(item.subject, 0) + 1
                    item.index = counters[item.subject]
                    item.update()
        self.view.commit_snapshot("Renumber counts")
        self.refresh_lists()
        total = sum(counters.values())
        self.status_hint.setText(f"Renumbered {total} count marker(s)")

    def select_tool(self, key: str) -> None:
        self.view.set_tool(key)
        action = self.tool_actions.get(key)
        if action is not None and not action.isChecked():
            action.setChecked(True)

    def toggle_sticky(self, on: bool) -> None:
        self.view.sticky_tool = on

    def _style_stroke(self, colour: str) -> None:
        self.default_style.stroke = colour
        self._push_style(lambda style: setattr(style, "stroke", colour), "Line colour")

    def _style_fill(self, colour: str) -> None:
        self.default_style.fill = colour
        self._push_style(lambda style: setattr(style, "fill", colour), "Fill colour")

    def _style_width(self, value: float) -> None:
        self.default_style.width = value
        self._push_style(lambda style: setattr(style, "width", value), "Line width")

    def _style_dash(self, value: str) -> None:
        self.default_style.line_style = value
        self._push_style(lambda style: setattr(style, "line_style", value), "Line style")

    def _style_font(self, value: float) -> None:
        self.default_style.font_size = value
        self._push_style(lambda style: setattr(style, "font_size", value), "Font size")

    def _push_style(self, mutate, description: str) -> None:
        items = self.selected_items()
        if not items:
            return
        self.view.begin_snapshot()
        for item in items:
            mutate(item.style)
            if hasattr(item, "apply_style"):
                item.apply_style()
            if isinstance(item, MathItem):
                item.relayout()
            item.prepareGeometryChange()
            item.update()
        self.view.commit_snapshot(description)
        self.properties_panel.show_items(items)

    def apply_default_style(self, item: MarkupItem) -> None:
        """Seed a freshly drawn markup from the style toolbar."""
        style = self.default_style
        if isinstance(item, (NoteItem, ImageItem, StampItem, TableItem)):
            return
        if isinstance(item, RectItem) and item.kind in ("highlight", "redact"):
            item.style.opacity = style.opacity
            return
        if isinstance(item, PolyItem) and item.kind == "highlighter":
            if style.stroke:
                item.style.stroke = style.stroke
            return
        if isinstance(item, MathItem):
            item.style.font_size = self.document.settings.math_size
            item.digits = self.document.settings.precision
            item.number_format = self.document.settings.number_format
            return
        if isinstance(item, MeasureItem):
            item.style.width = style.width
            item.style.line_style = style.line_style
            return
        if style.stroke:
            item.style.stroke = style.stroke
        if isinstance(item, _TextBase):
            if style.fill:
                item.style.fill = style.fill
        else:
            item.style.fill = style.fill
        item.style.width = style.width
        item.style.line_style = style.line_style
        item.style.opacity = style.opacity
        item.style.font_size = style.font_size
        if hasattr(item, "apply_style"):
            item.apply_style()

    def choose_count_subject(self) -> None:
        dialog = dialogs.CountSubjectDialog(self.view.count_subject, self.view.count_symbol, self)
        if dialog.exec() == dialogs.QDialog.Accepted:
            self.view.count_subject = dialog.subject.text().strip() or "Count"
            self.view.count_symbol = dialog.symbol.currentText()
            self.select_tool("count")

    # ==================================================================
    # selection & editing
    # ==================================================================
    def selected_items(self) -> list[MarkupItem]:
        scene = self.view.scene()
        if scene is None:
            return []
        return [item for item in scene.selectedItems() if isinstance(item, MarkupItem)]

    def refresh_selection(self) -> None:
        items = self.selected_items()
        self.properties_panel.show_items(items)
        if len(items) == 1:
            self.status_hint.setText(items[0].display_name())

    def delete_selection(self) -> None:
        items = [item for item in self.selected_items() if not item.locked]
        if not items:
            return
        self.view.deactivate_table()
        self.view.begin_snapshot()
        for item in items:
            self.view.scene().remove_markup(item)
        self.recalculate()
        self.view.commit_snapshot("Delete markup")
        self.refresh_selection()

    def copy_selection(self) -> None:
        items = self.selected_items()
        if not items:
            return
        self._clipboard = [item.serialize() for item in items]
        QApplication.clipboard().setText(json.dumps({CLIPBOARD_TAG: self._clipboard}))
        self.status_hint.setText(f"Copied {len(items)} markup(s)")

    def cut_selection(self) -> None:
        self.copy_selection()
        self.delete_selection()

    def paste_items(self) -> None:
        payload = self._clipboard
        text = QApplication.clipboard().text()
        if text.strip().startswith("{"):
            try:
                decoded = json.loads(text)
                if CLIPBOARD_TAG in decoded:
                    payload = decoded[CLIPBOARD_TAG]
            except ValueError:
                pass
        if not payload:
            return
        self.view.begin_snapshot()
        self.view.scene().clearSelection()
        for entry in payload:
            copy = dict(entry)
            copy["uid"] = os.urandom(8).hex()
            copy["x"] = copy.get("x", 0) + 14
            copy["y"] = copy.get("y", 0) + 14
            item = build_item(copy)
            if item is None:
                continue
            if isinstance(item, ImageItem):
                item.load_from_document(self.document)
            self.view.scene().add_markup(item)
            item.setSelected(True)
        self.recalculate()
        self.view.commit_snapshot("Paste")
        self.refresh_selection()

    def duplicate_selection(self) -> None:
        items = self.selected_items()
        if not items:
            return
        self.view.begin_snapshot()
        self.view.scene().clearSelection()
        for item in items:
            copy = item.clone()
            if copy is not None:
                if isinstance(copy, ImageItem):
                    copy.load_from_document(self.document)
                self.view.scene().add_markup(copy)
                copy.setSelected(True)
        self.recalculate()
        self.view.commit_snapshot("Duplicate")
        self.refresh_selection()

    def select_all(self) -> None:
        for item in self.view.scene().markups():
            if self.layer_visible(item.layer):
                item.setSelected(True)
        self.refresh_selection()

    def toggle_lock(self) -> None:
        items = self.selected_items()
        if not items:
            return
        target = not all(item.locked for item in items)
        self.view.begin_snapshot()
        for item in items:
            item.set_locked(target)
        self.view.commit_snapshot("Lock markup")
        self.refresh_selection()

    def reorder(self, mode: str) -> None:
        items = self.selected_items()
        if not items:
            return
        scene = self.view.scene()
        self.view.begin_snapshot()
        others = [i for i in scene.markups() if i not in items]
        if mode == "front":
            top = max((i.zValue() for i in others), default=0.0)
            for offset, item in enumerate(items, start=1):
                item.setZValue(top + offset)
        elif mode == "back":
            bottom = min((i.zValue() for i in others), default=0.0)
            for offset, item in enumerate(items, start=1):
                item.setZValue(bottom - offset)
        else:
            step = 1.5 if mode == "forward" else -1.5
            for item in items:
                item.setZValue(item.zValue() + step)
        self.view.commit_snapshot("Change order")

    def align_items(self, mode: str) -> None:
        items = [i for i in self.selected_items() if not i.locked]
        if len(items) < 2:
            return
        rects = {item: item.sceneBoundingRect() for item in items}
        union = QRectF()
        for rect in rects.values():
            union = rect if union.isNull() else union.united(rect)
        self.view.begin_snapshot()
        for item, rect in rects.items():
            delta = QPointF(0, 0)
            if mode == "left":
                delta.setX(union.left() - rect.left())
            elif mode == "right":
                delta.setX(union.right() - rect.right())
            elif mode == "hcenter":
                delta.setX(union.center().x() - rect.center().x())
            elif mode == "top":
                delta.setY(union.top() - rect.top())
            elif mode == "bottom":
                delta.setY(union.bottom() - rect.bottom())
            elif mode == "vcenter":
                delta.setY(union.center().y() - rect.center().y())
            item.setPos(item.pos() + delta)
        self.view.commit_snapshot("Align markups")

    def reveal_markup(self, page_index: int, uid: str) -> None:
        self.go_to_page(page_index)
        scene = self.view.scene()
        scene.clearSelection()
        for item in scene.markups():
            if item.uid == uid:
                item.setSelected(True)
                self.view.centerOn(item)
                break
        self.refresh_selection()

    def layer_visible(self, name: str) -> bool:
        for layer in self.document.layers:
            if layer.name == name:
                return layer.visible
        return True

    def load_image_into(self, item: ImageItem) -> bool:
        path, _ = QFileDialog.getOpenFileName(
            self, "Insert image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;All files (*)")
        if not path:
            return False
        try:
            with open(path, "rb") as handle:
                data = handle.read()
        except OSError as exc:
            QMessageBox.critical(self, "Insert image", str(exc))
            return False
        suffix = os.path.splitext(path)[1].lstrip(".").lower() or "png"
        item.asset_key = self.document.add_asset(data, suffix)
        item.load_from_document(self.document)
        pixmap = item.pixmap()
        if pixmap is not None and not pixmap.isNull():
            rect = item.local_rect()
            ratio = pixmap.height() / max(pixmap.width(), 1)
            item.set_local_rect(QRectF(0, 0, rect.width(), max(rect.width() * ratio, 10)))
        return True

    def edit_named_cells(self, table: TableItem) -> None:
        dialog = dialogs.NamedCellsDialog(table, self)
        if dialog.exec() != dialogs.QDialog.Accepted:
            return
        self.view.begin_snapshot()
        table.named_cells = dialog.result_names()
        self.recalculate()
        self.view.commit_snapshot("Named cells")

    def insert_into_math(self, text: str) -> None:
        """Drop a variable or function name into whatever is being edited."""
        editing = getattr(self.view, "_editing_item", None)
        if isinstance(editing, MathItem) and editing._editor is not None:
            editing._editor.textCursor().insertText(text)
            return
        if self.view.active_table is not None and self.view._cell_editor is not None:
            self.view._cell_editor.insert(text)
            return
        if self.formula_edit.hasFocus():
            self.formula_edit.insert(text)
            return
        QApplication.clipboard().setText(text)
        self.status_hint.setText(f"“{text}” copied — paste it into a calculation or cell")

    # ==================================================================
    # calculation
    # ==================================================================
    def recalculate(self) -> None:
        if self._suspend_recalc:
            return
        workspace = self.document.workspace
        workspace.clear()
        workspace.begin_pass()
        # One pass, strictly top-left to bottom-right across every page: a value
        # has to be defined above (or to the left of) whatever uses it, so moving
        # a region really does change what resolves — as it does in SMath.
        for page in self.document.pages:
            if page.scene is None:
                continue
            for item in page.scene.ordered_markups():
                item.refresh(workspace, page)
        self.variables_panel.rebuild(workspace)
        self.markups_panel.rebuild(self.document)
        self.refresh_problems()
        if self.view.active_table is not None:
            self.refresh_formula_bar(self.view.active_table)

    def split_calculation(self) -> None:
        """Break each selected multi-line calculation into one region per line."""
        blocks = [i for i in self.selected_items() if isinstance(i, MathItem)]
        if not blocks:
            self.status_hint.setText("Select a calculation to split.")
            return
        self.view.begin_snapshot()
        created = 0
        for block in blocks:
            pieces = block.split_lines()
            if not pieces:
                continue
            self.view.scene().remove_markup(block)
            for piece in pieces:
                self.view.scene().add_markup(piece)
                created += 1
        self.recalculate()
        self.view.commit_snapshot("Split calculation")
        self.status_hint.setText(f"Split into {created} line(s)" if created
                                 else "Nothing to split — already one line each")
        self.refresh_selection()

    def merge_calculations(self) -> None:
        """Join the selected calculations into one region, in reading order."""
        from ..ui.scene import reading_order
        blocks = [i for i in self.selected_items() if isinstance(i, MathItem)]
        if len(blocks) < 2:
            self.status_hint.setText("Select two or more calculations to merge.")
            return
        blocks = reading_order(blocks)
        first = blocks[0]
        merged = MathItem("\n".join(block.source.rstrip() for block in blocks))
        merged.style = first.style.copy()
        merged.digits = first.digits
        merged.number_format = first.number_format
        merged.author = first.author
        merged.layer = first.layer
        merged.setPos(first.pos())
        merged.setZValue(first.zValue())
        self.view.begin_snapshot()
        for block in blocks:
            self.view.scene().remove_markup(block)
        self.view.scene().add_markup(merged)
        self.recalculate()
        self.view.commit_snapshot("Merge calculations")
        self.view.scene().clearSelection()
        merged.setSelected(True)
        self.refresh_selection()

    def refresh_problems(self) -> None:
        from ..core.problems import collect_problems, summarise

        problems = collect_problems(self.document)
        self.problems_panel.rebuild(problems)
        if problems:
            self.status_problems.setText(f"⚠ {len(problems)} problem"
                                         f"{'s' if len(problems) != 1 else ''}")
            self.status_problems.setStyleSheet("color:#b3261e; font-weight:600;")
            self.status_problems.setToolTip(summarise(problems) + "\nClick to show them")
        else:
            self.status_problems.setText("No problems")
            self.status_problems.setStyleSheet("")
            self.status_problems.setToolTip("Everything in the document evaluated")

    def show_problems(self) -> None:
        self.dock_problems.show()
        self.dock_problems.raise_()

    def refresh_lists(self) -> None:
        self.markups_panel.rebuild(self.document)

    # ==================================================================
    # formula bar
    # ==================================================================
    def refresh_formula_bar(self, table: Optional[TableItem]) -> None:
        if table is None:
            self.formula_bar.setVisible(False)
            return
        self.formula_bar.setVisible(True)
        row, col = table.current
        self.cell_ref.setText(table.current_ref())
        if not self.formula_edit.hasFocus():
            self.formula_edit.setText(table.sheet.raw(row, col))
        cell = table.sheet.cells.get((row, col))
        if cell is not None and cell.error:
            self.cell_value.setText(cell.error)
            self.cell_value.setStyleSheet("color:#c92a2a;")
        else:
            self.cell_value.setText(table.sheet.display_text(row, col))
            self.cell_value.setStyleSheet("color:#3c5a86;")

    def commit_formula_bar(self) -> None:
        table = self.view.active_table
        if table is None:
            return
        row, col = table.current
        self.view.begin_snapshot()
        table.set_cell(row, col, self.formula_edit.text())
        self.recalculate()
        self.view.commit_snapshot("Edit cell")
        table.move_current(1, 0)
        self.refresh_formula_bar(table)
        self.view.setFocus()

    # ==================================================================
    # export & print
    # ==================================================================
    def export_pdf(self) -> None:
        suggested = os.path.splitext(self.document.path or self.document.title or "document")[0]
        path, _ = QFileDialog.getSaveFileName(self, "Export to PDF", suggested + ".pdf",
                                              "PDF files (*.pdf)")
        if not path:
            return
        try:
            export_io.export_pdf(self.document, path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Export to PDF", str(exc))
            return
        self.status_hint.setText(f"Exported {path}")

    def export_images(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder for the images")
        if not folder:
            return
        dpi, ok = QInputDialog.getInt(self, "Export images", "Resolution (dpi):", 200, 72, 600)
        if not ok:
            return
        written = export_io.export_images(self.document, folder, dpi,
                                          self.document.title or "page")
        self.status_hint.setText(f"Wrote {len(written)} image(s) to {folder}")

    def export_markups(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export markups", "markups.csv",
                                              "CSV files (*.csv)")
        if not path:
            return
        count = export_io.export_markups_csv(self.document, path)
        self.status_hint.setText(f"Exported {count} markup(s)")

    def export_variables(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export variables", "variables.csv",
                                              "CSV files (*.csv)")
        if not path:
            return
        count = export_io.export_variables_csv(self.document, path)
        self.status_hint.setText(f"Exported {count} variable(s)")

    def _printer(self) -> QPrinter:
        printer = QPrinter(QPrinter.HighResolution)
        printer.setDocName(self.document.title or "CalcForge document")
        return printer

    def print_document(self) -> None:
        printer = self._printer()
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QPrintDialog.Accepted:
            return
        try:
            export_io.print_document(self.document, printer)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Print", str(exc))

    def print_preview(self) -> None:
        printer = self._printer()
        preview = QPrintPreviewDialog(printer, self)
        preview.resize(1000, 800)
        preview.paintRequested.connect(
            lambda device: export_io.print_document(self.document, device))
        preview.exec()

    # ==================================================================
    # view toggles
    # ==================================================================
    def toggle_grid(self, on: bool) -> None:
        self.document.settings.show_grid = on
        self._refresh_all_scenes()

    def toggle_snap(self, on: bool) -> None:
        self.document.settings.snap_to_grid = on

    def toggle_margins(self, on: bool) -> None:
        self.document.settings.show_margins = on
        self._refresh_all_scenes()

    def _refresh_all_scenes(self) -> None:
        for page in self.document.pages:
            if page.scene is not None:
                page.scene.update()

    def _zoom_chosen(self, _index: int) -> None:
        text = self.zoom_combo.currentText().strip().lower()
        if text.startswith("fit page"):
            self.view.fit_page()
        elif text.startswith("fit width"):
            self.view.fit_width()
        else:
            try:
                self.view.set_zoom(float(text.rstrip("%")) / 100.0)
            except ValueError:
                pass

    def _show_zoom(self, factor: float) -> None:
        self.zoom_combo.blockSignals(True)
        self.zoom_combo.setCurrentText(f"{factor * 100:.0f}%")
        self.zoom_combo.blockSignals(False)

    def _show_position(self, point: QPointF) -> None:
        scale = self.current_page().scale
        millimetres = f"{point.x() * PT_TO_MM:.1f}, {point.y() * PT_TO_MM:.1f} mm"
        if scale.is_calibrated():
            real = format_quantity(scale.length(1.0) * 100, 4)
            self.status_position.setText(f"{millimetres}   ·   100 pt = {real}")
        else:
            self.status_position.setText(millimetres)

    # ==================================================================
    # menus & help
    # ==================================================================
    def build_context_menu(self, item, scene_pos: QPointF) -> QMenu:
        menu = QMenu(self)
        if item is not None:
            if isinstance(item, (MathItem, _TextBase)):
                menu.addAction("Edit…", lambda: self.view.begin_item_edit(item))
            if isinstance(item, MathItem):
                if not item.single_line:
                    menu.addAction(self.act_split_lines)
                if len([i for i in self.selected_items() if isinstance(i, MathItem)]) > 1:
                    menu.addAction(self.act_merge_lines)
            if isinstance(item, TableItem):
                menu.addAction("Edit table", lambda: self.view.activate_table(item))
                menu.addAction("Named cells…", lambda: self.edit_named_cells(item))
                menu.addSeparator()
                menu.addAction("Insert row above", lambda: self._table_op(item, "row_above"))
                menu.addAction("Insert row below", lambda: self._table_op(item, "row_below"))
                menu.addAction("Insert column left", lambda: self._table_op(item, "col_left"))
                menu.addAction("Insert column right", lambda: self._table_op(item, "col_right"))
                menu.addAction("Delete row", lambda: self._table_op(item, "del_row"))
                menu.addAction("Delete column", lambda: self._table_op(item, "del_col"))
                menu.addAction("Autofit columns", lambda: self._table_op(item, "autofit"))
            if isinstance(item, MeasureItem):
                menu.addAction("Page scale…", self.calibrate_dialog)
            menu.addSeparator()
            menu.addAction(self.act_cut)
            menu.addAction(self.act_copy)
            menu.addAction(self.act_duplicate)
            menu.addAction(self.act_delete)
            menu.addSeparator()
            order = menu.addMenu("Order")
            for action in (self.act_front, self.act_forward, self.act_backward, self.act_back):
                order.addAction(action)
            if len(self.selected_items()) > 1:
                align = menu.addMenu("Align")
                for key in ("left", "hcenter", "right", "top", "vcenter", "bottom"):
                    align.addAction(getattr(self, f"act_align_{key}"))
            menu.addAction(self.act_lock)
        else:
            menu.addAction(self.act_paste)
            menu.addSeparator()
            insert = menu.addMenu("Insert here")
            for key in ("math", "table", "text", "callout", "stamp", "image"):
                tool = TOOL_MAP[key]
                insert.addAction(icon(tool.icon), tool.label,
                                 lambda _c=False, k=key, p=scene_pos: self._insert_at(k, p))
            menu.addSeparator()
            menu.addAction(self.act_page_setup)
            menu.addAction(self.act_scale)
            menu.addAction(self.act_select_all)
        return menu

    def _insert_at(self, key: str, point: QPointF) -> None:
        tool = TOOL_MAP[key]
        self.view.begin_snapshot()
        item = tool.factory()
        self.apply_default_style(item)
        item.author = self.document.settings.default_author or self.document.author
        width, height = self.view._default_size(item)
        if (hasattr(item, "set_local_rect") and not isinstance(item, (TableItem, MathItem))):
            item.set_local_rect(QRectF(0, 0, width, height))
        if isinstance(item, ImageItem) and not self.load_image_into(item):
            return
        self.view.scene().add_markup(item, point)
        self.view.scene().clearSelection()
        item.setSelected(True)
        self.recalculate()
        self.view.commit_snapshot(f"Add {tool.label.lower()}")
        if isinstance(item, (MathItem, _TextBase)):
            self.view.begin_item_edit(item)
        elif isinstance(item, TableItem):
            self.view.activate_table(item)
        self.refresh_selection()

    def _table_op(self, table: TableItem, operation: str) -> None:
        row, col = table.current
        self.view.begin_snapshot()
        sheet = table.sheet
        if operation == "row_above":
            sheet.insert_rows(row)
        elif operation == "row_below":
            sheet.insert_rows(row + 1)
        elif operation == "col_left":
            sheet.insert_cols(col)
        elif operation == "col_right":
            sheet.insert_cols(col + 1)
        elif operation == "del_row":
            sheet.delete_rows(row)
        elif operation == "del_col":
            sheet.delete_cols(col)
        elif operation == "autofit":
            for index in range(sheet.cols):
                table.autofit_column(index)
        table.current = (min(row, sheet.rows - 1), min(col, sheet.cols - 1))
        table.anchor = table.current
        table.prepareGeometryChange()
        self.recalculate()
        self.view.commit_snapshot("Edit table")

    def document_properties(self) -> None:
        dialog = dialogs.DocumentPropertiesDialog(self.document, self)
        if dialog.exec() == dialogs.QDialog.Accepted:
            dialog.apply()
            self.act_grid.setChecked(self.document.settings.show_grid)
            self.act_snap.setChecked(self.document.settings.snap_to_grid)
            self.act_margins.setChecked(self.document.settings.show_margins)
            self._refresh_all_scenes()
            self.update_title()

    def show_shortcuts(self) -> None:
        dialogs.ShortcutsDialog(self).exec()

    def show_about(self) -> None:
        dialogs.AboutDialog(self).exec()

    def load_sample(self) -> None:
        from ..sample import build_sample
        if not self.confirm_discard():
            return
        self.document = build_sample()
        self.undo_stack.clear()
        self.current_index = 0
        self.rebuild_scenes()
        self.view.fit_page()
        self.update_title()
        self.status_hint.setText("Worked example loaded — edit anything and press F9 to recalculate")
