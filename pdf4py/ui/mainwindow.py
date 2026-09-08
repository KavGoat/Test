"""The main window: menus, toolbars, panels, and canvas."""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (QApplication, QDockWidget, QFileDialog, QMainWindow,
                               QMessageBox, QWidget)

from ..document import DocumentError, PdfDocument
from . import icons
from .bookmarks import BookmarkPanel
from .markuplist import MarkupListPanel
from .pagelist import PageList
from .pageview import (ARROW, CLOUD, ELLIPSE, HIGHLIGHT, INK, LINE, NOTE,
                       POLYGON, RECTANGLE, SELECT, TEXT, PageView)
from .properties import PropertyPanel

APP_NAME = "PDF4Py"
PDF_FILTER = "PDF documents (*.pdf);;All files (*)"


class MainWindow(QMainWindow):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.document = PdfDocument()
        self.view = PageView(self.document, self)
        self.pages = PageList(self.document, self)
        self.properties = PropertyPanel(self)
        self.bookmarks = BookmarkPanel(self.document, self)
        self.markup_list = MarkupListPanel(self.document, self)
        self.setCentralWidget(self.view)
        self.setWindowIcon(icons.app_icon())
        self.resize(1280, 860)

        # Pages dock (left)
        pages_dock = QDockWidget("Pages", self)
        pages_dock.setObjectName("pages")
        pages_dock.setWidget(self.pages)
        pages_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        pages_dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable
                               | QDockWidget.DockWidgetClosable)
        self.addDockWidget(Qt.LeftDockWidgetArea, pages_dock)

        # Properties dock (right)
        props_dock = QDockWidget("Properties", self)
        props_dock.setObjectName("properties")
        props_dock.setWidget(self.properties)
        props_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        props_dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable
                               | QDockWidget.DockWidgetClosable)
        self.addDockWidget(Qt.RightDockWidgetArea, props_dock)

        # Bookmarks dock (right, tabbed with properties)
        bookmarks_dock = QDockWidget("Bookmarks", self)
        bookmarks_dock.setObjectName("bookmarks")
        bookmarks_dock.setWidget(self.bookmarks)
        bookmarks_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        bookmarks_dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable
                                   | QDockWidget.DockWidgetClosable)
        self.tabifyDockWidget(props_dock, bookmarks_dock)

        # Markups list dock (bottom)
        markups_dock = QDockWidget("Markups", self)
        markups_dock.setObjectName("markups-list")
        markups_dock.setWidget(self.markup_list)
        markups_dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea
                                     | Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        markups_dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable
                                 | QDockWidget.DockWidgetClosable)
        self.addDockWidget(Qt.BottomDockWidgetArea, markups_dock)

        # Keep track of dock widgets for View menu
        self._docks = {
            "Pages": pages_dock,
            "Properties": props_dock,
            "Bookmarks": bookmarks_dock,
            "Markups": markups_dock,
        }

        self._build_actions()
        self._connect_signals()
        self.update_title()
        self.statusBar().showMessage("Open a PDF to start.")

    def _connect_signals(self) -> None:
        self.pages.page_chosen.connect(self.show_page)
        self.view.edited.connect(self.on_edited)
        self.view.selection.connect(self._on_selection_change)
        self.view.page_changed.connect(self._on_page_changed)
        self.view.message.connect(lambda text: self.statusBar().showMessage(text, 4000))

        self.properties.colour_changed.connect(self._set_stroke_colour)
        self.properties.fill_changed.connect(self._set_fill_colour)
        self.properties.border_width_changed.connect(self._set_border_width)
        self.properties.opacity_changed.connect(self._set_opacity)

        self.bookmarks.page_requested.connect(self.show_page)
        self.markup_list.markup_selected.connect(self._on_markup_list_select)

    # ---------------------------------------------------------------- actions

    def _build_actions(self) -> None:
        main_bar = self.addToolBar("Main")
        main_bar.setObjectName("main-toolbar")
        main_bar.setMovable(False)

        draw_bar = self.addToolBar("Draw")
        draw_bar.setObjectName("draw-toolbar")
        draw_bar.setMovable(False)

        file_menu = self.menuBar().addMenu("&File")
        edit_menu = self.menuBar().addMenu("&Edit")
        page_menu = self.menuBar().addMenu("&Pages")
        tool_menu = self.menuBar().addMenu("&Tools")
        markup_menu = self.menuBar().addMenu("&Markup")
        view_menu = self.menuBar().addMenu("&View")

        # File
        self.open_action = self._action("&Open...", icons.open_icon(), QKeySequence.Open,
                                        self.open_document, "Open a PDF")
        self.save_action = self._action("&Save", icons.save_icon(), QKeySequence.Save,
                                        self.save, "Save the document")
        self.save_as_action = self._action("Save &As...", None, QKeySequence.SaveAs,
                                           self.save_as, "Save under a new name")
        quit_action = self._action("&Quit", None, QKeySequence.Quit, self.close, "Quit")
        for action in (self.open_action, self.save_action, self.save_as_action):
            file_menu.addAction(action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)
        main_bar.addAction(self.open_action)
        main_bar.addAction(self.save_action)
        main_bar.addSeparator()

        # Edit
        self.undo_action = self._action("&Undo", None, QKeySequence.Undo,
                                        self.undo, "Take back the last change")
        self.redo_action = self._action("&Redo", None, QKeySequence.Redo,
                                        self.redo, "Do it again")
        self.delete_action_markup = self._action("&Delete Markup", None, "Delete",
                                                 self.delete_markups,
                                                 "Remove the selected markups")
        for action in (self.undo_action, self.redo_action):
            edit_menu.addAction(action)
            main_bar.addAction(action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.delete_action_markup)
        main_bar.addSeparator()

        # Pages
        self.insert_action = self._action("Insert Blank Page &After", icons.add_page_icon(),
                                          "Ctrl+Shift+A", self.insert_page,
                                          "Insert a blank page after this one")
        self.delete_page_action = self._action("&Delete Page", icons.delete_page_icon(),
                                               "Ctrl+Shift+D", self.delete_page,
                                               "Delete the page shown")
        self.rotate_cw_action = self._action("Rotate &Clockwise", icons.rotate_icon(),
                                             "Ctrl+Shift+R", self.rotate_page_cw,
                                             "Rotate the page 90 degrees clockwise")
        self.rotate_ccw_action = self._action("Rotate C&ounter-clockwise", None,
                                              "Ctrl+Shift+L", self.rotate_page_ccw,
                                              "Rotate the page 90 degrees counter-clockwise")
        for action in (self.insert_action, self.delete_page_action,
                       self.rotate_cw_action, self.rotate_ccw_action):
            page_menu.addAction(action)
        main_bar.addAction(self.insert_action)
        main_bar.addAction(self.delete_page_action)
        main_bar.addAction(self.rotate_cw_action)
        main_bar.addSeparator()

        # Tools
        tools_group = QActionGroup(self)
        tool_defs = [
            ("&Select", icons.select_icon(), "V", SELECT, "Move and select markups"),
            ("&Rectangle", icons.rectangle_icon(), "R", RECTANGLE, "Draw a rectangle"),
            ("&Line", icons.line_icon(), "L", LINE, "Draw a line"),
            ("&Arrow", icons.arrow_icon(), "A", ARROW, "Draw an arrow"),
            ("&Ellipse", icons.ellipse_icon(), "E", ELLIPSE, "Draw an ellipse"),
            ("&Polygon", icons.polygon_icon(), "P", POLYGON,
             "Click points, double-click to finish"),
            ("&Cloud", icons.cloud_icon(), "C", CLOUD, "Draw a revision cloud"),
            ("&Ink / Pen", icons.ink_icon(), "I", INK, "Draw freehand"),
            ("&Highlight", icons.highlight_icon(), "H", HIGHLIGHT, "Highlight an area"),
            ("&Text Box", icons.text_icon(), "T", TEXT, "Place a text box"),
            ("&Note", icons.note_icon(), "N", NOTE, "Place a sticky note"),
        ]

        self._tool_actions: dict[str, QAction] = {}
        for label, icon, shortcut, mode, tip in tool_defs:
            action = self._action(label, icon, shortcut,
                                  lambda m=mode: self.set_mode(m), tip)
            action.setCheckable(True)
            tools_group.addAction(action)
            tool_menu.addAction(action)
            draw_bar.addAction(action)
            self._tool_actions[mode] = action
        self._tool_actions[SELECT].setChecked(True)

        # Markup
        self.text_action = self._action("Edit &Text...", None, "F2", self.edit_text,
                                        "Rewrite what this markup says")
        self.group_action = self._action("&Group", None, "Ctrl+G", self.group_markups,
                                         "Make the selected markups move as one")
        self.ungroup_action = self._action("&Ungroup", None, "Ctrl+Shift+G",
                                           self.ungroup_markups,
                                           "Let these markups move on their own again")
        self.front_action = self._action("Bring to &Front", icons.order_front_icon(),
                                         "Ctrl+Shift+]", self.bring_to_front,
                                         "Bring markup to front")
        self.back_action = self._action("Send to &Back", icons.order_back_icon(),
                                        "Ctrl+Shift+[", self.send_to_back,
                                        "Send markup to back")
        for action in (self.text_action, self.group_action, self.ungroup_action):
            markup_menu.addAction(action)
        markup_menu.addSeparator()
        for action in (self.front_action, self.back_action):
            markup_menu.addAction(action)

        # View
        zoom_in = self._action("Zoom &In", icons.zoom_icon(True), QKeySequence.ZoomIn,
                               self.view.zoom_in, "Zoom in")
        zoom_out = self._action("Zoom &Out", icons.zoom_icon(False), QKeySequence.ZoomOut,
                                self.view.zoom_out, "Zoom out")
        fit = self._action("&Fit Page", icons.fit_icon(), "Ctrl+0",
                           self.view.fit_page, "Fit the whole page")
        for action in (zoom_in, zoom_out, fit):
            view_menu.addAction(action)
            main_bar.addAction(action)

        view_menu.addSeparator()
        panels_menu = view_menu.addMenu("&Panels")
        for name, dock in self._docks.items():
            panels_menu.addAction(dock.toggleViewAction())

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
        self.statusBar().showMessage(f"Opening {os.path.basename(path)}...")
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
        self.view.show_fitted(0)
        self.bookmarks.reload()
        self.markup_list.reload()
        self.update_enabled()
        self.update_title()
        self.statusBar().showMessage(self._opened_message(path), 8000)
        return True

    def _opened_message(self, path: str) -> str:
        name = os.path.basename(path)
        pages = self.document.page_count
        if self.document.repaired:
            return (f"{name} — {pages} page(s). The file's structure is damaged; "
                    "it was repaired to open it. Save As writes a clean copy.")
        return f"{name} — {pages} page(s)."

    def save(self) -> bool:
        if self.document.path is None:
            return self.save_as()
        self.statusBar().showMessage("Saving...")
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            reloaded = self.document.save()
        except DocumentError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return False
        finally:
            QGuiApplication.restoreOverrideCursor()
        if reloaded:
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
        self.statusBar().showMessage("Saving...")
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
        self.view._syncing = True
        self.view.index = index
        if self.view._page_rects:
            self.view._scroll_to_page(index)
        else:
            self.view.show_page(index)
        self.view._syncing = False
        if self.pages.currentRow() != index:
            blocked = self.pages.blockSignals(True)
            self.pages.setCurrentRow(index)
            self.pages.blockSignals(blocked)
        self.bookmarks.set_current_page(index)
        self.update_enabled()

    def _on_page_changed(self, index: int) -> None:
        """Scroll triggered a page change."""
        if self.pages.currentRow() != index:
            blocked = self.pages.blockSignals(True)
            self.pages.setCurrentRow(index)
            self.pages.blockSignals(blocked)
        self.bookmarks.set_current_page(index)
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
        self.view.refresh()
        self.view._syncing = True
        self.view.index = index
        if self.view._page_rects:
            self.view._scroll_to_page(index)
        self.view._syncing = False
        self.pages.setCurrentRow(index)
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
        self.view.refresh()
        self.view._syncing = True
        self.view.index = landing
        if self.view._page_rects:
            self.view._scroll_to_page(landing)
        self.view._syncing = False
        self.pages.setCurrentRow(landing)
        self.on_edited(refresh_thumbnail=False)
        self.statusBar().showMessage(f"Deleted page {index + 1}.", 4000)

    def rotate_page_cw(self) -> None:
        if self.document.is_empty:
            return
        try:
            self.document.rotate_page(self.view.index, 90)
        except DocumentError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        self.view.refresh()
        self.on_edited()
        self.statusBar().showMessage("Page rotated clockwise.", 4000)

    def rotate_page_ccw(self) -> None:
        if self.document.is_empty:
            return
        try:
            self.document.rotate_page(self.view.index, 270)
        except DocumentError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        self.view.refresh()
        self.on_edited()
        self.statusBar().showMessage("Page rotated counter-clockwise.", 4000)

    # ------------------------------------------------------------------ tools

    def set_mode(self, mode: str) -> None:
        self.view.set_mode(mode)
        if mode in self._tool_actions:
            self._tool_actions[mode].setChecked(True)
        tips = {
            SELECT: "Drag a markup to move it, or its handles to resize or reshape it.",
            RECTANGLE: "Drag on the page to draw a rectangle.",
            LINE: "Drag to draw a line.",
            ARROW: "Drag to draw an arrow.",
            ELLIPSE: "Drag to draw an ellipse.",
            POLYGON: "Click to add points. Double-click to finish the polygon.",
            CLOUD: "Drag to draw a revision cloud.",
            INK: "Draw freehand on the page.",
            HIGHLIGHT: "Drag to highlight an area.",
            TEXT: "Drag to place a text box.",
            NOTE: "Click to place a sticky note.",
        }
        self.statusBar().showMessage(tips.get(mode, ""), 4000)

    # ------------------------------------------------------------ undo, redo

    def undo(self) -> None:
        self._step_back(self.document.undo(), "Nothing left to undo.")

    def redo(self) -> None:
        self._step_back(self.document.redo(), "Nothing to redo.")

    def _step_back(self, label: Optional[str], nothing: str) -> None:
        if label is None:
            self.statusBar().showMessage(nothing, 3000)
            return
        current = min(self.view.index, max(self.document.page_count - 1, 0))
        if self.pages.count() != self.document.page_count:
            self.pages.reload(current)
        else:
            self.pages.refresh_thumbnail(current)
        self.view.index = current
        self.view.refresh()
        self.markup_list.reload()
        self.update_title()
        self.update_enabled()
        self.statusBar().showMessage(f"{label} — undone." if label else "", 4000)

    # ---------------------------------------------------------------- markups

    def delete_markups(self) -> None:
        chosen = [item.xref for item in self.view.selected_items()]
        if not chosen:
            self.statusBar().showMessage("Select a markup to delete.", 4000)
            return
        page_idx = self.view.selected_items()[0].page_index
        removed = self.document.delete_markups(page_idx, chosen)
        if not removed:
            self.statusBar().showMessage("Those markups cannot be deleted.", 4000)
            return
        self.view.refresh()
        self.on_edited()
        self.statusBar().showMessage(
            f"Deleted {removed} markup{'s' if removed > 1 else ''}.", 4000)

    def edit_text(self) -> None:
        chosen = self.view.selected_items()
        item = chosen[0] if len(chosen) == 1 else None
        if item is None or not item.markup.editable_text:
            self.statusBar().showMessage(
                "Select a text box or a note to edit its text.", 4000)
            return
        self.view.edit_text(item.xref)

    def group_markups(self) -> None:
        xrefs = [item.xref for item in self.view.selected_items()]
        if len(xrefs) < 2:
            self.statusBar().showMessage(
                "Select two or more markups to group them.", 4000)
            return
        page_idx = self.view.selected_items()[0].page_index
        if not self.document.group(page_idx, xrefs):
            self.statusBar().showMessage("These markups cannot be grouped.", 4000)
            return
        self.view.refresh(xrefs[0])
        self.on_edited()
        self.statusBar().showMessage(f"Grouped {len(xrefs)} markups.", 4000)

    def ungroup_markups(self) -> None:
        chosen = self.view.selected_items()
        if not chosen:
            self.statusBar().showMessage("Select a grouped markup first.", 4000)
            return
        page_idx = chosen[0].page_index
        freed = self.document.ungroup(page_idx, chosen[0].xref)
        if not freed:
            self.statusBar().showMessage("That markup is not in a group.", 4000)
            return
        self.view.refresh(chosen[0].xref)
        self.on_edited()
        self.statusBar().showMessage(f"Ungrouped {freed} markups.", 4000)

    def bring_to_front(self) -> None:
        chosen = self.view.selected_items()
        if len(chosen) != 1:
            self.statusBar().showMessage("Select one markup to reorder.", 4000)
            return
        item = chosen[0]
        if self.document.bring_to_front(item.page_index, item.xref):
            self.view.refresh(item.xref)
            self.on_edited()
            self.statusBar().showMessage("Markup brought to front.", 4000)

    def send_to_back(self) -> None:
        chosen = self.view.selected_items()
        if len(chosen) != 1:
            self.statusBar().showMessage("Select one markup to reorder.", 4000)
            return
        item = chosen[0]
        if self.document.send_to_back(item.page_index, item.xref):
            self.view.refresh(item.xref)
            self.on_edited()
            self.statusBar().showMessage("Markup sent to back.", 4000)

    # --------------------------------------------------------- property edits

    def _set_stroke_colour(self, rgb: tuple) -> None:
        chosen = self.view.selected_items()
        if len(chosen) != 1:
            return
        item = chosen[0]
        if self.document.set_markup_colour(item.page_index, item.xref, stroke=rgb):
            self.view.refresh(item.xref)
            self.on_edited()

    def _set_fill_colour(self, rgb: tuple) -> None:
        chosen = self.view.selected_items()
        if len(chosen) != 1:
            return
        item = chosen[0]
        if self.document.set_markup_colour(item.page_index, item.xref, fill=rgb):
            self.view.refresh(item.xref)
            self.on_edited()

    def _set_border_width(self, width: float) -> None:
        chosen = self.view.selected_items()
        if len(chosen) != 1:
            return
        item = chosen[0]
        if self.document.set_markup_border_width(item.page_index, item.xref, width):
            self.view.refresh(item.xref)
            self.on_edited()

    def _set_opacity(self, opacity: float) -> None:
        chosen = self.view.selected_items()
        if len(chosen) != 1:
            return
        item = chosen[0]
        if self.document.set_markup_opacity(item.page_index, item.xref, opacity):
            self.view.refresh(item.xref)
            self.on_edited()

    # --------------------------------------------------------- selection sync

    def _on_selection_change(self) -> None:
        chosen = self.view.selected_items()
        if len(chosen) == 1:
            self.properties.set_markup(chosen[0].markup)
            self.markup_list.select_markup(chosen[0].page_index, chosen[0].xref)
        else:
            self.properties.set_markup(None)
        self.update_enabled()

    def _on_markup_list_select(self, page_index: int, xref: int) -> None:
        self.show_page(page_index)
        self.view.refresh(xref)

    # ------------------------------------------------------------------ state

    def on_edited(self, refresh_thumbnail: bool = True) -> None:
        if refresh_thumbnail:
            self.pages.refresh_thumbnail(self.view.index)
        self.markup_list.reload()
        self.update_title()
        self.update_enabled()

    def update_title(self) -> None:
        name = os.path.basename(self.document.path) if self.document.path else "Untitled"
        star = "*" if self.document.modified else ""
        self.setWindowTitle(f"{name}{star} — {APP_NAME}")

    def update_enabled(self) -> None:
        has_pages = not self.document.is_empty
        for action in (self.save_action, self.save_as_action, self.insert_action):
            action.setEnabled(has_pages)
        for mode, action in self._tool_actions.items():
            action.setEnabled(has_pages)
        self.delete_page_action.setEnabled(self.document.page_count > 1)
        self.rotate_cw_action.setEnabled(has_pages)
        self.rotate_ccw_action.setEnabled(has_pages)

        chosen = self.view.selected_items() if has_pages else []
        self.text_action.setEnabled(len(chosen) == 1 and chosen[0].markup.editable_text)
        self.group_action.setEnabled(len(chosen) > 1)
        self.ungroup_action.setEnabled(any(item.markup.leader for item in chosen))
        self.delete_action_markup.setEnabled(bool(chosen))
        self.front_action.setEnabled(len(chosen) == 1)
        self.back_action.setEnabled(len(chosen) == 1)

        self.undo_action.setEnabled(self.document.can_undo)
        self.redo_action.setEnabled(self.document.can_redo)
        self.undo_action.setText(f"&Undo {self.document.history.undo_label}".rstrip()
                                 if self.document.can_undo else "&Undo")
        self.redo_action.setText(f"&Redo {self.document.history.redo_label}".rstrip()
                                 if self.document.can_redo else "&Redo")

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
