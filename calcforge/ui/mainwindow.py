"""The CalcForge main window."""
from __future__ import annotations

import base64
import json
import os
from typing import Optional

from PySide6.QtCore import (QBuffer, QEvent, QIODevice, QMimeData, QPointF,
                            QRect, QRectF,
                            QSettings, QSize, Qt, QTimer)
from PySide6.QtGui import (QAction, QActionGroup, QColor, QFont, QImage,
                           QKeySequence, QTransform, QUndoStack)
from PySide6.QtPrintSupport import QPrintDialog, QPrintPreviewDialog, QPrinter
from PySide6.QtWidgets import (QApplication, QComboBox, QDockWidget, QDoubleSpinBox,
                               QFileDialog, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QMainWindow, QMenu, QMessageBox,
                               QSpinBox, QStatusBar, QToolBar, QToolButton,
                               QVBoxLayout, QWidget)

from ..core.document import (LANDSCAPE, MM_TO_PT, PAGE_SIZES, PORTRAIT,
                             PT_TO_MM, Document, Page, PageSetup)
from ..core.engine import name_problem
from ..core.spreadsheet import (MAX_COLS, MAX_ROWS, looks_like_a_grid,
                                parse_clipboard_grid)
from ..core.units import format_quantity, parse_unit
from ..io import export as export_io
from ..io import pdfio
from ..io import project as project_io
from ..items.base import MarkupItem, Style, build_item
from ..items.contents import ContentsItem
from ..items.mathitem import MathItem
from ..items.measure import MeasureItem
from ..items.media import ImageItem
from ..items.plotitem import PlotItem
from ..items.shapes import PolyItem, RectItem
from ..items.tableitem import TableItem
from ..items.text import NoteItem, StampItem, _TextBase
from . import dialogs
from .commands import DocumentStructureCommand
from .icons import icon
from .panels import (BookmarksPanel, FunctionsPanel, LayersPanel, MarkupsPanel,
                     PagesPanel, ProblemsPanel, PropertiesPanel,
                     ToolSetsPanel, VariablesPanel)
from .docks import PanelDock, load_panel_state, save_panel_state
from .scene import DocumentScene, detach
from .shortcuts import COMMAND, INSERT, SYMBOL, TOOL, ShortcutManager
from . import toolsets
from .tools import CATEGORIES, TOOL_MAP, TOOLS, tools_in
from .view import SIZED_SHAPES
from .view import PageView
from .widgets import ColorButton

APP_NAME = "CalcForge"
ORGANISATION = "CalcForge"
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
        # Drawing a rectangle on a scaled page, or a dimension, asks a question.
        # Automated runs turn that off and set the values directly.
        self.interactive_prompts = True
        self._clipboard: list[dict] = []
        self._suspend_recalc = False
        # The independent check is not cheap, so it runs once the document has
        # been left alone for a moment rather than on every keystroke.
        self._verification = None
        self.scene = None
        self.toolbars: list = []
        self.visible_tools = None       # None means every tool
        self._default_state = None
        self._icon_names: dict = {}
        self._verify_timer = QTimer(self)
        self._verify_timer.setSingleShot(True)
        self._verify_timer.setInterval(900)
        self._verify_timer.timeout.connect(self._verify_quietly)

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

        self._autosave = QTimer(self)
        self._autosave.setInterval(120_000)
        self._autosave.timeout.connect(self.write_autosave)
        self._autosave.start()

        self.new_document(confirm=False)
        from ..app import current_theme
        from ..theme import DARK
        self.act_dark.setChecked(current_theme() == DARK)
        # What the arrangement looks like out of the box, so it can be put
        # back later however far it has been dragged about.
        self._default_state = self.saveState()
        self.restore_layout()
        # The arrangement is written out shortly after it changes, not only on
        # a clean quit — a crash or a kill should not cost the layout.
        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.setInterval(1500)
        self._layout_timer.timeout.connect(self.save_layout)
        for dock in self.panels:
            dock.dockLocationChanged.connect(lambda *_: self.note_layout_change())
            dock.topLevelChanged.connect(lambda *_: self.note_layout_change())
            dock.visibilityChanged.connect(lambda *_: self.note_layout_change())
            dock.pinnedChanged.connect(lambda *_: self.note_layout_change())
            dock.collapsedChanged.connect(lambda *_: self.note_layout_change())
        for toolbar in self.toolbars:
            toolbar.topLevelChanged.connect(lambda *_: self.note_layout_change())
            toolbar.visibilityChanged.connect(lambda *_: self.note_layout_change())
            toolbar.movableChanged.connect(lambda *_: self.note_layout_change())
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
        self.cell_ref.setMinimumWidth(54)
        self.cell_ref.setAlignment(Qt.AlignCenter)
        self.cell_ref.setStyleSheet(
            "border:1px solid #c6ccd6; border-radius:3px; padding:2px 6px; background:#fff;")
        # Excel's name box: type a name here and the rest of the document can
        # read this cell by it.
        self.cell_name = QLineEdit()
        self.cell_name.setMinimumWidth(110)
        self.cell_name.setMaximumWidth(160)
        self.cell_name.setPlaceholderText("name this cell")
        self.cell_name.setToolTip(
            "Give this cell a variable name and every calculation in the\n"
            "document can use it. Clear the box to stop publishing it.")
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
        bar.addWidget(QLabel("as"))
        bar.addWidget(self.cell_name)
        bar.addWidget(QLabel("ƒx"))
        bar.addWidget(self.formula_edit, 1)
        bar.addWidget(self.cell_value)
        self.formula_bar.setVisible(False)
        layout.addWidget(self.formula_bar)
        layout.addWidget(self.view, 1)
        self.setCentralWidget(central)

    def give_icon(self, action, name: str):
        """Put an icon on an action and remember which, for the next theme.

        Every icon is drawn in the theme's ink, so one set and forgotten stays
        the colour it was drawn in and goes invisible when the theme flips.
        Nothing may call ``setIcon`` on a long-lived action without coming
        through here.
        """
        action.setIcon(icon(name))
        self._icon_names[action] = name
        return action

    def _act(self, key: str, text: str, slot, shortcut: str = "", icon_name: str = "",
             checkable: bool = False, tip: str = "") -> QAction:
        action = QAction(text, self)
        if icon_name:
            self.give_icon(action, icon_name)
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
        self._act("insert_pdf", "Insert PDF pages…", lambda: self.insert_pdf(),
                  "Ctrl+I", "pdf")
        self._act("insert_image_page", "Insert image as a page…",
                  lambda: self.insert_image_page(), "", "image")
        self._act("export_pdf", "Export to PDF…", self.export_pdf, "Ctrl+E", "pdf")
        self._act("export_png", "Export pages as images…", self.export_images)
        self._act("export_markups", "Export markups list…", self.export_markups)
        self._act("export_vars", "Export variables…", self.export_variables)
        self._act("print", "Print…", self.print_document, "Ctrl+P", "print")
        self._act("preview", "Print preview…", self.print_preview)
        self._act("quit", "Exit", self.close, "Ctrl+Q")

        self.act_undo = self.undo_stack.createUndoAction(self, "Undo")
        self.act_undo.setShortcut(QKeySequence.Undo)
        self.give_icon(self.act_undo, "undo")
        self.act_redo = self.undo_stack.createRedoAction(self, "Redo")
        self.act_redo.setShortcut(QKeySequence.Redo)
        self.give_icon(self.act_redo, "redo")

        self._act("cut", "Cut", self.cut_selection, "Ctrl+X")
        self._act("copy", "Copy", self.copy_selection, "Ctrl+C")
        self._act("paste", "Paste", self.paste_items, "Ctrl+V")
        self._act("paste_here", "Paste where I click…", self.paste_with_preview,
                  "Ctrl+Shift+V",
                  tip="Carry what was copied on the pointer and click to drop it")
        self._act("duplicate", "Duplicate", self.duplicate_selection, "Ctrl+D")
        self._act("delete", "Delete", self.delete_selection, "", "delete")
        self._act("select_all", "Select all", self.select_all, "Ctrl+A")
        self._act("lock", "Lock / unlock", self.toggle_lock, "Ctrl+L")
        self._act("array", "Move or duplicate by an offset…", self.array_selection,
                  "Ctrl+Shift+D",
                  tip="Repeat the selection at a fixed spacing, any number of times")
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
        # Bare Page Up/Down scroll a screenful, as they do in any reader; with
        # Ctrl they jump a whole page.
        self._act("prev_page", "Previous page", lambda: self.go_to_page(self.current_index - 1),
                  "Ctrl+PgUp")
        self._act("next_page", "Next page", lambda: self.go_to_page(self.current_index + 1),
                  "Ctrl+PgDown")
        self._act("actual_size", "Actual size", lambda: self.view.set_zoom(1.0), "Ctrl+Alt+0")
        self._act("pin_panels", "Pin every panel", self.pin_all_panels, "", checkable=True,
                  tip="Keep the panels where they are, so a stray drag cannot move them")
        self._act("show_panels", "Show every panel", self.show_all_panels)
        self._act("reset_layout", "Reset the layout", self.reset_layout,
                  tip="Put the panels and toolbars back where they started")
        self._act("lock_toolbars", "Lock the toolbars", self.lock_toolbars, "",
                  checkable=True, tip="Stop the toolbars being dragged about")
        self._act("customise_toolbar", "Choose tools on the toolbar…",
                  self.customise_toolbar,
                  tip="Pick which tools appear on the markup toolbar")

        self._act("add_page", "Add page", lambda: self.add_page())
        self._act("duplicate_page", "Duplicate page", lambda: self.duplicate_page())
        self._act("delete_page", "Delete page", lambda: self.delete_page())
        self._act("page_setup", "Page setup…", self.page_setup, "Ctrl+Shift+P", "page")
        self._act("scale", "Page scale…", self.calibrate_dialog, "", "calibrate")
        self._act("doc_props", "Document properties…", lambda: self.document_properties())
        self._act("header_footer", "Header and footer…", self.edit_header_footer, "",
                  tip="Page numbers, the date, a title and a logo on every page")

        self._act("grid", "Show grid", self.toggle_grid, "Ctrl+G", checkable=True)
        self._act("snap", "Snap to grid", self.toggle_snap, "", checkable=True)
        self._act("snap_items", "Snap to what is drawn", self.toggle_item_snap, "",
                  checkable=True,
                  tip="Catch corners, centres and line ends of markups already "
                      "on the page")
        self._act("dark", "Dark theme", self.toggle_theme, "", checkable=True)
        self._act("margins", "Show margins", self.toggle_margins, "", checkable=True)
        self.act_margins.setChecked(True)
        self.act_snap_items.setChecked(True)
        self._act("sticky", "Keep the tool active", self.toggle_sticky, "", "pin",
                  checkable=True,
                  tip="Stay on the current tool after drawing instead of returning to Select")
        self._act("recalc", "Recalculate", self.recalculate, "F9", "recalc")
        self._act("verify", "Check every number…", self.verify_document, "F10",
                  "verify",
                  tip="Re-derive the whole document from scratch and report\n"
                      "anything that does not come back the same")
        self._act("apply_redactions", "Apply redactions…", self.apply_redactions, "",
                  tip="Permanently remove what the black boxes cover")
        self._act("split_lines", "Split into separate lines", self.split_calculation, "",
                  tip="Turn a multi-line calculation into one movable region per line")
        self._act("merge_lines", "Merge into one block", self.merge_calculations, "",
                  tip="Combine the selected calculations into a single region")

        self._act("shortcuts", "Keyboard shortcuts…", self.show_shortcuts, "F1",
                  tip="Every shortcut, and the keys you want them on")
        self._act("edit_shortcuts", "Keyboard shortcuts…", self.edit_shortcuts,
                  "Ctrl+K", tip="Change any shortcut by pressing the keys you want")
        self._act("problems", "Show problems", self.show_problems)
        self._act("renumber_counts", "Renumber count markers", self.renumber_counts)
        self._act("group", "Group", self.group_selection, "Ctrl+G",
                  tip="Make the selected markups one thing to click and move")
        self._act("ungroup", "Ungroup", self.ungroup_selection, "Ctrl+Shift+G")
        self._act("autosize", "Auto-size text box", self.autosize_text, "Alt+Z",
                  tip="Shrink the box around the words in it")
        self._act("preferences", "Preferences…", self.edit_preferences, "Ctrl+,",
                  tip="How the wheel behaves, how blocks start, spell checking")
        self._act("forget_defaults", "Forget markup defaults", self.forget_defaults,
                  tip="Put every kind of markup back to how it started")
        self._act("bookmark", "Add bookmark here", self.add_bookmark_here, "Ctrl+B",
                  tip="Name this place so it can be jumped to, printed in a "
                      "contents block and exported as a PDF bookmark")
        self._act("contents", "Insert a table of contents", self.insert_contents_block)
        self.symbol_actions: dict[str, QAction] = {}
        for binding in self.shortcuts.bindings():
            if binding.kind != SYMBOL:
                continue
            action = QAction(binding.label, self)
            action.setToolTip(f"Type {binding.payload} into the calculation being edited")
            action.triggered.connect(
                lambda _checked=False, text=binding.payload: self.insert_symbol(text))
            self.addAction(action)
            self.symbol_actions[binding.action_id] = action

        self._act("about", f"About {APP_NAME}", self.show_about)
        self._act("sample", "Load the worked example", self.load_sample)

    def _add_toolbar(self, bar) -> None:
        """Toolbars go on any edge, and remember where they were put."""
        bar.setMovable(True)
        bar.setFloatable(False)
        bar.setAllowedAreas(Qt.AllToolBarAreas)
        self.addToolBar(bar)
        self.toolbars.append(bar)

    def _build_toolbars(self) -> None:
        main_bar = QToolBar("Main")
        main_bar.setObjectName("toolbar_main")
        main_bar.setIconSize(QSize(22, 22))
        for action in (self.act_new, self.act_open, self.act_save, None,
                       self.act_insert_pdf, self.act_export_pdf, self.act_print, None,
                       self.act_undo, self.act_redo, None, self.act_recalc,
                       self.act_verify):
            main_bar.addSeparator() if action is None else main_bar.addAction(action)
        self._add_toolbar(main_bar)
        # The markup tools get a row to themselves: there are enough of them
        # that sharing one with the file actions hides the last few.
        self.addToolBarBreak()

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
                action = self.give_icon(QAction(tool.label, self), tool.icon)
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
        self._add_toolbar(tool_bar)
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
        # The stamp's wording and the count's subject only mean anything while
        # those tools are in hand, and reading "APPROVED" across the top of the
        # window while drawing a rectangle is just noise. Both come and go with
        # the tool they belong to.
        self.stamp_combo = QComboBox()
        from ..items.text import STAMP_PRESETS
        self.stamp_combo.addItems(list(STAMP_PRESETS))
        self.stamp_combo.setEditable(True)
        self.stamp_combo.setToolTip("What the stamp says")
        self.stamp_combo.currentTextChanged.connect(
            lambda text: setattr(self.view, "stamp_text", text))
        self.stamp_label = QLabel(" Stamp ")
        self._stamp_widgets = [style_bar.addWidget(self.stamp_label),
                               style_bar.addWidget(self.stamp_combo)]
        count_button = QToolButton()
        count_button.setText("Count subject…")
        count_button.clicked.connect(self.choose_count_subject)
        self._count_widgets = [style_bar.addWidget(count_button)]
        self._show_tool_extras("select")
        self._add_toolbar(style_bar)

    def _dock(self, title: str, widget: QWidget, area: Qt.DockWidgetArea,
              name: str) -> PanelDock:
        dock = PanelDock(title, widget, name, self)
        self.addDockWidget(area, dock)
        self.panels.append(dock)
        return dock

    def _build_docks(self) -> None:
        self.panels: list[PanelDock] = []
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
        self.layers_panel = LayersPanel(self)
        self.dock_layers = self._dock("Layers", self.layers_panel,
                                      Qt.RightDockWidgetArea, "dock_layers")
        self.markups_panel = MarkupsPanel(self)
        self.dock_markups = self._dock("Markups", self.markups_panel,
                                       Qt.BottomDockWidgetArea, "dock_markups")
        self.problems_panel = ProblemsPanel(self)
        self.dock_problems = self._dock("Problems", self.problems_panel,
                                        Qt.BottomDockWidgetArea, "dock_problems")
        self.toolsets_panel = ToolSetsPanel(self)
        self.dock_toolsets = self._dock("Tool sets", self.toolsets_panel,
                                        Qt.BottomDockWidgetArea, "dock_toolsets")
        self.bookmarks_panel = BookmarksPanel(self)
        self.bookmarks_panel.bookmarkActivated.connect(self.go_to_bookmark)
        self.dock_bookmarks = self._dock("Bookmarks", self.bookmarks_panel,
                                         Qt.BottomDockWidgetArea, "dock_bookmarks")
        # Everything you look things up in goes in one place along the bottom:
        # markups, variables, functions, layers and problems as tabs of the
        # same panel, so the right-hand side is left to Properties alone.
        self.reference_docks = [self.dock_markups, self.dock_variables,
                                self.dock_functions, self.dock_layers,
                                self.dock_toolsets, self.dock_bookmarks,
                                self.dock_problems]
        for dock in self.reference_docks[1:]:
            self.addDockWidget(Qt.BottomDockWidgetArea, dock)
        for first, second in zip(self.reference_docks, self.reference_docks[1:]):
            self.tabifyDockWidget(first, second)
        self.dock_markups.raise_()
        self.resizeDocks([self.dock_pages, self.dock_properties], [190, 320], Qt.Horizontal)
        self.resizeDocks(self.reference_docks, [230] * len(self.reference_docks),
                         Qt.Vertical)

    def _build_menus(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("&File")
        for action in (self.act_new, self.act_open, None, self.act_save, self.act_save_as,
                       None, self.act_insert_pdf, self.act_insert_image_page,
                       None, self.act_export_pdf,
                       self.act_export_png, self.act_export_markups, self.act_export_vars,
                       None, self.act_preview, self.act_print, None, self.act_quit):
            file_menu.addSeparator() if action is None else file_menu.addAction(action)

        edit_menu = bar.addMenu("&Edit")
        for action in (self.act_undo, self.act_redo, None, self.act_cut, self.act_copy,
                       self.act_paste, self.act_duplicate, self.act_delete, None,
                       self.act_select_all, self.act_lock, self.act_array):
            edit_menu.addSeparator() if action is None else edit_menu.addAction(action)
        order_menu = edit_menu.addMenu("Order")
        for action in (self.act_front, self.act_forward, self.act_backward, self.act_back):
            order_menu.addAction(action)
        align_menu = edit_menu.addMenu("Align")
        for key in ("left", "hcenter", "right", "top", "vcenter", "bottom"):
            align_menu.addAction(getattr(self, f"act_align_{key}"))
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_preferences)

        view_menu = bar.addMenu("&View")
        for action in (self.act_zoom_in, self.act_zoom_out, self.act_actual_size,
                       self.act_fit_page,
                       self.act_fit_width, self.act_zoom_sel, None, self.act_grid,
                       self.act_snap, self.act_snap_items, self.act_margins,
                       self.act_dark, None,
                       self.act_prev_page,
                       self.act_next_page):
            view_menu.addSeparator() if action is None else view_menu.addAction(action)
        panels_menu = view_menu.addMenu("Panels")
        for dock in self.panels:
            panels_menu.addAction(dock.toggleViewAction())
        panels_menu.addSeparator()
        panels_menu.addAction(self.act_pin_panels)
        panels_menu.addAction(self.act_show_panels)
        panels_menu.addAction(self.act_reset_layout)
        view_menu.addSeparator()
        toolbars_menu = view_menu.addMenu("Toolbars")
        for toolbar in self.toolbars:
            toolbars_menu.addAction(toolbar.toggleViewAction())
        toolbars_menu.addSeparator()
        toolbars_menu.addAction(self.act_lock_toolbars)
        toolbars_menu.addAction(self.act_customise_toolbar)

        # Mnemonic on the "k": Alt+M belongs to the dimension tool, and a
        # menu with the same mnemonic makes the shortcut ambiguous.
        markup_menu = bar.addMenu("Mar&kup")
        markup_menu.addAction(self.act_group)
        markup_menu.addAction(self.act_ungroup)
        markup_menu.addAction(self.act_autosize)
        markup_menu.addSeparator()
        markup_menu.addAction(self.act_forget_defaults)
        markup_menu.addSeparator()
        markup_menu.addAction(self.act_apply_redactions)
        markup_menu.addAction(self.act_renumber_counts)
        markup_menu.addSeparator()
        markup_menu.addAction(self.act_export_markups)

        # Mnemonic on the "g" for the same reason: Alt+P draws freehand.
        page_menu = bar.addMenu("Pa&ge")
        for action in (self.act_bookmark, None,
                       self.act_add_page, self.act_duplicate_page, self.act_delete_page,
                       None, self.act_page_setup, self.act_scale, self.act_header_footer,
                       None, self.act_doc_props):
            page_menu.addSeparator() if action is None else page_menu.addAction(action)

        insert_menu = bar.addMenu("&Insert")
        for tool in TOOLS:
            if tool.category in ("Calculate", "Annotate"):
                action = self.give_icon(QAction(tool.label, self), tool.icon)
                action.triggered.connect(lambda _c=False, key=tool.key: self.select_tool(key))
                insert_menu.addAction(action)
        insert_menu.addSeparator()
        symbol_menu = insert_menu.addMenu("Maths s&ymbol")
        for action in self.symbol_actions.values():
            symbol_menu.addAction(action)
        insert_menu.addSeparator()
        insert_menu.addAction(self.act_contents)
        insert_menu.addSeparator()
        insert_menu.addAction(self.act_insert_pdf)
        insert_menu.addAction(self.act_insert_image_page)

        calc_menu = bar.addMenu("&Calculate")
        calc_menu.addAction(self.act_recalc)
        calc_menu.addAction(self.act_verify)
        calc_menu.addSeparator()
        calc_menu.addAction(self.act_split_lines)
        calc_menu.addAction(self.act_merge_lines)
        calc_menu.addSeparator()
        calc_menu.addAction(self.act_problems)
        calc_menu.addAction(self.act_renumber_counts)
        calc_menu.addAction(self.act_export_vars)

        help_menu = bar.addMenu("&Help")
        # One entry, not two: both used to be called "Keyboard shortcuts".
        help_menu.addAction(self.act_shortcuts)
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
        self.view.pageChanged.connect(self.follow_scrolled_page)
        # Tool keys have to fall silent while somebody is typing, and a
        # shortcut fires before the key ever reaches the editor — so they are
        # headed off at the one point that sees every keystroke.
        application = QApplication.instance()
        if application is not None:
            application.installEventFilter(self)
        self.pages_panel.pageSelected.connect(self.go_to_page)
        self.pages_panel.pagesReordered.connect(self.move_page)
        self.markups_panel.markupActivated.connect(self.reveal_markup)
        self.problems_panel.problemActivated.connect(self.reveal_markup)
        self.layers_panel.layersChanged.connect(self.apply_layers)
        self.variables_panel.insertRequested.connect(self.insert_into_math)
        self.functions_panel.insertRequested.connect(self.insert_into_math)
        self.formula_edit.returnPressed.connect(self.commit_formula_bar)
        self.cell_name.editingFinished.connect(self.commit_cell_name)
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
        """Give every page a frame on the canvas, and show the current one.

        A page that already has a live frame keeps it. Building a fresh one
        would load the page's *pending* items, and those were emptied into the
        frame the first time it was built — so rebuilding after inserting a
        page would have quietly emptied every page in the document.
        """
        if self.scene is None or self.scene.document is not self.document:
            self.scene = DocumentScene(self.document)
            self.scene.itemsChanged.connect(self.refresh_lists)
            self.view.setScene(self.scene)
        # Frames whose page has gone leave the canvas with it.
        live = {id(page) for page in self.document.pages}
        for frame in list(self.scene.frames):
            if id(frame.page) not in live:
                self.scene.frames.remove(frame)
                self.scene.removeItem(frame)
        ordered = []
        for page in self.document.pages:
            if page.frame is None or page.frame.scene() is not self.scene:
                frame = self.scene.add_frame(page)
                page.frame = frame
                frame.load_items(page._pending_items)
            elif page._pending_items:
                page.frame.load_items(page._pending_items)
            page._pending_items = []
            ordered.append(page.frame)
        self.scene.frames = ordered
        self.scene.layout_pages()
        self.current_index = max(0, min(self.current_index, len(self.document.pages) - 1))
        self.recalculate()
        self.page_spin.blockSignals(True)
        self.page_spin.setRange(1, len(self.document.pages))
        self.page_spin.setValue(self.current_index + 1)
        self.page_spin.blockSignals(False)
        self.pages_panel.rebuild(self.document, self.current_index)
        self.apply_layers()
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
        self.clear_autosave()
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
        self.save_layout()
        self._autosave.stop()
        self.clear_autosave()
        try:
            self.undo_stack.cleanChanged.disconnect()
        except (RuntimeError, TypeError):
            pass
        event.accept()

    # ==================================================================
    # autosave and recovery
    # ==================================================================
    def autosave_path(self) -> str:
        if self.document.path:
            return self.document.path + ".autosave"
        return os.path.join(self.recovery_dir(), "untitled.cfx.autosave")

    @staticmethod
    def recovery_dir() -> str:
        from PySide6.QtCore import QStandardPaths
        base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or "."
        folder = os.path.join(base, "recovery")
        os.makedirs(folder, exist_ok=True)
        return folder

    def write_autosave(self) -> Optional[str]:
        """Save a recovery copy beside the document, quietly."""
        if self.undo_stack.isClean() and not self.document.modified:
            return None
        path = self.autosave_path()
        try:
            saved_path = self.document.path
            project_io.save_document(self.document, path, enforce_extension=False)
            self.document.path = saved_path     # an autosave is not a save-as
            self.document.modified = True
            return path
        except Exception:                        # noqa: BLE001 - never interrupt typing
            return None

    def clear_autosave(self) -> None:
        for path in {self.autosave_path(),
                     os.path.join(self.recovery_dir(), "untitled.cfx.autosave")}:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass

    def offer_recovery(self) -> bool:
        """On start-up, offer to reopen whatever a previous session left behind."""
        path = os.path.join(self.recovery_dir(), "untitled.cfx.autosave")
        if not os.path.exists(path):
            return False
        answer = QMessageBox.question(
            self, "Recover unsaved work",
            "CalcForge found a document from a session that did not finish.\n\n"
            "Open the recovered copy?",
            QMessageBox.Yes | QMessageBox.No)
        if answer != QMessageBox.Yes:
            self.clear_autosave()
            return False
        try:
            project_io.load_document(self.document, path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Recover unsaved work", str(exc))
            return False
        self.document.path = None
        self.document.modified = True
        self.current_index = 0
        self.rebuild_scenes()
        self.update_title()
        self.status_hint.setText("Recovered unsaved work — save it somewhere permanent")
        return True

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
        # Anything half-finished belongs to the page being left, so it is
        # settled here rather than being carried onto the next one.
        self.view.end_item_edit()
        self.view.deactivate_table()
        self.view.cancel_draft()
        self.current_index = index
        self.view._shown_page = index
        self.view.go_to_page_top(index)
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(index + 1)
        self.page_spin.blockSignals(False)
        self.pages_panel.list.blockSignals(True)
        self.pages_panel.list.setCurrentRow(index)
        self.pages_panel.list.blockSignals(False)
        self.refresh_scale_label()
        self.refresh_selection()

    def eventFilter(self, watched, event) -> bool:
        """Let the editor keep a key that would otherwise pick a tool.

        Qt asks with a ShortcutOverride before it fires a shortcut. Accepting
        it means the key goes to whatever has focus instead — which is exactly
        what should happen to M, or Alt+M, in the middle of a sentence.
        Document commands (save, undo, zoom) are deliberately left alone: every
        other application keeps those live while you type, and so does this.
        """
        if event.type() == QEvent.ShortcutOverride and self.view.is_editing():
            sequence = QKeySequence(event.keyCombination())
            if self.shortcuts.is_canvas_binding(sequence):
                event.accept()
                return True
        return super().eventFilter(watched, event)

    # ==================================================================
    # panels and toolbars
    # ==================================================================
    def pin_all_panels(self, pinned: bool) -> None:
        for dock in self.panels:
            dock.set_pinned(pinned)
        self.status_hint.setText("Panels pinned" if pinned else "Panels unpinned")

    def show_all_panels(self) -> None:
        for dock in self.panels:
            dock.set_collapsed(False)
            dock.show()

    def lock_toolbars(self, locked: bool) -> None:
        for bar in self.toolbars:
            bar.setMovable(not locked)
        self.status_hint.setText("Toolbars locked" if locked else "Toolbars unlocked")

    def reset_layout(self) -> None:
        """Put every panel and toolbar back where it started."""
        settings = QSettings(ORGANISATION, APP_NAME)
        for key in ("window/geometry", "window/state", "panels/pinned",
                    "panels/collapsed", "toolbars/locked", "toolbars/tools"):
            settings.remove(key)
        if self._default_state is not None:
            self.restoreState(self._default_state)
        for dock in self.panels:
            dock.set_pinned(False)
            dock.set_collapsed(False)
            dock.show()
        for bar in self.toolbars:
            bar.setMovable(True)
            bar.show()
        self.act_pin_panels.setChecked(False)
        self.act_lock_toolbars.setChecked(False)
        self.visible_tools = None
        self.apply_visible_tools()
        self.status_hint.setText("Layout reset")

    def customise_toolbar(self) -> None:
        """Choose which markup tools are on the toolbar."""
        dialog = dialogs.ToolbarDialog(TOOLS, self.visible_tool_keys(), self)
        if dialog.exec() != dialogs.QDialog.Accepted:
            return
        self.visible_tools = dialog.chosen()
        self.apply_visible_tools()
        self.save_layout()

    def visible_tool_keys(self) -> set:
        if self.visible_tools is None:
            return {tool.key for tool in TOOLS}
        return set(self.visible_tools)

    def apply_visible_tools(self) -> None:
        wanted = self.visible_tool_keys()
        for key, action in self.tool_actions.items():
            action.setVisible(key in wanted)

    # -- remembering it ------------------------------------------------
    def note_layout_change(self) -> None:
        """Something moved; write the arrangement out in a moment."""
        timer = getattr(self, "_layout_timer", None)
        if timer is not None:
            timer.start()

    def save_layout(self) -> None:
        settings = QSettings(ORGANISATION, APP_NAME)
        settings.setValue("window/geometry", self.saveGeometry())
        settings.setValue("window/maximised", self.isMaximized())
        settings.setValue("window/state", self.saveState())
        settings.setValue("toolbars/locked", not self.toolbars[0].isMovable())
        if self.visible_tools is None:
            settings.remove("toolbars/tools")
        else:
            settings.setValue("toolbars/tools", sorted(self.visible_tools))
        save_panel_state(self.panels)
        settings.sync()

    def restore_layout(self) -> None:
        settings = QSettings(ORGANISATION, APP_NAME)
        geometry = settings.value("window/geometry")
        state = settings.value("window/state")
        if geometry is not None:
            self.restoreGeometry(geometry)
        if state is not None:
            self.restoreState(state)
        if str(settings.value("window/maximised", "false")).lower() == "true":
            self.showMaximized()
        stored = settings.value("toolbars/tools", None)
        if stored:
            if isinstance(stored, str):
                stored = [stored]
            self.visible_tools = set(stored)
            self.apply_visible_tools()
        locked = str(settings.value("toolbars/locked", "false")).lower() == "true"
        self.act_lock_toolbars.setChecked(locked)
        self.lock_toolbars(locked)
        load_panel_state(self.panels)
        self.act_pin_panels.setChecked(all(d.pinned for d in self.panels))

    def follow_scrolled_page(self, index: int) -> None:
        """The reader scrolled onto another page; catch the chrome up.

        Deliberately does not scroll: the view is already where the reader put
        it, and moving it under them would be maddening.
        """
        if not 0 <= index < len(self.document.pages) or index == self.current_index:
            return
        self.current_index = index
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(index + 1)
        self.page_spin.blockSignals(False)
        self.pages_panel.list.blockSignals(True)
        self.pages_panel.list.setCurrentRow(index)
        self.pages_panel.list.blockSignals(False)
        self.refresh_scale_label()

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
        # Adding or removing a page moves the reader to it, the way inserting a
        # page in any document viewer does. The target is held over the scroll:
        # a short page (a photo, a small PDF sheet) leaves the next page over
        # the middle of the view, and that must not steal the selection back.
        target = self.current_index
        self.view.go_to_page_top(target)
        self.current_index = target
        self.view._shown_page = target
        self.follow_scrolled_page(target)
        after = self._structure_snapshot()
        self.undo_stack.push(DocumentStructureCommand(before, after, description,
                                                      self._restore_structure))
        self.mark_modified()

    def page_index(self, index: Optional[int] = None) -> int:
        """The page a command applies to: the one named, else the current one."""
        if index is None:
            return self.current_index
        return max(0, min(int(index), len(self.document.pages) - 1))

    def add_page(self, index: Optional[int] = None, before: bool = False) -> None:
        target = self.page_index(index) + (0 if before else 1)

        def mutate():
            self.document.add_page(target)
            self.current_index = target
        self._structural_change("Add page", mutate)

    def add_page_before(self, index: Optional[int] = None) -> None:
        self.add_page(index, before=True)

    def duplicate_page(self, index: Optional[int] = None) -> None:
        which = self.page_index(index)
        source = self.document.pages[which].to_dict()
        target = which + 1

        def mutate():
            copy = Page.from_dict(source)
            copy.uid = os.urandom(8).hex()
            self.document.pages.insert(target, copy)
            self.current_index = target
        self._structural_change("Duplicate page", mutate)

    def copy_page(self, index: Optional[int] = None) -> None:
        """Put a whole page on the clipboard, background and markups and all."""
        which = self.page_index(index)
        page = self.document.pages[which].to_dict()
        source = self.document.pages[which]
        keys = set(source.frame.assets_used()) if source.frame is not None else set()
        if source.background_key:
            keys.add(source.background_key)
        assets = {}
        for key in keys:
            blob = self.document.asset(key)
            if blob:
                assets[key] = base64.b64encode(blob).decode("ascii")
        payload = {"calcforge_page": page, "assets": assets}
        QApplication.clipboard().setText(json.dumps(payload))
        self.status_hint.setText(f"Copied page {which + 1}")

    def page_on_the_clipboard(self) -> Optional[dict]:
        """The page waiting on the clipboard, if there is one."""
        try:
            payload = json.loads(QApplication.clipboard().text() or "")
        except (ValueError, TypeError):
            return None
        if not isinstance(payload, dict) or "calcforge_page" not in payload:
            return None
        return payload

    def paste_page(self, index: Optional[int] = None) -> None:
        """Put the copied page in after this one."""
        payload = self.page_on_the_clipboard()
        if payload is None:
            self.status_hint.setText("There is no page on the clipboard")
            return
        which = self.page_index(index)
        target = which + 1
        for key, encoded in (payload.get("assets") or {}).items():
            if not self.document.asset(key):
                try:
                    self.document.put_asset(key, base64.b64decode(encoded))
                except (ValueError, TypeError):
                    pass

        def mutate():
            page = Page.from_dict(payload["calcforge_page"])
            page.uid = os.urandom(8).hex()
            self.document.pages.insert(target, page)
            self.current_index = target
        self._structural_change("Paste page", mutate)

    def delete_page(self, index: Optional[int] = None) -> None:
        if len(self.document.pages) <= 1:
            QMessageBox.information(self, "Delete page", "A document needs at least one page.")
            return
        which = self.page_index(index)
        if QMessageBox.question(self, "Delete page",
                                f"Delete page {which + 1}?") != QMessageBox.Yes:
            return

        def mutate():
            self.document.remove_page(which)
            self.current_index = max(0, which - 1)
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

    def insert_pdf(self, index: Optional[int] = None, before: bool = False) -> None:
        dialog = dialogs.PdfImportDialog(self, self.current_page().setup)
        if dialog.exec() != dialogs.QDialog.Accepted:
            return
        path, indices, fit, dpi = dialog.selection()
        if not path or not indices:
            QMessageBox.information(self, "Insert PDF", "No pages were selected.")
            return
        target = self.page_index(index) + (0 if before else 1)

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

    def insert_image_page(self, index: Optional[int] = None,
                          before: bool = False) -> None:
        """Put a photo or a scan in as a page of its own."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Insert image as a page", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp)")
        if not path:
            return
        target = self.page_index(index) + (0 if before else 1)

        def mutate():
            pdfio.import_image(self.document, path, pdfio.FIT_ORIGINAL, at=target)
            self.current_index = target
        try:
            self._structural_change("Insert image page", mutate)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Insert image", str(exc))
            return
        self.view.fit_page()
        self.status_hint.setText(f"Inserted {os.path.basename(path)} as a page")

    def rotate_page(self, index: Optional[int] = None, clockwise: bool = True) -> None:
        """Turn a page a quarter turn, and everything that is drawn on it.

        The paper, its background sheet and the markups all turn together —
        rotating only the paper would leave the drawing stretched across the
        wrong shape and the markups off the edge.
        """
        which = self.page_index(index)
        page = self.document.pages[which]
        setup = page.setup
        width, height = setup.width_pt, setup.height_pt
        rotated_background = self._rotate_background(page, clockwise)

        def mutate():
            setup.width_mm, setup.height_mm = setup.height_mm, setup.width_mm
            if setup.orientation == LANDSCAPE:
                setup.orientation = PORTRAIT
            else:
                setup.orientation = LANDSCAPE
            if clockwise:
                (setup.margin_left, setup.margin_top,
                 setup.margin_right, setup.margin_bottom) = (
                    setup.margin_bottom, setup.margin_left,
                    setup.margin_top, setup.margin_right)
            else:
                (setup.margin_left, setup.margin_top,
                 setup.margin_right, setup.margin_bottom) = (
                    setup.margin_top, setup.margin_right,
                    setup.margin_bottom, setup.margin_left)
            if rotated_background:
                page.background_key = rotated_background
            frame = page.frame
            if frame is not None:
                frame._background = None
                for item in frame.markups():
                    position = item.pos()
                    if clockwise:
                        item.setPos(height - position.y(), position.x())
                        item.setRotation(item.rotation() + 90)
                    else:
                        item.setPos(position.y(), width - position.x())
                        item.setRotation(item.rotation() - 90)
            self.current_index = which
        self._structural_change("Rotate page", mutate)
        self.view.fit_page()

    def _rotate_background(self, page, clockwise: bool) -> str:
        """A quarter-turned copy of the page's background sheet, if it has one."""
        data = self.document.asset(page.background_key)
        if not data:
            return ""
        image = QImage()
        if not image.loadFromData(data) or image.isNull():
            return ""
        transform = QTransform().rotate(90 if clockwise else -90)
        turned = image.transformed(transform, Qt.SmoothTransformation)
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        if not turned.save(buffer, "PNG"):
            return ""
        return self.document.add_asset(bytes(buffer.data()), "png")

    def set_page_size(self, index: Optional[int] = None, name: str = "A4") -> None:
        """Put one page onto a different sheet of paper, keeping its way up."""
        which = self.page_index(index)
        page = self.document.pages[which]
        orientation = page.setup.orientation

        def mutate():
            setup = PageSetup.from_name(name, orientation)
            setup.margin_left = page.setup.margin_left
            setup.margin_top = page.setup.margin_top
            setup.margin_right = page.setup.margin_right
            setup.margin_bottom = page.setup.margin_bottom
            page.setup = setup
            self.current_index = which
        self._structural_change(f"Page size {name}", mutate)
        self.view.fit_page()

    def page_menu(self, index: int) -> QMenu:
        """Everything you can do to one page, for its right-click menu."""
        index = self.page_index(index)
        menu = QMenu(self)
        menu.addAction("Go to this page", lambda: self.go_to_page(index))
        menu.addAction("Add to bookmarks…", lambda: self.bookmark_page(index))
        menu.addSeparator()
        menu.addAction("Copy page", lambda: self.copy_page(index))
        menu.addAction("Paste page", lambda: self.paste_page(index))
        menu.addSeparator()
        menu.addAction("Insert blank page before",
                       lambda: self.add_page_before(index))
        menu.addAction("Insert blank page after", lambda: self.add_page(index))
        menu.addAction("Duplicate page", lambda: self.duplicate_page(index))
        menu.addSeparator()
        menu.addAction("Insert PDF pages before…",
                       lambda: self.insert_pdf(index, before=True))
        menu.addAction("Insert PDF pages after…", lambda: self.insert_pdf(index))
        menu.addAction("Insert image before…",
                       lambda: self.insert_image_page(index, before=True))
        menu.addAction("Insert image after…",
                       lambda: self.insert_image_page(index))
        menu.addSeparator()
        up = menu.addAction("Move up", lambda: self.move_page(index, index - 1))
        up.setEnabled(index > 0)
        down = menu.addAction("Move down", lambda: self.move_page(index, index + 1))
        down.setEnabled(index < len(self.document.pages) - 1)
        menu.addSeparator()
        menu.addSeparator()
        menu.addAction("Rotate clockwise", lambda: self.rotate_page(index, True))
        menu.addAction("Rotate anticlockwise", lambda: self.rotate_page(index, False))
        paper = menu.addMenu("Paper size")
        for name in PAGE_SIZES:
            entry = paper.addAction(name, lambda n=name: self.set_page_size(index, n))
            entry.setCheckable(True)
            entry.setChecked(self.document.pages[index].setup.size_name == name)
        menu.addAction("Page setup…", lambda: (self.go_to_page(index),
                                               self.page_setup()))
        menu.addAction("Page scale…", lambda: (self.go_to_page(index),
                                               self.calibrate_dialog()))
        recolour = menu.addAction("Change colours…",
                                  lambda: self.recolour_page(index))
        recolour.setEnabled(bool(self.document.pages[index].background_key))
        delete = menu.addAction("Delete page", lambda: self.delete_page(index))
        delete.setEnabled(len(self.document.pages) > 1)
        return menu

    # ==================================================================
    # scale
    # ==================================================================
    def calibrate_scale(self, measured_pt: Optional[float] = None) -> None:
        """Set the page scale, from a drawn distance or straight from a ratio."""
        dialog = dialogs.ScaleDialog(self.current_page().scale, measured_pt, self)
        answer = dialog.exec()
        if answer == dialogs.ScaleDialog.PICK:
            self.start_calibrating()
            return
        if answer != dialogs.QDialog.Accepted:
            return
        scale = dialog.result_scale()
        if scale is None:
            return
        self.current_page().scale = scale
        self.apply_scale_change()

    def calibrate_dialog(self) -> None:
        self.calibrate_scale(None)

    def start_calibrating(self) -> None:
        """Hand over to the calibrate tool: two clicks, then the length."""
        self.select_tool("calibrate")
        self.status_hint.setText(
            "Calibrate: click one end of something you know the length of, "
            "then the other — then type that length")

    def apply_scale_change(self) -> None:
        """Everything that has to catch up when a page's scale changes.

        Through a full recalculation, never by refreshing one page's items on
        their own: evaluating a page against a workspace that already holds
        this pass's definitions turns every definition on it into a check, and
        "q = 5 kPa" quietly starts reading "true".
        """
        self.refresh_scale_label()
        self.recalculate()
        # Measurements and rectangle sizes are in the takeoff list too, so it
        # goes stale unless it is rebuilt with them.
        self.refresh_lists()
        self.refresh_selection()
        self.mark_modified()

    def set_area_unit(self, unit: str) -> None:
        if unit:
            self.current_page().scale.area_unit = unit
            self.recalculate()
            self.refresh_lists()
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
        for action_id, action in getattr(self, "symbol_actions", {}).items():
            action.setShortcut(QKeySequence(self.shortcuts.sequence(action_id)))

    def insert_symbol(self, text: str) -> None:
        """Put a maths symbol in at the cursor, wherever the cursor is."""
        if self.view.insert_symbol(text):
            return
        self.status_hint.setText(
            f"{text} has nowhere to go — open a calculation, a text box or a cell first")

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
        if binding.kind == SYMBOL:
            self.insert_symbol(binding.payload)
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
            if page.frame is None:
                continue
            for item in reading_order(page.frame.markups()):
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
        self._show_tool_extras(key)

    def _show_tool_extras(self, key: str) -> None:
        """Show the toolbar bits that belong to the tool now in hand."""
        for action in getattr(self, "_stamp_widgets", ()):
            action.setVisible(key == "stamp")
        for action in getattr(self, "_count_widgets", ()):
            action.setVisible(key == "count")

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
        """Seed a freshly drawn markup: the style toolbar, then its own default.

        A default saved for that kind of markup is a deliberate decision about
        how they should all look, so it has the last word over the toolbar's
        live colours.
        """
        self._apply_toolbar_style(item)
        toolsets.apply_default(item)

    def set_as_default(self, item: MarkupItem) -> None:
        """Draw the next markup of this kind the way this one is drawn."""
        key = toolsets.remember_default(item)
        self.status_hint.setText(
            f"New {item.display_name().lower()}s will look like this one "
            f"— Markup ▸ Forget defaults puts it back")
        return key

    def forget_defaults(self) -> None:
        """Put every kind of markup back to how it started."""
        toolsets.save_defaults({})
        self.status_hint.setText("Markups are back to their original look")

    def _apply_toolbar_style(self, item: MarkupItem) -> None:
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

    # ==================================================================
    # prompts the drawing tools use
    # ==================================================================
    def prompt_rectangle_size(self, item, always: bool = False) -> None:
        """Offer an exact size for a rectangle.

        Drawing on a scaled page asks straight away, because setting out is the
        whole point there. On an unscaled page a rectangle is usually markup, so
        it is only asked for on demand — the size is written on it either way.
        """
        page = self.current_page()
        if item.kind not in SIZED_SHAPES:
            return
        if not always and (not self.interactive_prompts
                           or not page.scale.is_calibrated()):
            return
        item.refresh(page=page)
        if item.width_value is None or item.height_value is None:
            return
        scaled = page.scale.is_calibrated()
        digits = max(page.scale.precision, 0) if scaled else 1
        dialog = dialogs.RectangleSizeDialog(
            format_quantity(item.width_value, digits, "fixed"),
            format_quantity(item.height_value, digits, "fixed"),
            page.scale.display_unit if scaled else "mm", self, scaled=scaled)
        if dialog.exec() != dialogs.QDialog.Accepted:
            return
        width, height = dialog.values()
        if not item.set_real_size(width, height, page):
            self.status_hint.setText("Could not read those dimensions — "
                                     "try something like “3 m”.")

    def prompt_table_size(self, table) -> None:
        """Ask how big a table just drawn should be.

        Dragging out a box says where the table goes, not how many cells it
        holds; every other editor asks, so this one does too.
        """
        if not self.interactive_prompts:
            return
        dialog = dialogs.TableSizeDialog(table.sheet.rows, table.sheet.cols, self)
        if dialog.exec() != dialogs.QDialog.Accepted:
            return
        rows, cols, header = dialog.values()
        table.prepareGeometryChange()
        table.sheet.resize(rows, cols)
        table.sheet.header_row = header
        table.refresh(self.document.workspace, self.current_page())

    def edit_plot(self, item, fresh: bool = False) -> None:
        """Ask a graph what it plots."""
        if fresh and not self.interactive_prompts:
            return
        workspace = self.document.workspace
        names = set(workspace.variables) | set(workspace.functions)
        dialog = dialogs.PlotDialog(item, names, self)
        if dialog.exec() != dialogs.QDialog.Accepted:
            return
        if not fresh:
            self.view.begin_snapshot(self.view.involved_frames(item))
        dialog.apply()
        item.refresh(workspace, self.current_page())
        if not fresh:
            self.view.commit_snapshot("Edit plot")
        self.refresh_selection()

    def rename_table(self, table, name: str) -> None:
        """Set a table's name from the properties panel."""
        name = (name or "").strip()
        if name == table.table_name:
            return
        if name and not name.isidentifier():
            self.status_hint.setText(
                f"“{name}” cannot be used as a name — letters, digits and "
                "underscores only, not starting with a digit")
            return
        self.view.begin_snapshot(self.view.involved_frames(table))
        table.prepareGeometryChange()
        table.table_name = name
        self.recalculate()
        self.view.commit_snapshot("Name table")
        self.refresh_lists()

    def name_table(self, table) -> None:
        """Name a table so calculations can look values up in it."""
        name, accepted = QInputDialog.getText(
            self, "Name this table",
            "A calculation can then read it — for example, with the name "
            "“bolts”:\n\n    V := bolts(d, A, B)\n\n"
            "which finds d in column A and gives back the value beside it in "
            "column B, interpolating between the rows either side when it has "
            "to. Leave it empty to take the name away.",
            text=table.table_name)
        if not accepted:
            return
        name = name.strip()
        if name and not name.isidentifier():
            QMessageBox.warning(self, "Name this table",
                                f"“{name}” cannot be used as a name — letters, "
                                "digits and underscores only, not starting with "
                                "a digit.")
            return
        self.view.begin_snapshot(self.view.involved_frames(table))
        table.table_name = name
        self.recalculate()
        self.view.commit_snapshot("Name table")
        self.refresh_lists()
        self.status_hint.setText(
            f"This table is now “{name}” — read it with {name}(value, A, B)"
            if name else "This table no longer has a name")

    def edit_measure_text(self, item) -> None:
        """Type on a measurement, where the words are going to appear."""
        self.view.open_label_editor(item)

    def set_label_angle(self, item, angle) -> None:
        """Let the text follow the line again, or hold it where it was put."""
        self.view.begin_snapshot(self.view.involved_frames(item))
        item.label_angle = angle
        item.update()
        self.view.commit_snapshot("Dimension text angle")

    def set_rectangle_size(self, item) -> None:
        """Ask for an exact size for a rectangle already on the page."""
        self.view.begin_snapshot()
        self.prompt_rectangle_size(item, always=True)
        self.view.commit_snapshot("Rectangle size")
        self.refresh_selection()

    def set_size_visible(self, item, on: bool) -> None:
        self.view.begin_snapshot()
        item.show_size = bool(on)
        item.refresh(page=self.current_page())
        self.view.commit_snapshot("Show rectangle size")

    def note_missing_scale(self) -> None:
        """Say once that measurements are in page units until a scale is set."""
        if self.current_page().scale.is_calibrated():
            return
        self.status_hint.setText(
            "This page has no scale — measurements are paper distances. "
            "Click “Scale 1:1” in the status bar to set one.")

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
        if self.view.editing_item() is not None:
            return                      # Delete belongs to the text being edited
        items = [item for item in self.selected_items() if self.view.editable(item)]
        if not items:
            return
        self.view.deactivate_table()
        self.view.begin_snapshot()
        for item in items:
            detach(item)
        self.recalculate()
        self.view.commit_snapshot("Delete markup")
        self.refresh_selection()

    def take_snapshot(self, frame, region: QRectF) -> None:
        """Copy everything inside *region* on *frame*, keeping it as itself.

        Bluebeam's snapshot, but what comes back is not a picture: every
        markup, calculation and table in the region is copied as the thing it
        is, so pasting it puts real items down that stay sharp at any zoom and
        can still be edited. Only the page's own background sheet — the raster
        a PDF or a photo came in on — can be nothing but pixels, so that part
        is cropped at the resolution it was imported at.
        """
        region = region.normalized()
        if frame is None or region.width() < 2 or region.height() < 2:
            self.status_hint.setText("Snapshot: drag a region to copy")
            return
        payload: list[dict] = []
        assets: dict[str, str] = {}

        cropped = self._crop_background(frame.page, region)
        if cropped is not None:
            key, data = cropped
            assets[key] = base64.b64encode(data).decode("ascii")
            payload.append({"type": "image", "asset_key": key, "x": 0.0, "y": 0.0,
                            "rect": [0, 0, region.width(), region.height()],
                            "keep_aspect": False, "uid": os.urandom(8).hex()})

        for item in frame.ordered_markups():
            box = item.mapRectToParent(item.boundingRect())
            if not region.intersects(box):
                continue
            entry = item.serialize()
            entry["x"] = float(entry.get("x", 0.0)) - region.left()
            entry["y"] = float(entry.get("y", 0.0)) - region.top()
            payload.append(entry)
            key = entry.get("asset_key")
            if key and key not in assets:
                data = self.document.asset(key)
                if data:
                    assets[key] = base64.b64encode(data).decode("ascii")

        if len(payload) <= (1 if cropped is not None else 0) and not payload:
            self.status_hint.setText("Nothing in that region to copy")
            return

        self._clipboard = payload
        mime = QMimeData()
        mime.setText(json.dumps({CLIPBOARD_TAG: payload, "assets": assets}))
        picture = frame.render_image(dpi=150.0, for_print=False)
        scale = 150.0 / 72.0
        mime.setImageData(picture.copy(
            QRect(int(region.left() * scale), int(region.top() * scale),
                  max(int(region.width() * scale), 1),
                  max(int(region.height() * scale), 1))))
        QApplication.clipboard().setMimeData(mime)
        self.status_hint.setText(
            f"Snapshot: {len(payload)} item(s) copied — paste it anywhere")

    def _crop_background(self, page, region: QRectF):
        """The part of the page's background sheet inside the region."""
        data = self.document.asset(page.background_key)
        if not data:
            return None
        image = QImage()
        if not image.loadFromData(data) or image.isNull():
            return None
        across = image.width() / max(page.width_pt, 1.0)
        down = image.height() / max(page.height_pt, 1.0)
        box = QRect(int(region.left() * across), int(region.top() * down),
                    max(int(region.width() * across), 1),
                    max(int(region.height() * down), 1))
        box = box.intersected(image.rect())
        if box.isEmpty():
            return None
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        if not image.copy(box).save(buffer, "PNG"):
            return None
        raw = bytes(buffer.data())
        return self.document.add_asset(raw, "png"), raw

    def recolour_page(self, index: Optional[int] = None) -> None:
        """Change the colours of the sheet a page came in on."""
        which = self.page_index(index)
        page = self.document.pages[which]
        image = self._background_image(page)
        if image is None:
            QMessageBox.information(
                self, "Change colours",
                "This page has no drawing on it to recolour — it is a blank "
                "sheet you have written on, and the markups keep their own "
                "colours.")
            return
        changed = self._ask_recolour(image)
        if changed is None:
            return

        def mutate():
            page.background_key = changed
            if page.frame is not None:
                page.frame._background = None
            self.current_index = which
        self._structural_change("Change page colours", mutate)

    def recolour_item(self, item) -> None:
        """Change the colours of a picture on the page — a snapshot, say."""
        image = QImage()
        data = self.document.asset(getattr(item, "asset_key", ""))
        if not data or not image.loadFromData(data) or image.isNull():
            return
        changed = self._ask_recolour(image)
        if changed is None:
            return
        self.view.begin_snapshot(self.view.involved_frames(item))
        item.asset_key = changed
        item.load_from_document(self.document)
        self.view.commit_snapshot("Change colours")
        self.refresh_selection()

    def _background_image(self, page):
        image = QImage()
        data = self.document.asset(page.background_key)
        if not data or not image.loadFromData(data) or image.isNull():
            return None
        return image

    def _ask_recolour(self, image) -> Optional[str]:
        """Run the dialog and store the result; the new asset key, or None."""
        dialog = dialogs.RecolourDialog(image, self)
        if dialog.exec() != dialogs.QDialog.Accepted:
            return None
        recoloured = dialog.apply_to(image)
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        if not recoloured.save(buffer, "PNG"):
            QMessageBox.warning(self, "Change colours",
                                "The recoloured drawing could not be stored.")
            return None
        return self.document.add_asset(bytes(buffer.data()), "png")

    # ==================================================================
    # tool sets
    # ==================================================================
    def add_to_toolset(self, item=None, into: str = "") -> None:
        """Keep a markup — or the selection — in a tool set to use again."""
        items = [item] if item is not None else [
            i for i in self.selected_items() if isinstance(i, MarkupItem)]
        items = [i for i in items if isinstance(i, MarkupItem)]
        # Picking one member of a group means the group: it is one thing.
        whole: list = []
        for one in items:
            for member in self.view.group_of(one):
                if member not in whole:
                    whole.append(member)
        items = whole
        if not items:
            self.status_hint.setText("Select something on the page to keep")
            return
        groups = toolsets.load_toolsets()
        names = [group.name for group in groups]
        chosen, accepted = QInputDialog.getItem(
            self, "Add to a tool set", "Which set?", names,
            max(names.index(into), 0) if into in names else 0, False)
        if not accepted:
            return
        group = next(g for g in groups if g.name == chosen)
        # Grouped markups go in as one tool; anything else, one tool each.
        families: dict = {}
        loose = []
        for one in items:
            if one.group:
                families.setdefault(one.group, []).append(one)
            else:
                loose.append(one)
        for one in loose:
            group.entries.append(toolsets.entry_for(one, toolsets.COPY))
        for members in families.values():
            group.entries.append(toolsets.entry_for_many(members))
        kept = len(loose) + len(families)
        toolsets.save_toolsets(groups)
        self.toolsets_panel.rebuild(keep=chosen)
        self.dock_toolsets.raise_()
        self.status_hint.setText(
            f"Kept {kept} tool(s) in “{chosen}” — double-click one to put "
            "it down again")

    def paste_with_preview(self) -> None:
        """Take the clipboard in hand and show it before it is put down.

        Ctrl+V still pastes straight away, because that is what Ctrl+V does
        everywhere. This is for when the placing matters: the markups follow
        the pointer, faded, until a click drops them.
        """
        payload = self._clipboard
        text = QApplication.clipboard().text()
        if not payload and text.strip().startswith("{"):
            try:
                decoded = json.loads(text)
                payload = decoded.get(CLIPBOARD_TAG) or []
                for key, encoded in (decoded.get("assets") or {}).items():
                    if not self.document.asset(key):
                        self.document.put_asset(key, base64.b64decode(encoded))
            except (ValueError, TypeError):
                payload = []
        if not payload:
            self.status_hint.setText("Nothing copied to place")
            return
        left = min(float(entry.get("x", 0.0)) for entry in payload)
        top = min(float(entry.get("y", 0.0)) for entry in payload)
        parts = []
        for entry in payload:
            data = dict(entry)
            data["x"] = float(data.get("x", 0.0)) - left
            data["y"] = float(data.get("y", 0.0)) - top
            parts.append(data)
        one = len(parts) == 1
        held = toolsets.ToolEntry(
            "Pasted markup" if one else f"{len(parts)} pasted markups",
            parts[0] if one else {"type": toolsets.GROUP, "items": parts},
            toolsets.COPY)
        self.view.set_pending_stamp(held)
        self.status_hint.setText("Click where it should go · Esc to put it back")

    def use_tool_entry(self, entry) -> None:
        """Pick up a tool from a set: a copy to place, or a tool to draw with."""
        if entry.mode == toolsets.PROPERTIES:
            key = self._tool_for_payload(entry.payload)
            if key is None:
                self.status_hint.setText(f"“{entry.label}” cannot be drawn as a tool")
                return
            self.view.set_pending_properties(entry.payload)
            self.select_tool(key)
            self.status_hint.setText(
                f"{entry.label}: draw one — it will have this tool's properties")
            return
        self.view.set_pending_stamp(entry)
        self.status_hint.setText(
            f"{entry.label}: click where it should go · Esc to put it back")

    @staticmethod
    def _tool_for_payload(payload: dict):
        """The drawing tool that makes the kind of markup a payload describes."""
        type_name = payload.get("type", "")
        kind = payload.get("kind", "") or payload.get("shape_kind", "")
        for tool in TOOLS:
            if tool.factory is None:
                continue
            sample = tool.factory()
            if sample.TYPE != type_name:
                continue
            sample_kind = getattr(sample, "kind", "") or getattr(sample, "shape_kind", "")
            if kind and sample_kind != kind:
                continue
            return tool.key
        return None

    def activate_my_tool(self, number: int) -> bool:
        """The number keys reach for the first nine things in My Tools."""
        groups = toolsets.load_toolsets()
        mine = next((g for g in groups if g.name == toolsets.MY_TOOLS), None)
        if mine is None or not (1 <= number <= len(mine.entries)):
            return False
        self.use_tool_entry(mine.entries[number - 1])
        return True

    # ==================================================================
    # groups
    # ==================================================================
    def group_selection(self) -> None:
        """Make the selected markups one thing to click, move and copy."""
        items = [i for i in self.selected_items() if isinstance(i, MarkupItem)]
        if len(items) < 2:
            self.status_hint.setText("Select two or more markups to group them")
            return
        name = os.urandom(6).hex()
        self.view.begin_snapshot(self.view.all_frames())
        for item in items:
            item.group = name
            item.touch()
        self.view.commit_snapshot("Group markups")
        self.refresh_selection()
        self.status_hint.setText(f"Grouped {len(items)} markups — Ctrl+Shift+G "
                                 "takes them apart again")

    def ungroup_selection(self) -> None:
        """Take the selected groups apart."""
        items = [i for i in self.selected_items()
                 if isinstance(i, MarkupItem) and i.group]
        if not items:
            self.status_hint.setText("Nothing grouped in the selection")
            return
        self.view.begin_snapshot(self.view.all_frames())
        for item in items:
            item.group = ""
            item.touch()
        self.view.commit_snapshot("Ungroup markups")
        self.refresh_selection()
        self.status_hint.setText(f"Ungrouped {len(items)} markups")

    def copy_selection(self) -> None:
        if self.view.text_clipboard("copy"):
            self._clipboard = []
            return
        if self.view.active_table is not None and self.view.copy_cells():
            # Whatever markups were copied before, cells are what is on the
            # clipboard now — otherwise the next paste puts the old ones back.
            self._clipboard = []
            return
        items = self.selected_items()
        if not items:
            return
        self._clipboard = [item.serialize() for item in items]
        QApplication.clipboard().setText(json.dumps({CLIPBOARD_TAG: self._clipboard}))
        self.status_hint.setText(f"Copied {len(items)} markup(s)")

    def cut_selection(self) -> None:
        if self.view.text_clipboard("cut"):
            self._clipboard = []
            return
        if self.view.active_table is not None and self.view.cut_cells():
            self._clipboard = []
            return
        self.copy_selection()
        self.delete_selection()

    def paste_items(self) -> None:
        if self.view.text_clipboard("paste"):
            return
        if self.view.active_table is not None and self.view.paste_cells():
            return
        payload = self._clipboard
        text = QApplication.clipboard().text()
        # A table picked out on the page is where a block of cells belongs,
        # without having to open one of its cells first.
        if not payload and looks_like_a_grid(text):
            selected = [i for i in self.selected_items() if isinstance(i, TableItem)]
            if len(selected) == 1 and not selected[0].locked:
                self.view.activate_table(selected[0])
                if self.view.paste_cells():
                    return
        # Cells copied out of Excel with nowhere to go become a table of their
        # own, which is how most sheets get into a calculation in the first place.
        if not payload and looks_like_a_grid(text):
            self.paste_grid_as_table(text)
            return
        if text.strip().startswith("{"):
            try:
                decoded = json.loads(text)
                if CLIPBOARD_TAG in decoded:
                    payload = decoded[CLIPBOARD_TAG]
                    # A snapshot carries its images with it, so it can be
                    # pasted into a document that has never seen them.
                    for key, encoded in (decoded.get("assets") or {}).items():
                        if not self.document.asset(key):
                            self.document.put_asset(key, base64.b64decode(encoded))
            except (ValueError, TypeError):
                pass
        if not payload:
            return
        self.view.begin_snapshot()
        self.view.scene().clearSelection()
        # A paste lands under the pointer, the way it does in Bluebeam.
        target = self.view.pointer_scene_pos()
        offset = None
        if target is not None and payload:
            frame = self.view.typing_frame()
            local = frame.mapFromScene(target)
            first = payload[0]
            offset = QPointF(local.x() - float(first.get("x", 0)),
                             local.y() - float(first.get("y", 0)))
        # A pasted group is a group of its own: the members stay together, but
        # they are not the same group as the ones they were copied from.
        renamed: dict[str, str] = {}
        for entry in payload:
            copy = dict(entry)
            copy["uid"] = os.urandom(8).hex()
            if copy.get("group"):
                copy["group"] = renamed.setdefault(copy["group"], os.urandom(6).hex())
            if offset is not None:
                copy["x"] = copy.get("x", 0) + offset.x()
                copy["y"] = copy.get("y", 0) + offset.y()
            else:
                copy["x"] = copy.get("x", 0) + 14
                copy["y"] = copy.get("y", 0) + 14
            item = build_item(copy)
            if item is None:
                continue
            if isinstance(item, ImageItem):
                item.load_from_document(self.document)
            self.view.frame().add_markup(item)
            item.setSelected(True)
        self.recalculate()
        self.view.commit_snapshot("Paste")
        self.refresh_selection()

    @staticmethod
    def _looks_like_a_header(grid: list[list[str]]) -> bool:
        """A row of labels sitting over columns that are mostly numbers."""
        if len(grid) < 2:
            return False
        from ..core.spreadsheet import parse_literal
        first = [c for c in grid[0] if c.strip()]
        if not first or any(isinstance(parse_literal(c), (int, float)) for c in first):
            return False
        below = [c for line in grid[1:] for c in line if c.strip()]
        if not below:
            return False
        numeric = sum(1 for c in below if not isinstance(parse_literal(c), str))
        return numeric >= len(below) / 2

    def paste_grid_as_table(self, text: str) -> Optional[TableItem]:
        """Build a table from spreadsheet text on the clipboard."""
        grid = parse_clipboard_grid(text)
        if not grid:
            return None
        height = len(grid)
        width = max(len(line) for line in grid)
        table = TableItem()
        self.apply_default_style(table)
        table.author = self.document.settings.default_author or self.document.author
        table.sheet.resize(min(max(height, 1), MAX_ROWS), min(max(width, 1), MAX_COLS))
        table.sheet.paste_text(text, 0, 0)
        # A first row of words over columns of numbers is a header, the way
        # Excel would read it.
        table.sheet.header_row = self._looks_like_a_header(grid)
        table.sheet.recalculate(self.document.workspace)
        for index in range(table.sheet.cols):
            table.autofit_column(index)

        self.view.begin_snapshot()
        self.view.scene().clearSelection()
        self.view.typing_frame().add_markup(table, self.view.typing_position())
        table.setSelected(True)
        self.recalculate()
        self.view.commit_snapshot("Paste as table")
        self.refresh_selection()
        self.status_hint.setText(f"Pasted {height} × {width} cells as a table")
        return table

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
                self.view.frame().add_markup(copy)
                copy.setSelected(True)
        self.recalculate()
        self.view.commit_snapshot("Duplicate")
        self.refresh_selection()

    def select_all(self) -> None:
        for item in self.view.frame().markups():
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
        items = [i for i in self.selected_items() if self.view.editable(i)]
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

    def array_selection(self) -> None:
        """Move or copy the selection by an exact offset, any number of times."""
        items = [i for i in self.selected_items() if self.view.editable(i)]
        if not items:
            self.status_hint.setText("Select something to move or duplicate first.")
            return
        page = self.current_page()
        scaled = page.scale.is_calibrated()
        dialog = dialogs.ArrayDialog(page.scale.display_unit if scaled else "mm",
                                     scaled, self)
        if dialog.exec() != dialogs.QDialog.Accepted:
            return
        dx_text, dy_text, count, duplicate = dialog.offsets()
        self.apply_array(items, dx_text, dy_text, count, duplicate)

    def apply_array(self, items, dx_text: str, dy_text: str,
                    count: int, duplicate: bool) -> None:
        """The half of the array command that does not need a dialog."""
        if not items or count < 1:
            return
        page = self.current_page()
        try:
            step = QPointF(self.distance_in_points(dx_text, page),
                           self.distance_in_points(dy_text, page))
        except ValueError as exc:
            QMessageBox.warning(self, "Move or duplicate", str(exc))
            return

        self.view.begin_snapshot()
        self.view.scene().clearSelection()
        made = 0
        for step_index in range(1, count + 1):
            offset = QPointF(step.x() * step_index, step.y() * step_index)
            for item in items:
                if duplicate:
                    copy = item.clone()
                    if copy is None:
                        continue
                    if isinstance(copy, ImageItem):
                        copy.load_from_document(self.document)
                    copy.setPos(item.pos() + offset)
                    self.view.frame().add_markup(copy)
                    copy.setSelected(True)
                    made += 1
                elif step_index == count:
                    item.setPos(item.pos() + offset)
                    item.setSelected(True)
        self.recalculate()
        self.view.commit_snapshot("Duplicate along an offset" if duplicate
                                  else "Move by an offset")
        self.refresh_selection()
        self.status_hint.setText(
            f"Made {made} cop{'y' if made == 1 else 'ies'}" if duplicate
            else f"Moved {len(items)} markup(s)")

    def distance_in_points(self, text: str, page) -> float:
        """Read a typed distance as page points, honouring the page scale."""
        text = (text or "").strip()
        if not text or text in ("0", "0.0"):
            return 0.0
        try:
            quantity = parse_unit(text)
        except Exception:  # noqa: BLE001 - pint raises for unknown unit names
            quantity = None
        if quantity is None:
            raise ValueError(f"Could not read “{text}” as a distance.")
        try:
            if page.scale.is_calibrated():
                return float((quantity / page.scale.length(1.0)).to("dimensionless").magnitude)
            return float(quantity.to("mm").magnitude) * MM_TO_PT
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"“{text}” is not a length.") from exc

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
        return self.document.layer(name).visible

    def apply_layers(self) -> None:
        """Push layer visibility, locking and print flags onto every page."""
        for page in self.document.pages:
            if page.frame is not None:
                page.frame.apply_layers()
        self.layers_panel.rebuild()
        self.refresh_selection()

    def rename_layer(self, old: str, new: str) -> None:
        for page in self.document.pages:
            if page.frame is None:
                continue
            for item in page.frame.markups():
                if item.layer == old:
                    item.layer = new
        self.document.modified = True

    def move_selection_to_layer(self, name: str) -> None:
        items = self.selected_items()
        if not items:
            self.status_hint.setText("Select some markups first.")
            return
        self.view.begin_snapshot()
        for item in items:
            item.layer = name
        self.view.commit_snapshot("Change layer")
        self.apply_layers()
        self.status_hint.setText(f"Moved {len(items)} markup(s) to “{name}”")

    def replace_image(self, item) -> None:
        """Put a different picture in an image already on the page."""
        self.view.begin_snapshot(self.view.involved_frames(item))
        if self.load_image_into(item):
            self.view.commit_snapshot("Replace image")
            self.refresh_selection()

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
        workspace.declare(self.declared_names())
        workspace.begin_pass()
        # One pass, strictly top-left to bottom-right across every page: a value
        # has to be defined above (or to the left of) whatever uses it, so moving
        # a region really does change what resolves — as it does in SMath.
        for page in self.document.pages:
            if page.frame is None:
                continue
            for item in page.frame.ordered_markups():
                item.refresh(workspace, page)
        self.variables_panel.rebuild(workspace)
        self.markups_panel.rebuild(self.document)
        self.refresh_problems()
        if self.view.active_table is not None:
            self.refresh_formula_bar(self.view.active_table)
        # The independent check runs once the typing stops, so that a sheet is
        # never left unverified without anybody being told.
        self._verify_timer.start()

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
            detach(block)
            for piece in pieces:
                self.view.frame().add_markup(piece)
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
        # Several lines in one region is a block, so Enter inside it makes
        # another line rather than another region.
        merged = MathItem("\n".join(block.source.rstrip() for block in blocks),
                          block=True)
        merged.style = first.style.copy()
        merged.digits = first.digits
        merged.number_format = first.number_format
        merged.author = first.author
        merged.layer = first.layer
        merged.setPos(first.pos())
        merged.setZValue(first.zValue())
        self.view.begin_snapshot()
        for block in blocks:
            detach(block)
        self.view.frame().add_markup(merged)
        self.recalculate()
        self.view.commit_snapshot("Merge calculations")
        self.view.scene().clearSelection()
        merged.setSelected(True)
        self.refresh_selection()

    def declared_names(self) -> set[str]:
        """Every name the document assigns, gathered before anything evaluates."""
        names: set[str] = set()
        for page in self.document.pages:
            if page.frame is None:
                continue
            for item in page.frame.markups():
                collect = getattr(item, "declared_names", None)
                if callable(collect):
                    names |= collect()
        return names

    def verify_document(self, quiet: bool = False):
        """Re-derive every number in the document and report the differences.

        The live pass is incremental and evaluates in reading order, which is
        what makes it pleasant to type into. This is the opposite: a clean
        workspace, the whole document from its source, and a comparison with
        what is on the page.
        """
        from ..core.verify import verify_document as run_check

        result = run_check(self.document)
        self._verification = result
        self.refresh_problems()
        self.status_hint.setText(result.summary())
        if not quiet and not result.ok:
            self.problems_panel.show()
            self.problems_panel.raise_()
        return result

    def _verify_quietly(self) -> None:
        """The background check, after the document has been left alone."""
        try:
            self.verify_document(quiet=True)
        except Exception as exc:                      # noqa: BLE001
            # A check that crashes must never take the document down with it.
            self.status_hint.setText(f"The check could not run: {exc}")

    def refresh_problems(self) -> None:
        from ..core.problems import collect_problems, summarise

        problems = collect_problems(self.document)
        verification = getattr(self, "_verification", None)
        if verification is not None:
            problems = problems + verification.problems
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
        self.bookmarks_panel.rebuild(self.document)

    # ==================================================================
    # bookmarks
    # ==================================================================
    def add_bookmark_here(self) -> None:
        """Bookmark the page and place the reader is looking at."""
        if self.view.busy_typing():
            # Ctrl+B belongs to the words being typed, not to the bookmarks.
            self.toggle_bold()
            return
        index = self.current_index
        page = self.document.pages[index]
        anchor = self.view.pointer_scene_pos()
        y = 0.0
        if anchor is not None and page.frame is not None:
            y = max(page.frame.mapFromScene(anchor).y(), 0.0)
        suggestion = page.label or self._nearby_heading(page, y) or f"Page {index + 1}"
        title, accepted = QInputDialog.getText(self, "Add bookmark", "Name",
                                               text=suggestion)
        if not accepted:
            return
        self.document.add_bookmark(title, index, y)
        self.bookmarks_changed()
        self.status_hint.setText(f"Bookmarked “{title.strip() or suggestion}”")

    @staticmethod
    def _nearby_heading(page, y: float) -> str:
        """The nearest piece of text above the spot, as a name to offer."""
        if page.frame is None:
            return ""
        best = ""
        best_distance = 200.0
        for item in page.frame.markups():
            text = getattr(item, "text", None)
            if not callable(text):
                continue
            written = text().strip().split("\n")[0][:60]
            if not written:
                continue
            distance = abs(item.pos().y() - y)
            if distance < best_distance:
                best, best_distance = written, distance
        return best

    def bookmark_page(self, index: int) -> None:
        """Bookmark a page from the pages panel, top of the page."""
        index = self.page_index(index)
        page = self.document.pages[index]
        suggestion = page.label or self._nearby_heading(page, 0.0) or f"Page {index + 1}"
        title, accepted = QInputDialog.getText(self, "Add bookmark", "Name",
                                               text=suggestion)
        if not accepted or not title.strip():
            return
        self.document.add_bookmark(title.strip(), index, 0.0)
        self.bookmarks_changed()
        self.status_hint.setText(f"Bookmarked “{title.strip()}”")

    def autosize_text(self) -> None:
        """Alt+Z: bring a text box or callout back in around its words."""
        items = [item for item in self.selected_items()
                 if hasattr(item, "size_to_text")]
        editing = self.view.editing_item()
        if not items and editing is not None and hasattr(editing, "size_to_text"):
            items = [editing]
        if not items:
            return
        self.view.begin_snapshot(self.view.involved_frames(*items))
        for item in items:
            item.size_to_text()
        self.view.commit_snapshot("Auto-size text box")

    def edit_preferences(self) -> None:
        """The settings that stay the same whatever document is open."""
        from . import preferences as prefs_module

        dialog = dialogs.PreferencesDialog(prefs_module.current(), self)
        if dialog.exec() != dialogs.QDialog.Accepted:
            return
        prefs_module.apply(dialog.result_preferences())
        self.view.viewport().update()
        self.status_hint.setText("Preferences saved")

    def toggle_bold(self) -> None:
        """Bold the text being typed, which is what Ctrl+B means in text."""
        item = self.view.editing_item()
        if item is None or not hasattr(item, "style"):
            return
        self.view.begin_snapshot(self.view.involved_frames(item))
        item.style.bold = not item.style.bold
        if hasattr(item, "apply_style"):
            item.apply_style()
        item.touch()
        item.update()
        self.view.commit_snapshot("Bold")

    def bookmarks_changed(self) -> None:
        self.bookmarks_panel.rebuild(self.document)
        self._refresh_all_scenes()
        self.mark_modified()

    def go_to_bookmark(self, index: int, y: float = 0.0) -> None:
        """Show the page a bookmark points at, at the place it points to."""
        self.go_to_page(index)
        page = self.document.pages[index] if 0 <= index < len(self.document.pages) else None
        if page is not None and page.frame is not None and y:
            self.view.centerOn(page.frame.mapToScene(QPointF(0, y))
                               + QPointF(page.setup.width_pt / 2, 0))

    def insert_contents_block(self) -> None:
        """Put a contents block on the page, listing the bookmarks."""
        self.select_tool("contents")
        self.status_hint.setText(
            "Drag out where the contents should go — it lists the bookmarks, "
            "and each line goes to its page")

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
        if not self.cell_name.hasFocus():
            self.cell_name.setText(table.name_for(row, col))
        if not self.formula_edit.hasFocus():
            self.formula_edit.setText(table.sheet.raw(row, col))
        cell = table.sheet.cells.get((row, col))
        if cell is not None and cell.error:
            self.cell_value.setText(cell.error)
            self.cell_value.setStyleSheet("color:#c92a2a;")
        else:
            self.cell_value.setText(table.sheet.display_text(row, col))
            self.cell_value.setStyleSheet("color:#3c5a86;")

    def commit_cell_name(self) -> None:
        """Publish (or stop publishing) the current cell under a typed name."""
        table = self.view.active_table
        if table is None:
            return
        row, col = table.current
        wanted = self.cell_name.text().strip()
        if wanted == table.name_for(row, col):
            return
        if wanted:
            problem = name_problem(wanted, self.declared_names() - table.declared_names())
            if problem:
                QMessageBox.warning(self, "Name this cell", problem)
                self.cell_name.setText(table.name_for(row, col))
                return
        self.view.begin_snapshot()
        table.set_cell_name(wanted, row, col)
        self.recalculate()
        self.view.commit_snapshot("Name a cell" if wanted else "Unname a cell")
        self.status_hint.setText(
            f"{table.current_ref()} is published as {wanted}" if wanted
            else f"{table.current_ref()} is no longer published")

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

    def toggle_item_snap(self, on: bool) -> None:
        self.document.settings.snap_to_items = on

    def toggle_margins(self, on: bool) -> None:
        self.document.settings.show_margins = on
        self._refresh_all_scenes()

    def refresh_icons(self) -> None:
        """Redraw every icon in the colours of the theme now in use."""
        for action, name in self._icon_names.items():
            action.setIcon(icon(name))
        for dock in self.panels:
            bar = dock.titleBarWidget()
            if hasattr(bar, "refresh_icons"):
                bar.refresh_icons()
        self.markups_panel.rebuild(self.document)
        self.problems_panel.rebuild(getattr(self.problems_panel, "_problems", []))

    def toggle_theme(self, dark: bool) -> None:
        from ..app import apply_theme
        from ..theme import CANVAS, DARK, LIGHT

        theme = DARK if dark else LIGHT
        application = QApplication.instance()
        if application is not None:
            apply_theme(application, theme)
        if self.scene is not None:
            self.scene.set_canvas_colour(CANVAS[theme])
        self.refresh_icons()
        self._refresh_all_scenes()
        self.status_hint.setText("Dark theme" if dark else "Light theme")

    def _refresh_all_scenes(self) -> None:
        if self.scene is not None:
            self.scene.update()

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
                row = item.result_at(item.mapFromScene(scene_pos))
                if row < 0:
                    row = next((i for i, r in enumerate(item.rows)
                                if r.result is not None), -1)
                if row >= 0:
                    menu.addAction("Show this result in…",
                                   lambda r=row: self.view.open_unit_editor(item, r))
                if not item.single_line:
                    menu.addAction(self.act_split_lines)
                turn = menu.addAction("Keep as one block")
                turn.setCheckable(True)
                turn.setChecked(item.block)
                turn.setToolTip("A block holds several lines and Enter makes a "
                                "new one.\nA line is one line, and Enter opens "
                                "the next line below it.")
                turn.toggled.connect(self.set_block_kind)
                if len([i for i in self.selected_items() if isinstance(i, MathItem)]) > 1:
                    menu.addAction(self.act_merge_lines)
                scope = menu.addAction("Self-contained block")
                scope.setCheckable(True)
                scope.setChecked(item.local_scope)
                scope.setEnabled(item.block)
                scope.setToolTip(
                    "Keep this block's own names inside it. It can still read\n"
                    "anything the document defines above it.")
                scope.toggled.connect(self.set_block_scope)
            if isinstance(item, ImageItem):
                menu.addAction("Change colours…", lambda: self.recolour_item(item))
            if isinstance(item, PlotItem):
                menu.addAction("Edit plot…", lambda: self.edit_plot(item))
            if isinstance(item, TableItem):
                menu.addAction("Edit table", lambda: self.view.activate_table(item))
                menu.addAction("Named cells…", lambda: self.edit_named_cells(item))
                menu.addAction("Name this table…", lambda: self.name_table(item))
                menu.addSeparator()
                menu.addAction("Insert row above", lambda: self._table_op(item, "row_above"))
                menu.addAction("Insert row below", lambda: self._table_op(item, "row_below"))
                menu.addAction("Insert column left", lambda: self._table_op(item, "col_left"))
                menu.addAction("Insert column right", lambda: self._table_op(item, "col_right"))
                menu.addAction("Delete row", lambda: self._table_op(item, "del_row"))
                menu.addAction("Delete column", lambda: self._table_op(item, "del_col"))
                menu.addAction("Autofit columns", lambda: self._table_op(item, "autofit"))
            if isinstance(item, RectItem) and item.kind in SIZED_SHAPES:
                menu.addAction("Set exact size…",
                               lambda: self.set_rectangle_size(item))
                show = menu.addAction("Show its size")
                show.setCheckable(True)
                show.setChecked(item.show_size)
                show.toggled.connect(lambda on: self.set_size_visible(item, on))
            if isinstance(item, MeasureItem):
                menu.addAction("Type on it…", lambda: self.edit_measure_text(item))
                straight = menu.addAction("Text in line with it")
                straight.setCheckable(True)
                straight.setChecked(item.label_angle is None)
                straight.toggled.connect(
                    lambda on, i=item: self.set_label_angle(i, None if on else 0.0))
                menu.addAction("Page scale…", self.calibrate_dialog)
            if hasattr(item, "size_to_text"):
                menu.addAction(self.act_autosize)
            menu.addSeparator()
            if len([i for i in self.selected_items() if isinstance(i, MarkupItem)]) > 1:
                menu.addAction(self.act_group)
            if any(getattr(i, "group", "") for i in self.selected_items()):
                menu.addAction(self.act_ungroup)
            menu.addAction("Set as default", lambda: self.set_as_default(item))
            menu.addAction("Add to a tool set…", lambda: self.add_to_toolset(item))
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
            menu.addAction(self.act_array)
            menu.addAction(self.act_lock)
        else:
            menu.addAction(self.act_paste)
            menu.addAction(self.act_paste_here)
            menu.addSeparator()
            insert = menu.addMenu("Insert here")
            for key in ("math", "table", "plot", "text", "callout", "stamp", "image"):
                tool = TOOL_MAP[key]
                insert.addAction(icon(tool.icon), tool.label,
                                 lambda _c=False, k=key, p=scene_pos: self._insert_at(k, p))
            menu.addSeparator()
            menu.addAction(self.act_page_setup)
            menu.addAction(self.act_scale)
            menu.addAction(self.act_select_all)
        return menu

    def set_block_kind(self, on: bool) -> None:
        """Turn a calculation line into a block, or a block back into a line."""
        items = [i for i in self.selected_items() if isinstance(i, MathItem)]
        if not items:
            return
        self.view.begin_snapshot()
        for item in items:
            item.block = bool(on)
            if not on:
                item.local_scope = False
            item.local_values.clear()
        self.recalculate()
        self.view.commit_snapshot("Calculation kind")
        self.refresh_selection()

    def set_block_scope(self, on: bool) -> None:
        """Self-contain the selected calculations, or open them up again."""
        blocks = [i for i in self.selected_items()
                  if isinstance(i, MathItem) and i.block]
        if not blocks:
            return
        self.view.begin_snapshot()
        for block in blocks:
            block.local_scope = bool(on)
            block.local_values.clear()
        self.recalculate()
        self.view.commit_snapshot("Self-contained block" if on
                                  else "Block defines for the document")
        self.refresh_selection()
        self.status_hint.setText(
            "This block keeps its names to itself" if on
            else "This block defines for the whole document")

    def _insert_at(self, key: str, scene_point: QPointF) -> None:
        """Put a new markup on the page under *scene_point*."""
        tool = TOOL_MAP[key]
        frame = self.view.frame_at(scene_point) or self.view.frame()
        point = frame.mapFromScene(scene_point)
        self.view.begin_snapshot()
        item = tool.factory()
        self.apply_default_style(item)
        item.author = self.document.settings.default_author or self.document.author
        width, height = self.view._default_size(item)
        if (hasattr(item, "set_local_rect") and not isinstance(item, (TableItem, MathItem))):
            item.set_local_rect(QRectF(0, 0, width, height))
        if isinstance(item, ImageItem) and not self.load_image_into(item):
            return
        frame.add_markup(item, point)
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

    # ==================================================================
    # redaction
    # ==================================================================
    def redaction_items(self) -> list[tuple]:
        from ..items.shapes import RectItem
        found = []
        for index, page in enumerate(self.document.pages):
            if page.frame is None:
                continue
            for item in page.frame.markups():
                if isinstance(item, RectItem) and item.kind == "redact":
                    found.append((index, page, item))
        return found

    def apply_redactions(self) -> None:
        """Burn every redaction box into the page and delete what it covers."""
        targets = self.redaction_items()
        if not targets:
            QMessageBox.information(
                self, "Apply redactions",
                "There are no redaction boxes in this document.\n\n"
                "Draw one with the Redact tool first — until it is applied it only "
                "hides the content, it does not remove it.")
            return
        answer = QMessageBox.warning(
            self, "Apply redactions",
            f"Permanently remove everything under {len(targets)} redaction box"
            f"{'es' if len(targets) != 1 else ''}?\n\n"
            "The imported page pixels underneath are overwritten and markups that "
            "sit entirely inside a box are deleted. Markups that only partly overlap "
            "one are left alone — check those yourself.\n\n"
            "This cannot be undone.",
            QMessageBox.Yes | QMessageBox.Cancel)
        if answer != QMessageBox.Yes:
            return

        removed = 0
        by_page: dict[int, list] = {}
        for index, page, item in targets:
            by_page.setdefault(index, []).append((page, item))
        for index, entries in by_page.items():
            page = entries[0][0]
            boxes = [item.sceneBoundingRect() for _page, item in entries]
            self._burn_into_background(page, boxes)
            removed += self._flatten_redactions(page, [item for _page, item in entries], boxes)
        self.document.modified = True
        self.recalculate()
        self.undo_stack.clear()          # the pixels are gone; undo would lie
        self.status_hint.setText(
            f"Applied {len(targets)} redaction(s); removed {removed} covered markup(s)")

    def _burn_into_background(self, page, boxes: list) -> None:
        """Paint the boxes into the page's background image, destroying it."""
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        from PySide6.QtGui import QImage, QPainter as _Painter

        data = self.document.asset(page.background_key)
        if not data:
            return
        image = QImage()
        if not image.loadFromData(QByteArray(data)):
            return
        scale_x = image.width() / max(page.width_pt, 1.0)
        scale_y = image.height() / max(page.height_pt, 1.0)
        painter = _Painter(image)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#000000"))
        for box in boxes:
            painter.drawRect(QRectF(box.x() * scale_x, box.y() * scale_y,
                                    box.width() * scale_x, box.height() * scale_y))
        painter.end()
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, "PNG")
        page.background_key = self.document.add_asset(bytes(buffer.data()), "png")
        if page.frame is not None:
            page.frame._background = None
            page.frame.load_background()
            page.frame.update()

    def _flatten_redactions(self, page, items: list, boxes: list) -> int:
        """Delete what the boxes fully cover and leave a locked black rectangle."""
        frame = page.frame
        if frame is None:
            return 0
        removed = 0
        for other in list(frame.markups()):
            if other in items:
                continue
            rect = other.sceneBoundingRect()
            if any(box.contains(rect) for box in boxes):
                frame.remove_markup(other)
                removed += 1
        for item in items:
            item.kind = "redact"
            item.style.fill = "#000000"
            item.style.fill_opacity = 1.0
            item.style.stroke = "#000000"
            item.style.opacity = 1.0
            item.label = "Redacted"
            item.comment = "Applied redaction — the content underneath was removed."
            item.set_locked(True)
            item.update()
        return removed

    def edit_header_footer(self) -> None:
        """Straight to the header and footer, logo and all."""
        self.document_properties(tab="header")

    def document_properties(self, tab: str = "") -> None:
        dialog = dialogs.DocumentPropertiesDialog(self.document, self)
        if tab:
            dialog.show_tab(tab)
        if dialog.exec() == dialogs.QDialog.Accepted:
            dialog.apply()
            self.act_grid.setChecked(self.document.settings.show_grid)
            self.act_snap.setChecked(self.document.settings.snap_to_grid)
            self.act_snap_items.setChecked(self.document.settings.snap_to_items)
            self.act_margins.setChecked(self.document.settings.show_margins)
            self._refresh_all_scenes()
            self.update_title()

    def show_shortcuts(self) -> None:
        """F1 opens the one shortcut window there is."""
        self.edit_shortcuts()

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
