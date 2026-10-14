"""Main application window — matching SMath Studio's layout."""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QCloseEvent
from PySide6.QtWidgets import (
    QMainWindow, QStatusBar, QFileDialog,
    QMessageBox, QLabel,
)

from ..core.document import Document, Region
from ..core.evaluator import EvalContext
from ..core.problems import ProblemCollector
from ..io.project import save_project, load_project
from .canvas import DocumentScene, DocumentCanvas
from .panels import VariablesPanel, FunctionsPanel, ProblemsPanel, ThumbnailPanel
from .toolbar import MathToolbar, ViewToolbar
from .dialogs import PageSetupDialog, DocumentPropertiesDialog, AboutDialog, CalcInputDialog
from ..items.calculation import CalculationItem
from ..items.text import TextItem
from ..items.plot import PlotItem

OPERATOR_MAP = {
    "op_assign": ":=",
    "op_eval": "=",
    "op_convert": "->",
    "op_plus": "+",
    "op_minus": "-",
    "op_mul": "*",
    "op_div": "/",
    "op_pow": "^",
    "op_sqrt": "sqrt(",
    "greek_alpha": "α",
    "greek_beta": "β",
    "greek_gamma": "γ",
    "greek_delta": "δ",
    "greek_pi": "π",
    "greek_sigma": "σ",
}


class MainWindow(QMainWindow):
    def __init__(self, file_path: Optional[str] = None):
        super().__init__()
        self.setWindowTitle("SMath Studio")
        self.resize(1000, 750)

        self._document = Document()
        self._eval_ctx = EvalContext()
        self._problems = ProblemCollector()
        self._file_path: Optional[str] = None

        self._scene = DocumentScene(self._document)
        self._canvas = DocumentCanvas(self._scene)
        self.setCentralWidget(self._canvas)

        self._setup_menus()
        self._setup_toolbars()
        self._setup_panels()
        self._setup_statusbar()
        self._connect_scene_signals()

        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(120_000)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start()

        if file_path:
            self._open_file(file_path)

        self._recalculate()

    def _connect_scene_signals(self):
        self._scene.selectionChanged.connect(self._on_selection_changed)
        self._scene.focusItemChanged.connect(self._on_focus_changed)

    def _setup_menus(self):
        mb = self.menuBar()

        file_menu = mb.addMenu("&File")
        file_menu.addAction("&New", self._new_document, QKeySequence.StandardKey.New)
        file_menu.addAction("&Open...", self._open_dialog, QKeySequence.StandardKey.Open)
        file_menu.addAction("&Save", self._save, QKeySequence.StandardKey.Save)
        file_menu.addAction("Save &As...", self._save_as, QKeySequence("Ctrl+Shift+S"))
        file_menu.addSeparator()
        file_menu.addAction("Page Set&up...", self._page_setup)
        file_menu.addSeparator()
        file_menu.addAction("E&xit", self.close, QKeySequence("Ctrl+Q"))

        edit_menu = mb.addMenu("&Edit")
        edit_menu.addAction("&Undo", self._undo, QKeySequence.StandardKey.Undo)
        edit_menu.addAction("&Redo", self._redo, QKeySequence.StandardKey.Redo)

        view_menu = mb.addMenu("&View")
        view_menu.addAction("Fit &Page", self._canvas.zoom_fit_page, QKeySequence("Ctrl+0"))
        view_menu.addAction("Fit &Width", self._canvas.zoom_fit_width, QKeySequence("Ctrl+1"))

        insert_menu = mb.addMenu("&Insert")
        insert_menu.addAction("&Math Region", self._insert_math, QKeySequence("Ctrl+M"))
        insert_menu.addAction("&Text Region", self._insert_text, QKeySequence("Ctrl+T"))
        insert_menu.addAction("&2D Plot", self._insert_plot)
        insert_menu.addSeparator()
        insert_menu.addAction("&Page Break", self._add_page)

        calc_menu = mb.addMenu("&Calculation")
        calc_menu.addAction("&Recalculate", self._recalculate, QKeySequence("F9"))

        tools_menu = mb.addMenu("&Tools")
        tools_menu.addAction("&Document Properties...", self._doc_properties)

        help_menu = mb.addMenu("&Help")
        help_menu.addAction("&About", self._about)

    def _setup_toolbars(self):
        self._math_toolbar = MathToolbar(self)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._math_toolbar)
        self._math_toolbar.insert_requested.connect(self._on_insert)

        self._view_toolbar = ViewToolbar(self)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._view_toolbar)
        self._view_toolbar.zoom_fit_page.connect(self._canvas.zoom_fit_page)
        self._view_toolbar.zoom_fit_width.connect(self._canvas.zoom_fit_width)

    def _setup_panels(self):
        self._vars_panel = VariablesPanel(self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._vars_panel)

        self._funcs_panel = FunctionsPanel(self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._funcs_panel)
        self.tabifyDockWidget(self._vars_panel, self._funcs_panel)
        self._vars_panel.raise_()

        self._problems_panel = ProblemsPanel(self)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._problems_panel)

        self._thumb_panel = ThumbnailPanel(self)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._thumb_panel)
        self._thumb_panel.page_selected.connect(self._scroll_to_page)
        self._thumb_panel.page_add_requested.connect(self._add_page_after)
        self._thumb_panel.page_delete_requested.connect(self._delete_page)
        self._thumb_panel.page_duplicate_requested.connect(self._duplicate_page)
        self._thumb_panel.update_pages(len(self._document.pages))

    def _setup_statusbar(self):
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status_label = QLabel("Ready")
        self._status.addWidget(self._status_label, 1)
        self._problems_label = QLabel("")
        self._status.addPermanentWidget(self._problems_label)

    def _on_focus_changed(self, new_focus, old_focus, reason):
        if isinstance(old_focus, CalculationItem):
            self._recalculate()

    def _on_insert(self, item_id: str):
        focused = self._scene.focusItem()
        if isinstance(focused, (CalculationItem, TextItem)) and focused.editing:
            text = OPERATOR_MAP.get(item_id)
            if text:
                focused.insert_text_at_cursor(text)
                return

        if item_id == "calculation":
            self._insert_math()
        elif item_id == "text":
            self._insert_text()
        elif item_id == "plot":
            self._insert_plot()

    def _insert_math(self):
        region = Region(
            type="calculation", x=40, y=40, width=100, height=24,
            page_index=0, data={"lines": [""]},
        )
        page = self._document.pages[0]
        page.add_region(region)
        item = self._scene.add_region_item(region)
        self._document.modified = True
        if item:
            item.setFocus()
            item.start_edit()

    def _insert_text(self):
        region = Region(
            type="text", x=40, y=40, width=200, height=30,
            page_index=0, data={"text": "", "font_size": 10},
        )
        page = self._document.pages[0]
        page.add_region(region)
        item = self._scene.add_region_item(region)
        self._document.modified = True
        if item:
            item.setFocus()
            item.start_edit()

    def _insert_plot(self):
        self._insert_region("plot", 300, 200, {
            "expressions": ["x^2"], "x_var": "x",
            "x_min": 0, "x_max": 10,
        })

    def _insert_region(self, rtype: str, w: float, h: float, data: dict):
        page_idx = 0
        region = Region(
            type=rtype, x=40, y=40, width=w, height=h,
            page_index=page_idx, data=data,
        )
        page = self._document.pages[page_idx]
        page.add_region(region)
        self._scene.add_region_item(region)
        self._document.modified = True
        self._recalculate()

    def _on_selection_changed(self):
        items = self._scene.selectedItems()
        if len(items) == 1:
            from ..items.base import PageItem
            item = items[0]
            if isinstance(item, PageItem):
                self._status_label.setText(
                    f"Region: {item.region.type} on page {item.region.page_index + 1}")

    def _recalculate(self):
        self._eval_ctx = EvalContext()
        self._problems.clear()
        for region in self._document.all_regions_sorted():
            item = self._scene.get_item(region.id)
            if isinstance(item, CalculationItem):
                results = item.evaluate(self._eval_ctx)
                for r in results:
                    if r.error:
                        self._problems.error(
                            r.error, page=region.page_index,
                            region_id=region.id, source="calculation")
            elif isinstance(item, PlotItem):
                item.evaluate(self._eval_ctx)
        self._vars_panel.update_variables(self._eval_ctx)
        self._problems_panel.update_problems(self._problems)
        count = self._problems.error_count
        self._problems_label.setText(
            f"{count} error{'s' if count != 1 else ''}" if count else "")
        self._scene.update()

    def _new_document(self):
        if self._document.modified:
            r = QMessageBox.question(
                self, "Unsaved changes",
                "Save changes before creating a new document?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No |
                QMessageBox.StandardButton.Cancel,
            )
            if r == QMessageBox.StandardButton.Cancel:
                return
            if r == QMessageBox.StandardButton.Yes:
                self._save()
        self._document = Document()
        self._file_path = None
        self._scene = DocumentScene(self._document)
        self._canvas.setScene(self._scene)
        self._canvas._scene = self._scene
        self._connect_scene_signals()
        self._thumb_panel.update_pages(len(self._document.pages))
        self._recalculate()
        self.setWindowTitle("SMath Studio")

    def _open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open", "", "SMath files (*.sm *.cfx);;All files (*)")
        if path:
            self._open_file(path)

    def _open_file(self, path: str):
        try:
            self._document = load_project(path)
            self._file_path = path
            self._scene = DocumentScene(self._document)
            self._canvas.setScene(self._scene)
            self._canvas._scene = self._scene
            self._connect_scene_signals()
            self._thumb_panel.update_pages(len(self._document.pages))
            self._recalculate()
            self.setWindowTitle(f"SMath Studio — {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open file:\n{e}")

    def _save(self):
        if self._file_path:
            self._save_to(self._file_path)
        else:
            self._save_as()

    def _save_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save", "", "SMath files (*.cfx)")
        if path:
            if not path.endswith(".cfx"):
                path += ".cfx"
            self._save_to(path)

    def _save_to(self, path: str):
        try:
            save_project(self._document, path)
            self._file_path = path
            self._document.modified = False
            self._document.file_path = path
            self.setWindowTitle(f"SMath Studio — {os.path.basename(path)}")
            self._status_label.setText(f"Saved to {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save:\n{e}")

    def _autosave(self):
        if self._file_path and self._document.modified:
            autosave_path = self._file_path + ".autosave"
            try:
                save_project(self._document, autosave_path)
            except Exception:
                pass

    def _page_setup(self):
        if not self._document.pages:
            return
        page = self._document.pages[0]
        dlg = PageSetupDialog(page.settings, self)
        if dlg.exec():
            page.settings = dlg.get_settings()
            self._scene.rebuild()
            self._recalculate()

    def _doc_properties(self):
        dlg = DocumentPropertiesDialog(
            self._document.title, self._document.author,
            self._document.project, self)
        if dlg.exec():
            self._document.title = dlg.doc_title
            self._document.author = dlg.doc_author
            self._document.project = dlg.doc_project
            self._document.modified = True

    def _add_page(self):
        self._document.add_page()
        self._scene.rebuild()
        self._thumb_panel.update_pages(len(self._document.pages))
        self._recalculate()

    def _add_page_after(self, index: int):
        self._document.add_page(index)
        self._scene.rebuild()
        self._thumb_panel.update_pages(len(self._document.pages))
        self._recalculate()

    def _delete_page(self, index: int):
        if len(self._document.pages) <= 1:
            return
        self._document.remove_page(index)
        self._scene.rebuild()
        self._thumb_panel.update_pages(len(self._document.pages))
        self._recalculate()

    def _duplicate_page(self, index: int):
        self._document.duplicate_page(index)
        self._scene.rebuild()
        self._thumb_panel.update_pages(len(self._document.pages))
        self._recalculate()

    def _scroll_to_page(self, index: int):
        y = self._scene.page_y_offset(index)
        from PySide6.QtCore import QRectF
        page = self._document.pages[index]
        self._canvas.ensureVisible(
            QRectF(0, y, page.settings.width, page.settings.height))

    def _undo(self):
        pass

    def _redo(self):
        pass

    def _about(self):
        AboutDialog(self).exec()

    def closeEvent(self, event: QCloseEvent):
        if self._document.modified:
            r = QMessageBox.question(
                self, "Unsaved changes",
                "Save changes before closing?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No |
                QMessageBox.StandardButton.Cancel,
            )
            if r == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if r == QMessageBox.StandardButton.Yes:
                self._save()
        event.accept()
