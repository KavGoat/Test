"""Main application window."""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence, QCloseEvent
from PySide6.QtWidgets import (
    QMainWindow, QMenuBar, QStatusBar, QFileDialog,
    QMessageBox, QApplication, QDockWidget, QLabel,
)

from ..core.document import Document, Region
from ..core.evaluator import EvalContext
from ..core.problems import ProblemCollector
from ..io.project import save_project, load_project
from .canvas import DocumentScene, DocumentCanvas
from .panels import VariablesPanel, FunctionsPanel, ProblemsPanel, ThumbnailPanel
from .toolbar import DrawingToolbar, ViewToolbar
from .dialogs import PageSetupDialog, DocumentPropertiesDialog, AboutDialog, CalcInputDialog
from ..items.calculation import CalculationItem
from ..items.table import TableItem
from ..items.plot import PlotItem


class MainWindow(QMainWindow):
    def __init__(self, file_path: Optional[str] = None):
        super().__init__()
        self.setWindowTitle("CalcForge")
        self.resize(1200, 850)

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

        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(120_000)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start()

        if file_path:
            self._open_file(file_path)

        self._recalculate()

    def _setup_menus(self):
        mb = self.menuBar()

        file_menu = mb.addMenu("&File")
        file_menu.addAction("&New", self._new_document, QKeySequence.StandardKey.New)
        file_menu.addAction("&Open...", self._open_dialog, QKeySequence.StandardKey.Open)
        file_menu.addAction("&Save", self._save, QKeySequence.StandardKey.Save)
        file_menu.addAction("Save &As...", self._save_as, QKeySequence("Ctrl+Shift+S"))
        file_menu.addSeparator()
        file_menu.addAction("E&xit", self.close, QKeySequence("Ctrl+Q"))

        edit_menu = mb.addMenu("&Edit")
        edit_menu.addAction("&Undo", self._undo, QKeySequence.StandardKey.Undo)
        edit_menu.addAction("&Redo", self._redo, QKeySequence.StandardKey.Redo)

        calc_menu = mb.addMenu("&Calculate")
        calc_menu.addAction("&Recalculate All", self._recalculate, QKeySequence("F9"))

        page_menu = mb.addMenu("&Page")
        page_menu.addAction("Page &Setup...", self._page_setup)
        page_menu.addAction("&Add Page", self._add_page)
        page_menu.addAction("&Document Properties...", self._doc_properties)

        help_menu = mb.addMenu("&Help")
        help_menu.addAction("&About CalcForge", self._about)

    def _setup_toolbars(self):
        self._draw_toolbar = DrawingToolbar(self)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._draw_toolbar)
        self._draw_toolbar.tool_selected.connect(self._on_tool_selected)

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

        self._scene.selectionChanged.connect(self._on_selection_changed)

    def _setup_statusbar(self):
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status_label = QLabel("Ready")
        self._status.addWidget(self._status_label, 1)
        self._problems_label = QLabel("")
        self._status.addPermanentWidget(self._problems_label)

    def _on_tool_selected(self, tool: str):
        self._canvas.current_tool = tool
        self._status_label.setText(f"Tool: {tool.title()}")

    def _on_selection_changed(self):
        items = self._scene.selectedItems()
        if len(items) == 1:
            from ..items.base import PageItem
            item = items[0]
            if isinstance(item, PageItem):
                self._status_label.setText(
                    f"Selected: {item.region.type} at page {item.region.page_index + 1}")

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
            elif isinstance(item, TableItem):
                item.evaluate(self._eval_ctx)
            elif isinstance(item, PlotItem):
                item.evaluate(self._eval_ctx)
        self._vars_panel.update_variables(self._eval_ctx)
        self._problems_panel.update_problems(self._problems)
        count = self._problems.error_count
        self._problems_label.setText(f"{count} error{'s' if count != 1 else ''}" if count else "")
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
        self._scene.selectionChanged.connect(self._on_selection_changed)
        self._thumb_panel.update_pages(len(self._document.pages))
        self._recalculate()
        self.setWindowTitle("CalcForge")

    def _open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "", "CalcForge files (*.cfx);;All files (*)")
        if path:
            self._open_file(path)

    def _open_file(self, path: str):
        try:
            self._document = load_project(path)
            self._file_path = path
            self._scene = DocumentScene(self._document)
            self._canvas.setScene(self._scene)
            self._canvas._scene = self._scene
            self._scene.selectionChanged.connect(self._on_selection_changed)
            self._thumb_panel.update_pages(len(self._document.pages))
            self._recalculate()
            self.setWindowTitle(f"CalcForge — {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open file:\n{e}")

    def _save(self):
        if self._file_path:
            self._save_to(self._file_path)
        else:
            self._save_as()

    def _save_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project", "", "CalcForge files (*.cfx)")
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
            self.setWindowTitle(f"CalcForge — {os.path.basename(path)}")
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
