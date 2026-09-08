"""The main window: menus, toolbar, page strip and canvas."""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (QApplication, QDockWidget, QFileDialog, QMainWindow,
                               QMessageBox, QWidget)

from ..document import DocumentError, PdfDocument
from . import icons
from .pagelist import PageList
from .pageview import RECTANGLE, SELECT, PageView

APP_NAME = "PDF4Py"
PDF_FILTER = "PDF documents (*.pdf);;All files (*)"


class MainWindow(QMainWindow):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.document = PdfDocument()
        self.view = PageView(self.document, self)
        self.pages = PageList(self.document, self)
        self.setCentralWidget(self.view)
        self.setWindowIcon(icons.app_icon())
        self.resize(1180, 820)

        dock = QDockWidget("Pages", self)
        dock.setObjectName("pages")
        dock.setWidget(self.pages)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

        self._build_actions()
        self.pages.page_chosen.connect(self.show_page)
        self.view.edited.connect(self.on_edited)
        self.view.message.connect(lambda text: self.statusBar().showMessage(text, 4000))
        self.update_title()
        self.statusBar().showMessage("Open a PDF to start.")

    # ---------------------------------------------------------------- actions

    def _build_actions(self) -> None:
        bar = self.addToolBar("Main")
        bar.setObjectName("main-toolbar")
        bar.setMovable(False)
        file_menu = self.menuBar().addMenu("&File")
        page_menu = self.menuBar().addMenu("&Pages")
        tool_menu = self.menuBar().addMenu("&Tools")
        view_menu = self.menuBar().addMenu("&View")

        self.open_action = self._action("&Open…", icons.open_icon(), QKeySequence.Open,
                                        self.open_document, "Open a PDF")
        self.save_action = self._action("&Save", icons.save_icon(), QKeySequence.Save,
                                        self.save, "Save the document")
        self.save_as_action = self._action("Save &As…", None, QKeySequence.SaveAs,
                                           self.save_as, "Save under a new name")
        quit_action = self._action("&Quit", None, QKeySequence.Quit, self.close, "Quit")
        for action in (self.open_action, self.save_action, self.save_as_action):
            file_menu.addAction(action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)
        bar.addAction(self.open_action)
        bar.addAction(self.save_action)
        bar.addSeparator()

        self.insert_action = self._action("Insert Blank Page &After", icons.add_page_icon(),
                                          "Ctrl+Shift+A", self.insert_page,
                                          "Insert a blank page after this one")
        self.delete_action = self._action("&Delete Page", icons.delete_page_icon(),
                                          "Ctrl+Shift+D", self.delete_page,
                                          "Delete the page shown")
        page_menu.addAction(self.insert_action)
        page_menu.addAction(self.delete_action)
        bar.addAction(self.insert_action)
        bar.addAction(self.delete_action)
        bar.addSeparator()

        self.select_action = self._action("&Move Markups", icons.select_icon(), "V",
                                          lambda: self.set_mode(SELECT),
                                          "Drag an existing markup to move it")
        self.rectangle_action = self._action("&Rectangle", icons.rectangle_icon(), "R",
                                             lambda: self.set_mode(RECTANGLE),
                                             "Drag on the page to draw a rectangle")
        group = QActionGroup(self)
        for action in (self.select_action, self.rectangle_action):
            action.setCheckable(True)
            group.addAction(action)
            tool_menu.addAction(action)
            bar.addAction(action)
        self.select_action.setChecked(True)
        bar.addSeparator()

        zoom_in = self._action("Zoom &In", icons.zoom_icon(True), QKeySequence.ZoomIn,
                               self.view.zoom_in, "Zoom in")
        zoom_out = self._action("Zoom &Out", icons.zoom_icon(False), QKeySequence.ZoomOut,
                                self.view.zoom_out, "Zoom out")
        fit = self._action("&Fit Page", icons.fit_icon(), "Ctrl+0",
                           self.view.fit_page, "Fit the whole page")
        for action in (zoom_in, zoom_out, fit):
            view_menu.addAction(action)
            bar.addAction(action)

        self.update_enabled()

    def _action(self, text, icon, shortcut, slot, tip) -> QAction:
        action = QAction(text, self)
        if icon is not None:
            action.setIcon(icon)
        if shortcut is not None:
            action.setShortcut(shortcut)
        action.setStatusTip(tip)
        action.setToolTip(tip)
        action.triggered.connect(slot)
        self.addAction(action)
        return action

    # ------------------------------------------------------------------- file

    def open_document(self) -> None:
        if not self.confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open PDF", "", PDF_FILTER)
        if path:
            self.load(path)

    def load(self, path: str) -> bool:
        self.statusBar().showMessage(f"Opening {os.path.basename(path)}…")
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            self.document.open(path)
        except DocumentError as exc:
            QGuiApplication.restoreOverrideCursor()
            self.statusBar().clearMessage()
            QMessageBox.warning(self, APP_NAME, str(exc))
            return False
        finally:
            if QGuiApplication.overrideCursor() is not None:
                QGuiApplication.restoreOverrideCursor()
        self.pages.reload(0)
        # Fits and draws in one pass: a big sheet is not rendered twice.
        self.view.show_fitted(0)
        self.update_enabled()
        self.update_title()
        self.update_enabled()
        self.statusBar().showMessage(self._opened_message(path), 8000)
        return True

    def _opened_message(self, path: str) -> str:
        name = os.path.basename(path)
        pages = self.document.page_count
        if self.document.repaired:
            # MuPDF's own complaints are kept off the console; this is the one
            # thing the user can act on — the file itself is damaged.
            return (f"{name} — {pages} page(s). The file's structure is damaged; "
                    "it was repaired to open it. Save As writes a clean copy.")
        return f"{name} — {pages} page(s)."

    def save(self) -> bool:
        if self.document.path is None:
            return self.save_as()
        self.statusBar().showMessage("Saving…")
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            reloaded = self.document.save()
        except DocumentError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return False
        finally:
            QGuiApplication.restoreOverrideCursor()
        if reloaded:
            # A rewritten file has new xrefs, so what is on screen is stale.
            self.view.refresh()
        self.update_title()
        self.statusBar().showMessage(f"Saved {os.path.basename(self.document.path)}.", 4000)
        return True

    def save_as(self) -> bool:
        if self.document.is_empty:
            return False
        path, _ = QFileDialog.getSaveFileName(self, "Save PDF As",
                                              self.document.path or "", PDF_FILTER)
        if not path:
            return False
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        self.statusBar().showMessage("Saving…")
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.document.save(path)
        except DocumentError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return False
        finally:
            QGuiApplication.restoreOverrideCursor()
        self.update_title()
        self.statusBar().showMessage(f"Saved {os.path.basename(path)}.", 4000)
        return True

    # ------------------------------------------------------------------ pages

    def show_page(self, index: int) -> None:
        self.view.show_page(index)
        if self.pages.currentRow() != self.view.index:
            blocked = self.pages.blockSignals(True)
            self.pages.setCurrentRow(self.view.index)
            self.pages.blockSignals(blocked)
        self.update_enabled()

    def insert_page(self) -> None:
        if self.document.is_empty:
            return
        index = self.view.index + 1
        try:
            self.document.insert_page(index)
        except DocumentError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        self.pages.insert_row(index)
        self.pages.setCurrentRow(index)
        self.show_page(index)
        self.on_edited(refresh_thumbnail=False)
        self.statusBar().showMessage(f"Inserted a blank page at {index + 1}.", 4000)

    def delete_page(self) -> None:
        if self.document.is_empty:
            return
        index = self.view.index
        try:
            self.document.delete_page(index)
        except DocumentError as exc:
            QMessageBox.information(self, APP_NAME, str(exc))
            return
        landing = min(index, self.document.page_count - 1)
        self.pages.remove_row(index)
        self.pages.setCurrentRow(landing)
        self.show_page(landing)
        self.on_edited(refresh_thumbnail=False)
        self.statusBar().showMessage(f"Deleted page {index + 1}.", 4000)

    # ------------------------------------------------------------------ tools

    def set_mode(self, mode: str) -> None:
        self.view.set_mode(mode)
        (self.select_action if mode == SELECT else self.rectangle_action).setChecked(True)
        self.statusBar().showMessage(
            "Drag a markup to move it." if mode == SELECT
            else "Drag on the page to draw a rectangle.", 4000)

    # ------------------------------------------------------------------ state

    def on_edited(self, refresh_thumbnail: bool = True) -> None:
        if refresh_thumbnail:
            self.pages.refresh_thumbnail(self.view.index)
        self.update_title()
        self.update_enabled()

    def update_title(self) -> None:
        name = os.path.basename(self.document.path) if self.document.path else "Untitled"
        star = "*" if self.document.modified else ""
        self.setWindowTitle(f"{name}{star} — {APP_NAME}")

    def update_enabled(self) -> None:
        has_pages = not self.document.is_empty
        for action in (self.save_action, self.save_as_action, self.insert_action,
                       self.select_action, self.rectangle_action):
            action.setEnabled(has_pages)
        self.delete_action.setEnabled(self.document.page_count > 1)

    def confirm_discard(self) -> bool:
        if not self.document.modified:
            return True
        answer = QMessageBox.question(
            self, APP_NAME, "Save the changes to this document first?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save)
        if answer == QMessageBox.Cancel:
            return False
        if answer == QMessageBox.Save:
            return self.save()
        return True

    def closeEvent(self, event):
        if self.confirm_discard():
            event.accept()
        else:
            event.ignore()
