"""The main window: menus, toolbars, panels, and canvas."""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox,
                               QDockWidget, QFileDialog, QFormLayout, QInputDialog,
                               QMainWindow, QMessageBox, QPushButton, QSpinBox,
                               QWidget)

from ..autosave import Autosave
from ..document import PAPER_SIZES, STAMP_NAMES, DocumentError, PdfDocument
from . import icons
from .bookmarks import BookmarkPanel
from .markuplist import MarkupListPanel
from .pagelist import PageList
from .pageview import (ARROW, CLOUD, ELLIPSE, ERASER, HIGHLIGHT, INK, LASSO,
                       LINE, MEASURE_ANGLE, MEASURE_AREA, MEASURE_LENGTH,
                       NOTE, POLYGON, POLYLINE, RECTANGLE, REDACTION, SELECT,
                       STAMP, TEXT, PageView)
from .properties import PropertyPanel

APP_NAME = "PDF4Py"
PDF_FILTER = "PDF documents (*.pdf);;All files (*)"
IMAGE_FILTER = "PNG images (*.png);;JPEG images (*.jpg *.jpeg);;All files (*)"
CSV_FILTER = "CSV files (*.csv);;All files (*)"

_MARKFORGE_STYLE = """
    QMainWindow { background: #1a1b26; }
    QWidget { background: #1a1b26; color: #c0caf5; }

    QMenuBar {
        background: #1f2335; color: #a9b1d6;
        border-bottom: 1px solid #292e42;
        padding: 2px 0;
    }
    QMenuBar::item { padding: 4px 10px; border-radius: 4px; }
    QMenuBar::item:selected { background: #292e42; color: #c0caf5; }
    QMenu {
        background: #1f2335; color: #c0caf5;
        border: 1px solid #292e42; border-radius: 6px;
        padding: 4px 0;
    }
    QMenu::item { padding: 5px 24px 5px 12px; border-radius: 4px; margin: 1px 4px; }
    QMenu::item:selected { background: #283457; }
    QMenu::separator { height: 1px; background: #292e42; margin: 4px 8px; }

    QToolBar {
        background: #1f2335; border: none;
        border-bottom: 1px solid #292e42;
        spacing: 2px; padding: 3px 6px;
    }
    QToolBar::separator { width: 1px; background: #292e42; margin: 4px 4px; }
    QToolButton {
        background: transparent; color: #a9b1d6;
        border: 1px solid transparent; border-radius: 6px;
        padding: 4px; margin: 1px;
    }
    QToolButton:hover { background: #292e42; border-color: #292e42; }
    QToolButton:checked { background: #283457; border-color: #3d59a1; }
    QToolButton:pressed { background: #3d59a1; }

    QDockWidget {
        color: #a9b1d6;
        titlebar-close-icon: none;
        titlebar-normal-icon: none;
    }
    QDockWidget::title {
        background: #1f2335; text-align: left;
        padding: 6px 10px;
        border-bottom: 1px solid #292e42;
        font-weight: 600;
    }

    QGroupBox {
        color: #a9b1d6; font-weight: 600;
        border: 1px solid #292e42; border-radius: 6px;
        margin-top: 8px; padding-top: 14px;
    }
    QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }

    QLabel { color: #c0caf5; background: transparent; }

    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit {
        background: #24283b; color: #c0caf5;
        border: 1px solid #292e42; border-radius: 4px;
        padding: 3px 6px; selection-background-color: #283457;
    }
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QTextEdit:focus {
        border-color: #3d59a1;
    }
    QComboBox::drop-down {
        border: none; width: 20px;
    }
    QComboBox QAbstractItemView {
        background: #1f2335; color: #c0caf5;
        border: 1px solid #292e42; selection-background-color: #283457;
    }

    QSlider::groove:horizontal {
        background: #292e42; height: 4px; border-radius: 2px;
    }
    QSlider::handle:horizontal {
        background: #7aa2f7; width: 14px; height: 14px;
        margin: -5px 0; border-radius: 7px;
    }
    QSlider::handle:horizontal:hover { background: #89b4fa; }

    QPushButton {
        background: #24283b; color: #c0caf5;
        border: 1px solid #292e42; padding: 4px 12px;
        border-radius: 4px; font-weight: 500;
    }
    QPushButton:hover { background: #292e42; border-color: #3d59a1; }
    QPushButton:pressed { background: #3d59a1; }

    QCheckBox { color: #c0caf5; spacing: 6px; }
    QCheckBox::indicator {
        width: 16px; height: 16px; border-radius: 3px;
        border: 1px solid #414868;
    }
    QCheckBox::indicator:checked {
        background: #7aa2f7; border-color: #7aa2f7;
    }
    QCheckBox::indicator:unchecked { background: #24283b; }

    QListWidget {
        background: #1f2335; color: #c0caf5;
        border: none; outline: none;
    }
    QListWidget::item:selected { background: #283457; }
    QListWidget::item:hover:!selected { background: #292e42; }

    QTableWidget {
        background: #1f2335; color: #c0caf5;
        gridline-color: #292e42; border: none;
        selection-background-color: #283457;
    }
    QHeaderView::section {
        background: #24283b; color: #a9b1d6;
        border: none; border-bottom: 1px solid #292e42;
        padding: 5px 8px; font-weight: 600;
    }

    QStatusBar {
        background: #1f2335; color: #565f89;
        border-top: 1px solid #292e42;
    }
    QStatusBar::item { border: none; }

    QScrollBar:vertical {
        background: #1a1b26; width: 10px; margin: 0; border: none;
    }
    QScrollBar::handle:vertical {
        background: #292e42; min-height: 30px; border-radius: 5px;
    }
    QScrollBar::handle:vertical:hover { background: #414868; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }

    QScrollBar:horizontal {
        background: #1a1b26; height: 10px; margin: 0; border: none;
    }
    QScrollBar::handle:horizontal {
        background: #292e42; min-width: 30px; border-radius: 5px;
    }
    QScrollBar::handle:horizontal:hover { background: #414868; }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }

    QSplitter::handle { background: #292e42; }
    QTabBar::tab {
        background: #1f2335; color: #565f89;
        border: none; padding: 6px 14px;
        border-bottom: 2px solid transparent;
    }
    QTabBar::tab:selected { color: #c0caf5; border-bottom-color: #7aa2f7; }
    QTabBar::tab:hover:!selected { color: #a9b1d6; background: #24283b; }
"""


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
        self._dark_mode = True
        self.setStyleSheet(_MARKFORGE_STYLE)

        self._autosave = Autosave(self._autosave_tick)

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
        self.properties.hidden_changed.connect(self._set_hidden)
        self.properties.locked_changed.connect(self._set_locked)

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
        self.print_action = self._action("&Print...", icons.print_icon(), QKeySequence.Print,
                                         self.print_document, "Print the document")
        self.export_csv_action = self._action("Export Markups as &CSV...", None, None,
                                              self.export_csv, "Export all markups to CSV")
        self.export_image_action = self._action("Export Page as &Image...", None, None,
                                                self.export_page_image,
                                                "Export the current page as an image")
        self.autosave_action = QAction("Auto&save", self)
        self.autosave_action.setCheckable(True)
        self.autosave_action.setStatusTip("Periodically save the document")
        self.autosave_action.setToolTip("Periodically save the document")
        self.autosave_action.toggled.connect(self._toggle_autosave)
        self.addAction(self.autosave_action)

        quit_action = self._action("&Quit", None, QKeySequence.Quit, self.close, "Quit")
        for action in (self.open_action, self.save_action, self.save_as_action):
            file_menu.addAction(action)
        file_menu.addSeparator()
        file_menu.addAction(self.print_action)
        file_menu.addAction(self.export_csv_action)
        file_menu.addAction(self.export_image_action)
        file_menu.addSeparator()
        file_menu.addAction(self.autosave_action)
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
        self.insert_sized_action = self._action("Insert &Sized Page...", None, None,
                                                self.insert_sized_page,
                                                "Insert a page with a chosen paper size")
        self.insert_pdf_action = self._action("Insert Pages from P&DF...", None, None,
                                              self.insert_pdf_pages,
                                              "Insert pages from another PDF")
        self.duplicate_page_action = self._action("D&uplicate Page", icons.duplicate_icon(),
                                                  None, self.duplicate_page,
                                                  "Duplicate the current page")
        self.delete_page_action = self._action("&Delete Page", icons.delete_page_icon(),
                                               "Ctrl+Shift+D", self.delete_page,
                                               "Delete the page shown")
        self.rotate_cw_action = self._action("Rotate &Clockwise", icons.rotate_icon(),
                                             "Ctrl+Shift+R", self.rotate_page_cw,
                                             "Rotate the page 90 degrees clockwise")
        self.rotate_ccw_action = self._action("Rotate C&ounter-clockwise", None,
                                              "Ctrl+Shift+L", self.rotate_page_ccw,
                                              "Rotate the page 90 degrees counter-clockwise")
        for action in (self.insert_action, self.insert_sized_action, self.insert_pdf_action,
                       self.duplicate_page_action):
            page_menu.addAction(action)
        page_menu.addSeparator()
        for action in (self.delete_page_action, self.rotate_cw_action, self.rotate_ccw_action):
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
            ("Po&lygon", icons.polygon_icon(), "P", POLYGON,
             "Click points, double-click to finish"),
            ("&Cloud", icons.cloud_icon(), "C", CLOUD, "Draw a revision cloud"),
            ("&Ink / Pen", icons.ink_icon(), "I", INK, "Draw freehand"),
            ("&Highlight", icons.highlight_icon(), "H", HIGHLIGHT, "Highlight an area"),
            ("&Text Box", icons.text_icon(), "T", TEXT, "Place a text box"),
            ("&Note", icons.note_icon(), "N", NOTE, "Place a sticky note"),
            ("Poly&line", icons.polyline_icon(), "Shift+L", POLYLINE,
             "Click points, double-click to finish"),
            ("Sta&mp", icons.stamp_icon(), "M", STAMP, "Drag to place a stamp"),
            ("E&raser", icons.eraser_icon(), "X", ERASER, "Click a markup to delete it"),
            ("Re&daction", icons.redaction_icon(), "D", REDACTION,
             "Drag to mark an area for redaction"),
            ("Measure &Length", icons.measure_icon(), None, MEASURE_LENGTH,
             "Drag to measure a distance"),
            ("Measure &Area", None, None, MEASURE_AREA,
             "Click points, double-click to measure area"),
            ("Measure An&gle", None, None, MEASURE_ANGLE,
             "Click three points to measure an angle"),
            ("&Lasso Select", icons.lasso_icon(), "Shift+V", LASSO,
             "Draw a freehand selection area"),
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
        self.forward_one_action = self._action("Move For&ward", None, "Ctrl+]",
                                               self.forward_one,
                                               "Move markup one step forward")
        self.backward_one_action = self._action("Move Back&ward", None, "Ctrl+[",
                                                self.backward_one,
                                                "Move markup one step backward")
        self.hide_action = self._action("&Hide Markup", None, None, self.toggle_hide_markup,
                                        "Toggle markup visibility")
        self.lock_action = self._action("&Lock Markup", None, None, self.toggle_lock_markup,
                                        "Toggle markup lock")
        for action in (self.text_action, self.group_action, self.ungroup_action):
            markup_menu.addAction(action)
        markup_menu.addSeparator()
        for action in (self.front_action, self.back_action,
                       self.forward_one_action, self.backward_one_action):
            markup_menu.addAction(action)
        markup_menu.addSeparator()
        for action in (self.hide_action, self.lock_action):
            markup_menu.addAction(action)

        # View
        zoom_in = self._action("Zoom &In", icons.zoom_icon(True), QKeySequence.ZoomIn,
                               self.view.zoom_in, "Zoom in")
        zoom_out = self._action("Zoom &Out", icons.zoom_icon(False), QKeySequence.ZoomOut,
                                self.view.zoom_out, "Zoom out")
        fit = self._action("&Fit Page", icons.fit_icon(), "Ctrl+0",
                           self.view.fit_page, "Fit the whole page")
        self.theme_action = self._action("&Dark Theme", icons.theme_icon(), None,
                                         self.toggle_theme, "Switch between light and dark")
        self.theme_action.setCheckable(True)
        self.theme_action.setChecked(True)
        for action in (zoom_in, zoom_out, fit):
            view_menu.addAction(action)
            main_bar.addAction(action)

        view_menu.addSeparator()
        view_menu.addAction(self.theme_action)
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
        self._autosave.set_has_path(self.document.path is not None)
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
        self._autosave.set_has_path(True)
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
        self._autosave.set_has_path(True)
        self.update_title()
        self.statusBar().showMessage(f"Saved {os.path.basename(path)}.", 4000)
        return True

    def print_document(self) -> None:
        if self.document.is_empty:
            return
        try:
            from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        except ImportError:
            QMessageBox.information(self, APP_NAME, "Printing support is not available.")
            return
        printer = QPrinter(QPrinter.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QDialog.Accepted:
            return
        from PySide6.QtGui import QImage, QPainter as QPrint
        painter = QPrint()
        painter.begin(printer)
        page_rect = printer.pageRect(QPrinter.DevicePixel)
        for i in range(self.document.page_count):
            if i > 0:
                printer.newPage()
            img_data = self.document.render_page(i, dpi=300)
            img = QImage(img_data["samples"], img_data["width"], img_data["height"],
                         img_data["stride"], QImage.Format_RGB888)
            scaled = img.scaled(int(page_rect.width()), int(page_rect.height()),
                                Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter.drawImage(0, 0, scaled)
        painter.end()
        self.statusBar().showMessage("Printed.", 4000)

    def export_csv(self) -> None:
        if self.document.is_empty:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Markups as CSV", "", CSV_FILTER)
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            self.document.export_markups_csv(path)
        except DocumentError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        self.statusBar().showMessage(f"Exported markups to {os.path.basename(path)}.", 4000)

    def export_page_image(self) -> None:
        if self.document.is_empty:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Page as Image", "", IMAGE_FILTER)
        if not path:
            return
        dpi, ok = QInputDialog.getInt(self, "Export DPI", "Resolution (DPI):", 150, 72, 600)
        if not ok:
            return
        try:
            self.document.export_page_image(self.view.index, path, dpi)
        except DocumentError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        self.statusBar().showMessage(
            f"Exported page {self.view.index + 1} to {os.path.basename(path)}.", 4000)

    def _autosave_tick(self) -> None:
        if self.document.path and self.document.modified:
            try:
                self.document.save()
                self.update_title()
            except DocumentError:
                pass

    def _toggle_autosave(self, on: bool) -> None:
        self._autosave.set_enabled(on)
        self.statusBar().showMessage(
            "Autosave enabled." if on else "Autosave disabled.", 4000)

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

    def insert_sized_page(self) -> None:
        if self.document.is_empty:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Insert Sized Page")
        form = QFormLayout(dialog)
        size_combo = QComboBox()
        for name in PAPER_SIZES:
            w, h = PAPER_SIZES[name]
            size_combo.addItem(f"{name}  ({w} x {h} pt)", name)
        form.addRow("Paper size:", size_combo)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        name = size_combo.currentData()
        w, h = PAPER_SIZES[name]
        index = self.view.index + 1
        try:
            self.document.insert_page_sized(index, float(w), float(h))
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
        self.statusBar().showMessage(f"Inserted {name} page at {index + 1}.", 4000)

    def insert_pdf_pages(self) -> None:
        if self.document.is_empty:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Insert Pages from PDF", "", PDF_FILTER)
        if not path:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Page Range")
        form = QFormLayout(dialog)
        from_spin = QSpinBox()
        from_spin.setMinimum(1)
        from_spin.setMaximum(9999)
        from_spin.setValue(1)
        form.addRow("From page:", from_spin)
        to_spin = QSpinBox()
        to_spin.setMinimum(1)
        to_spin.setMaximum(9999)
        to_spin.setValue(1)
        form.addRow("To page:", to_spin)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        insert_at = self.view.index + 1
        try:
            self.document.insert_pdf_pages(path, from_spin.value() - 1,
                                           to_spin.value() - 1, insert_at)
        except DocumentError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        self.pages.reload(insert_at)
        self.view.refresh()
        self.view._syncing = True
        self.view.index = insert_at
        if self.view._page_rects:
            self.view._scroll_to_page(insert_at)
        self.view._syncing = False
        self.on_edited(refresh_thumbnail=False)
        self.statusBar().showMessage(
            f"Inserted pages from {os.path.basename(path)}.", 4000)

    def duplicate_page(self) -> None:
        if self.document.is_empty:
            return
        index = self.view.index
        try:
            self.document.duplicate_page(index)
        except DocumentError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        new_index = index + 1
        self.pages.insert_row(new_index)
        self.view.refresh()
        self.view._syncing = True
        self.view.index = new_index
        if self.view._page_rects:
            self.view._scroll_to_page(new_index)
        self.view._syncing = False
        self.pages.setCurrentRow(new_index)
        self.on_edited(refresh_thumbnail=False)
        self.statusBar().showMessage(f"Duplicated page {index + 1}.", 4000)

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
            POLYLINE: "Click to add points. Double-click to finish the polyline.",
            STAMP: "Drag to place a stamp annotation.",
            ERASER: "Click on a markup to delete it.",
            REDACTION: "Drag to mark an area for redaction.",
            MEASURE_LENGTH: "Drag to measure a distance.",
            MEASURE_AREA: "Click points, double-click to measure area.",
            MEASURE_ANGLE: "Click three points to measure an angle.",
            LASSO: "Draw around markups to select them.",
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

    def forward_one(self) -> None:
        chosen = self.view.selected_items()
        if len(chosen) != 1:
            self.statusBar().showMessage("Select one markup to reorder.", 4000)
            return
        item = chosen[0]
        if self.document.forward_one(item.page_index, item.xref):
            self.view.refresh(item.xref)
            self.on_edited()
            self.statusBar().showMessage("Markup moved forward.", 4000)

    def backward_one(self) -> None:
        chosen = self.view.selected_items()
        if len(chosen) != 1:
            self.statusBar().showMessage("Select one markup to reorder.", 4000)
            return
        item = chosen[0]
        if self.document.backward_one(item.page_index, item.xref):
            self.view.refresh(item.xref)
            self.on_edited()
            self.statusBar().showMessage("Markup moved backward.", 4000)

    def toggle_hide_markup(self) -> None:
        chosen = self.view.selected_items()
        if len(chosen) != 1:
            self.statusBar().showMessage("Select one markup.", 4000)
            return
        item = chosen[0]
        new_hidden = not item.markup.hidden
        if self.document.set_markup_hidden(item.page_index, item.xref, new_hidden):
            self.view.refresh(item.xref)
            self.on_edited()
            self.statusBar().showMessage(
                "Markup hidden." if new_hidden else "Markup shown.", 4000)

    def toggle_lock_markup(self) -> None:
        chosen = self.view.selected_items()
        if len(chosen) != 1:
            self.statusBar().showMessage("Select one markup.", 4000)
            return
        item = chosen[0]
        new_locked = not item.markup.locked
        if self.document.set_markup_locked(item.page_index, item.xref, new_locked):
            self.view.refresh(item.xref)
            self.on_edited()
            self.statusBar().showMessage(
                "Markup locked." if new_locked else "Markup unlocked.", 4000)

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

    def _set_hidden(self, hidden: bool) -> None:
        chosen = self.view.selected_items()
        if len(chosen) != 1:
            return
        item = chosen[0]
        if self.document.set_markup_hidden(item.page_index, item.xref, hidden):
            self.view.refresh(item.xref)
            self.on_edited()

    def _set_locked(self, locked: bool) -> None:
        chosen = self.view.selected_items()
        if len(chosen) != 1:
            return
        item = chosen[0]
        if self.document.set_markup_locked(item.page_index, item.xref, locked):
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

    # ----------------------------------------------------------------- theme

    def toggle_theme(self) -> None:
        self._dark_mode = not self._dark_mode
        if self._dark_mode:
            self.setStyleSheet(_MARKFORGE_STYLE)
            from ..app import _dark_palette
            QApplication.instance().setPalette(_dark_palette())
        else:
            self.setStyleSheet("")
            QApplication.instance().setPalette(QApplication.style().standardPalette())
        self.theme_action.setChecked(self._dark_mode)

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
        for action in (self.save_action, self.save_as_action, self.insert_action,
                       self.insert_sized_action, self.insert_pdf_action,
                       self.duplicate_page_action, self.print_action,
                       self.export_csv_action, self.export_image_action):
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
        self.forward_one_action.setEnabled(len(chosen) == 1)
        self.backward_one_action.setEnabled(len(chosen) == 1)
        self.hide_action.setEnabled(len(chosen) == 1)
        self.lock_action.setEnabled(len(chosen) == 1)

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
        self._autosave.stop()
        if self.confirm_discard():
            event.accept()
        else:
            event.ignore()
