"""The MarkForge main window."""
from __future__ import annotations

import base64
import json
import os
from typing import Optional

from PySide6.QtCore import (QBuffer, QEvent, QIODevice, QMimeData, QPointF,
                            QRect, QRectF,
                            QSettings, QSize, Qt, QTimer)
from PySide6.QtGui import (QAction, QActionGroup, QColor, QCursor, QFont, QImage,
                           QKeySequence, QPainter, QTextBlockFormat,
                           QTextCharFormat, QTextCursor, QTransform, QUndoStack)
from PySide6.QtPrintSupport import QPrintDialog, QPrintPreviewDialog, QPrinter
from PySide6.QtWidgets import (QTabBar, QApplication, QComboBox, QDockWidget, QDoubleSpinBox,
                               QFileDialog, QGraphicsItem, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QMainWindow,
                               QMenu, QMessageBox, QSizePolicy, QSpinBox,
                               QStatusBar, QToolBar, QToolButton, QVBoxLayout,
                               QWidget)

from ..core.document import (LANDSCAPE, MM_TO_PT, PAGE_SIZES, PORTRAIT,
                             PT_TO_MM, Document, Page, PageScale,
                             PageSetup)
from ..core.units import format_quantity, parse_unit
from ..io import export as export_io
from ..io import pdfio
from ..io import project as project_io
from ..items.base import HATCH_PATTERNS, MarkupItem, Style, build_item
from ..items.contents import ContentsItem
from ..items.measure import MeasureItem
from ..items.media import ImageItem
from ..items.shapes import PolyItem, RectItem
from ..items.snapshot import SnapshotItem
from ..items.text import (CalloutItem, FlagItem, NoteItem, StampItem,
                          TextItem, TypewriterItem, _TextBase)
from . import dialogs
from .commands import DocumentStructureCommand
from .icons import icon
from .panels import (BookmarksPanel, MarkupsPanel, PagesPanel,
                     PropertiesPanel, ToolSetsPanel)
from .docks import PanelDock, load_panel_state, save_panel_state
from .rail import (AREAS, LEFT, RIGHT, PanelRail, RailBar, load_sides,
                   save_sides)
from .scene import DocumentScene, detach
from .shortcuts import COMMAND, INSERT, SYMBOL, TOOL, ShortcutManager
from .stylecaps import (DASH, FILL, FILL_OPACITY, FONT, HATCH, OPACITY, STROKE,
                        WIDTH, capabilities, common_capabilities)
from . import toolsets
from .tools import CATEGORIES, NONE, TOOL_MAP, TOOLS, tools_in
from .view import SIZED_SHAPES
from .view import PageView, typing_somewhere_else
from .widgets import ColorButton, keep_the_wheel_with_the_scroller

APP_NAME = "MarkForge"
ORGANISATION = "MarkForge"
CLIPBOARD_TAG = "application/x-markforge-items"


def _command_id(method: str) -> str:
    """Binding id for a command method, e.g. fit_page -> fit_page."""
    return {"fit_page": "fit_page", "fit_width": "fit_width",
            "renumber_counts": "renumber_counts"}.get(method, method)


class CenteredStatusBar(QStatusBar):
    """Status bar with the page navigation centred in the room it has.

    It used to be centred by hand — parented to the bar, moved to the middle
    and raised above everything. Which is exactly what it did: the page
    navigation was drawn *over* the cursor position and the page label, and on
    a marked-up drawing the footer read "of 140.9, 246.8 mm drawing.pdf page 1"
    with three texts on top of one another. Nothing in a layout can overlap
    anything else, so it is in the layout now, between two stretches that keep
    it in the middle of whatever space the rest leaves it.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.center_widget = None

    def set_center_widget(self, widget: QWidget) -> None:
        self.center_widget = widget
        self.addWidget(_stretch(self), 1)
        self.addWidget(widget)
        self.addWidget(_stretch(self), 1)


def _stretch(parent) -> QWidget:
    """An empty widget that exists only to take up room."""
    spacer = QWidget(parent)
    spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    return spacer


# Which part of the shortcut list each action belongs in, so a long list is
# still findable. Anything not named here goes under "Document".
# Actions the shortcut list already knows under another name, so that they
# are not entered twice and do not read as clashing with themselves.
_ALREADY_BOUND = {
    "fit_page": "command.fit_page", "fit_width": "command.fit_width",
    "renumber_counts": "command.renumber_counts",
}

_SHORTCUT_GROUPS = {
    "new": "File", "open": "File", "save": "File", "save_as": "File",
    "insert_pdf": "File", "insert_image_page": "File", "import_toolset": "File",
    "export_pdf": "File", "export_png": "File", "export_markups": "File",
    "preview": "File", "print": "File", "quit": "File",
    "undo": "Edit", "redo": "Edit", "cut": "Edit", "copy": "Edit",
    "paste": "Edit", "paste_in_place": "Edit", "paste_here": "Edit",
    "duplicate": "Edit", "delete": "Edit", "select_all": "Edit",
    "lock": "Edit", "array": "Edit", "preferences": "Edit",
    "front": "Order", "back": "Order", "forward": "Order", "backward": "Order",
    "align_left": "Order", "align_right": "Order", "align_top": "Order",
    "align_bottom": "Order", "align_hcenter": "Order", "align_vcenter": "Order",
    "text_left": "Text", "text_center": "Text", "text_right": "Text",
    "font_increase": "Text", "font_decrease": "Text",
    "bold": "Text", "italic": "Text", "underline": "Text",
    "zoom_in": "View", "zoom_out": "View", "zoom_sel": "View",
    "fit_page": "View", "fit_width": "View", "actual_size": "View",
    "prev_page": "View", "next_page": "View", "grid": "View", "snap": "View",
    "snap_items": "View", "snap_content": "View", "snap_alignment": "View",
    "margins": "View", "dark": "View",
    "turn_view_cw": "View", "turn_view_acw": "View",
    "turn_view_reset": "View",
    "group": "Markup", "ungroup": "Markup", "autosize": "Markup",
    "format_painter": "Markup", "hide": "Markup", "show_hidden": "Markup",
    "flatten": "Markup", "forget_defaults": "Markup",
    "add_page": "Page", "duplicate_page": "Page", "delete_page": "Page",
    "page_setup": "Page", "scale": "Page", "header_footer": "Page",
    "bookmark": "Page", "contents": "Page", "doc_props": "Page",
    "renumber_counts": "Markup",
    "shortcuts": "Help", "sample": "Help",
    "find_tool": "Help",
    "about": "Help",
}


class MainWindow(QMainWindow):
    """Everything the user sees: canvas, toolbars, panels and menus."""

    def __init__(self):
        super().__init__()
        keep_the_wheel_with_the_scroller(QApplication.instance())
        self.document = Document()
        self.undo_stack = QUndoStack(self)
        self.undo_stack.setUndoLimit(200)
        self.current_index = 0
        self.default_style = Style()
        self.shortcuts = ShortcutManager(self)
        # Which binding each action carries, so a rebinding can find it again.
        self.action_ids: dict[str, str] = {}
        # Drawing a rectangle on a scaled page, or a dimension, asks a question.
        # Automated runs turn that off and set the values directly.
        self.interactive_prompts = True
        self._clipboard: list[dict] = []
        # The look the format painter is holding, if it is picked up.
        self._held_style: dict | None = None
        self.scene = None
        # Each entry is one open document with its own canvas, undo history
        # and page. Empty until a second document is opened, because one
        # document needs no tab bar.
        self._open_documents: list[dict] = []
        self.toolbars: list = []
        self.visible_tools = None       # None means every tool
        self._default_state = None
        self._icon_names: dict = {}
        self._changing_panels = False
        self._mode_hidden_docks: set[str] = set()

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
        self._layout_timer.timeout.connect(self._save_layout_unless_overtaken)
        for dock in self.panels:
            dock.dockLocationChanged.connect(lambda *_: self.note_layout_change())
            dock.topLevelChanged.connect(lambda *_: self.note_layout_change())
            name = dock.objectName()
            dock.visibilityChanged.connect(
                lambda visible, panel=name:
                self._panel_visibility_changed(panel, visible))
            dock.pinnedChanged.connect(lambda *_: self.note_layout_change())
            dock.collapsedChanged.connect(lambda *_: self.note_layout_change())
        for toolbar in self.toolbars:
            toolbar.topLevelChanged.connect(lambda *_: self.note_layout_change())
            toolbar.visibilityChanged.connect(lambda *_: self.note_layout_change())
            toolbar.movableChanged.connect(lambda *_: self.note_layout_change())
        self._enforce_panel_limit()
        QTimer.singleShot(0, self.view.fit_page)

    # ==================================================================
    # construction
    # ==================================================================
    def _build_central(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)


        # One document per tab, one view for all of them. Each tab keeps its
        # own document, canvas, undo history and page, and switching hands the
        # view a different canvas — so nothing has to be re-wired, and nothing
        # of one document can reach into another.
        self.document_tabs = QTabBar()
        self.document_tabs.setDocumentMode(True)
        self.document_tabs.setExpanding(False)
        self.document_tabs.setTabsClosable(True)
        self.document_tabs.setMovable(True)
        self.document_tabs.setDrawBase(False)
        self.document_tabs.setVisible(False)          # one document: no bar
        self.document_tabs.currentChanged.connect(self.switch_to_document)
        self.document_tabs.tabCloseRequested.connect(self.close_document_tab)
        layout.addWidget(self.document_tabs)

        layout.addWidget(self.view, 1)
        self.setCentralWidget(central)

        # The rails go in the toolbar areas, which is what puts them hard
        # against the window's own edges — outside the panels, the way
        # Bluebeam's are.
        self.left_rail = PanelRail(LEFT, self)
        self.right_rail = PanelRail(RIGHT, self)
        self.addToolBar(Qt.LeftToolBarArea, RailBar(self.left_rail, self))
        self.addToolBar(Qt.RightToolBarArea, RailBar(self.right_rail, self))

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

    # The three that belong to the words, not to the document. Bold, italic
    # and underline mean what they mean in every program there has ever been,
    # so they are not offered for rebinding and nothing else may take them.
    RESERVED_FOR_TEXT = ("Ctrl+B", "Ctrl+I", "Ctrl+U")
    EDITOR_COMMANDS = {
        "command.text_left", "command.text_center", "command.text_right",
        "command.font_increase", "command.font_decrease"}

    def _act(self, key: str, text: str, slot, shortcut: str = "", icon_name: str = "",
             checkable: bool = False, tip: str = "") -> QAction:
        action = QAction(text, self)
        if icon_name:
            self.give_icon(action, icon_name)
        if shortcut:
            # Every key the application answers to goes in the shortcut list,
            # so it can be seen in one place and changed. What is registered
            # is the default; a binding already changed keeps the change.
            already = _ALREADY_BOUND.get(key)
            if shortcut in self.RESERVED_FOR_TEXT:
                pass                     # the words keep bold, italic, underline
            elif already:
                # This command is already in the list under its own name; a
                # second entry for the same key would read as a clash with
                # itself.
                shortcut = self.shortcuts.sequence(already) or shortcut
                self.action_ids[key] = already
            else:
                shortcut = self.shortcuts.register(
                    f"command.{key}", text.rstrip("…"), shortcut,
                    _SHORTCUT_GROUPS.get(key, "Document"))
                self.action_ids[key] = f"command.{key}"
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
        self._act("new_tab", "New tab", lambda: self.open_in_new_tab(), "Ctrl+T",
                  tip="Open another document beside this one, in its own tab")
        self._act("new_window", "New window", self.open_new_window, "Ctrl+Shift+N",
                  tip="Open a second window with a document of its own")
        self._act("open", "Open…", self.open_document, "Ctrl+O", "open")
        self._act("save", "Save", self.save_document, "Ctrl+S", "save")
        self._act("save_as", "Save as…", self.save_document_as, "Ctrl+Shift+S")
        # Not Ctrl+I. That belongs to italic wherever there are words, and
        # while somebody was typing it inserted a PDF instead — which is the
        # exact thing the requirement says must never happen. It never reached
        # the shortcut list either, because keys reserved for the text are not
        # registered, so it was a binding nobody could see or change.
        self._act("insert_pdf", "Insert PDF…", lambda: self.insert_pdf(),
                  "Ctrl+Shift+I", "pdf")
        self._act("import_toolset", "Import tools…",
                  lambda: self.import_toolset(),
                  tip="Bring in a Bluebeam tool set — a .btx file")
        self._act("insert_image_page", "Image page…",
                  lambda: self.insert_image_page(), "", "image")
        self._act("export_pdf", "Export PDF…", self.export_pdf, "Ctrl+E", "pdf")
        self._act("export_png", "Export images…", self.export_images,
                  tip="Export every printable page as an image")
        self._act("export_markups", "Export markups…", self.export_markups,
                  tip="Export the document's markup list")
        self._act("print", "Print…", self.print_document, "Ctrl+P", "print")
        self._act("preview", "Print preview…", self.print_preview)
        self._act("quit", "Exit", self.close, "Ctrl+Q")

        # Undo and redo come from the stack itself rather than from _act, so
        # they are entered in the shortcut list by hand — every key the
        # application answers to belongs there.
        # Not the stack's own action: while something is being typed into, the
        # first thing Ctrl+Z should take back is the typing. Undoing straight
        # to the document stack threw away the whole edit in one go, so text
        # deleted with Backspace could not be got back at all — the only step
        # on the stack was the state before the line was opened.
        self.act_undo = QAction("Undo", self)
        self.act_undo.triggered.connect(self.undo_something)
        self.undo_stack.canUndoChanged.connect(self._refresh_undo_actions)
        self.act_undo.setShortcut(QKeySequence(self.shortcuts.register(
            "command.undo", "Undo", "Ctrl+Z", "Edit")))
        self.give_icon(self.act_undo, "undo")
        self.action_ids["undo"] = "command.undo"
        self.act_redo = QAction("Redo", self)
        self.act_redo.triggered.connect(self.redo_something)
        self.undo_stack.canRedoChanged.connect(self._refresh_undo_actions)
        self.act_redo.setShortcut(QKeySequence(self.shortcuts.register(
            "command.redo", "Redo", "Ctrl+Shift+Z", "Edit")))
        self.give_icon(self.act_redo, "redo")
        self.action_ids["redo"] = "command.redo"

        self._act("cut", "Cut", self.cut_selection, "Ctrl+X")
        self._act("copy", "Copy", self.copy_selection, "Ctrl+C")
        self._act("paste", "Paste", self.paste_items, "Ctrl+V")
        self._act("paste_in_place", "Paste in place", self.paste_in_place,
                  "Ctrl+Shift+V",
                  tip="Put it back at the same place on this page, as Bluebeam does")
        self._act("paste_here", "Paste here…", self.paste_with_preview,
                  "Ctrl+Alt+V",
                  tip="Carry what was copied on the pointer and click to drop it")
        self._act("duplicate", "Duplicate", self.duplicate_selection, "Ctrl+D")
        self._act("delete", "Delete", self.delete_selection, "", "delete")
        self._act("select_all", "Select all", self.select_all, "Ctrl+A")
        self._act("lock", "Lock", self.toggle_lock, "Ctrl+L",
                  tip="Lock the selection so it cannot be moved, or let it go")
        self._act("array", "Offset copies…", self.array_selection,
                  "Ctrl+Shift+D",
                  tip="Repeat the selection at a fixed spacing, any number of times")
        self._act("front", "Bring front", lambda: self.reorder("front"), "Ctrl+Shift+]",
                  tip="Bring the selection to the front")
        self._act("back", "Send back", lambda: self.reorder("back"), "Ctrl+Shift+[", tip="Send the selection behind every other markup")
        self._act("forward", "Bring forward", lambda: self.reorder("forward"), "Ctrl+]")
        self._act("backward", "Send backward", lambda: self.reorder("backward"), "Ctrl+[")
        for key, label in (("left", "Align left"), ("hcenter", "Align centres"),
                           ("right", "Align right"), ("top", "Align top"),
                           ("vcenter", "Align middles"), ("bottom", "Align bottom")):
            self._act(f"align_{key}", label, lambda _=False, k=key: self.align_items(k))
        # Bold has always been reachable — Ctrl+B tries the words before it
        # reaches for a bookmark. Italic and underline had nothing at all:
        # Ctrl+I inserted a PDF and Ctrl+U did nothing. They are commands now,
        # on the keys they have in every program there has ever been.
        self._act("bold", "Bold", self.toggle_bold, "",
                  tip="Embolden the words picked out, or the whole markup")
        self._act("italic", "Italic", self.toggle_italic, "Ctrl+I",
                  tip="Italicise the words picked out, or the whole markup")
        self._act("underline", "Underline", self.toggle_underline, "Ctrl+U",
                  tip="Underline the words picked out, or the whole markup")
        self._act("text_left", "Text left",
                  lambda: self.format_content(alignment="left"), "Ctrl+Alt+Left")
        self._act("text_center", "Text centre",
                  lambda: self.format_content(alignment="center"), "Ctrl+Alt+Home")
        self._act("text_right", "Text right",
                  lambda: self.format_content(alignment="right"), "Ctrl+Alt+Right")
        self._act("font_increase", "Larger text",
                  lambda: self.format_content(font_delta=1.0), "Ctrl+Alt+Up")
        self._act("font_decrease", "Smaller text",
                  lambda: self.format_content(font_delta=-1.0), "Ctrl+Alt+Down")

        self._act("zoom_in", "Zoom in", self.view.zoom_in, "Ctrl++", "zoom_in")
        self._act("zoom_out", "Zoom out", self.view.zoom_out, "Ctrl+-", "zoom_out")
        self._act("fit_page", "Fit page", self.view.fit_page, "Ctrl+0", "fit")
        self._act("fit_width", "Fit width", self.view.fit_width, "Ctrl+1")
        self._act("zoom_sel", "Zoom selection", self.view.zoom_to_selection, "Ctrl+2",
                  tip="Zoom to the selected markups")
        # Turning the view is a way of looking at the page, not a change to
        # it: for reading a drawing that came in sideways. Rotating the page
        # itself is on the page menu, and does change the document.
        self._act("turn_view_cw", "Turn clockwise",
                  lambda: self.view.rotate_view(True), "Ctrl+Shift+.",
                  tip="Turn the page on screen, for reading a drawing "
                      "sideways — the page itself is not changed")
        self._act("turn_view_acw", "Turn anticlockwise",
                  lambda: self.view.rotate_view(False), "Ctrl+Shift+,",
                  tip="Turn the page on screen the other way — the page "
                      "itself is not changed")
        self._act("turn_view_reset", "Reset turn",
                  self.view.reset_view_rotation,
                  tip="Put the view back the way up the page is")
        # Bare Page Up/Down scroll a screenful, as they do in any reader; with
        # Ctrl they jump a whole page.
        self._act("prev_page", "Previous page", lambda: self.go_to_page(self.current_index - 1),
                  "Ctrl+PgUp")
        self._act("next_page", "Next page", lambda: self.go_to_page(self.current_index + 1),
                  "Ctrl+PgDown")
        self._act("actual_size", "Actual size", lambda: self.view.set_zoom(1.0), "Ctrl+Alt+0")
        self._act("pin_panels", "Pin panels", self.pin_all_panels, "", checkable=True,
                  tip="Keep the panels where they are, so a stray drag cannot move them")
        self._act("show_panels", "Show panels", self.show_all_panels,
                  tip="Open the default panel on each side")
        self._act("reset_layout", "Reset layout", self.reset_layout,
                  tip="Put the panels and toolbars back where they started")
        self._act("lock_toolbars", "Lock toolbars", self.lock_toolbars, "",
                  checkable=True, tip="Stop the toolbars being dragged about")
        self._act("customise_toolbar", "Choose tools…",
                  self.customise_toolbar,
                  tip="Pick which tools appear on the markup toolbar")

        self._act("add_page", "Add page", lambda: self.add_page())
        self._act("duplicate_page", "Duplicate page", lambda: self.duplicate_page())
        self._act("delete_page", "Delete page", lambda: self.delete_page())
        # No key: Ctrl+Shift+P shows the problems panel, and page setup is on
        # the Page menu and on a page's own right-click menu.
        self._act("page_setup", "Page setup…", self.page_setup, "", "page")
        self._act("scale", "Page scale…", self.calibrate_dialog,
                  "Ctrl+Shift+K", "calibrate")
        self._act("doc_props", "Document properties…", lambda: self.document_properties())
        self._act("header_footer", "Header/footer…", self.edit_header_footer, "",
                  tip="Page numbers, the date, a title and a logo on every page")

        # Ctrl+G is Group, here as in Bluebeam, so the grid takes the key
        # next to it rather than fighting for one. Ctrl+Alt+G is Greek gamma.
        self._act("grid", "Show grid", self.toggle_grid, "Ctrl+'", checkable=True)
        self._act("snap", "Grid snap", self.toggle_snap, "", checkable=True,
                  tip="Snap points to the page grid")
        self._act("snap_items", "Markup snap", self.toggle_item_snap, "",
                  checkable=True,
                  tip="Catch corners, centres, side middles and line ends of "
                      "the markups already on the page")
        self._act("snap_content", "PDF snap", self.toggle_content_snap,
                  "", checkable=True,
                  tip="Catch the corners and ends of the line work that came "
                      "in on the page — and only those, because a drawing has "
                      "thousands of them")
        self._act("snap_alignment", "Align snap",
                  self.toggle_alignment_snap, "", checkable=True,
                  tip="Line a new markup up level with, or directly under, a "
                      "point on one already drawn. Never off the drawing "
                      "underneath — every line on that would offer a guide")
        self._act("dark", "Dark theme", self.toggle_theme, "", checkable=True)
        self._act("margins", "Show margins", self.toggle_margins, "", checkable=True)
        self.act_margins.setChecked(True)
        self.act_snap_items.setChecked(True)
        self.act_snap_content.setChecked(True)
        self.act_snap_alignment.setChecked(True)
        self._act("sticky", "Stay active", self.toggle_sticky, "", "pin",
                  checkable=True,
                  tip="Stay on the current tool after drawing instead of returning to Select")
        self._act("apply_redactions", "Apply redactions…", self.apply_redactions, "",
                  tip="Permanently remove what the black boxes cover")

        self._act("shortcuts", "Shortcuts…", self.show_shortcuts, "F1",
                  tip="Every shortcut, and the keys you want them on")
        self._act("find_tool", "Find tool…", self.find_a_tool, "Shift+F1",
                  tip="Type what you want to do, and it says which tool does "
                      "it and which key it is on")
        self._act("renumber_counts", "Renumber counts", self.renumber_counts,
                  tip="Renumber the count markers in page order")
        self._act("group", "Group", self.group_selection, "Ctrl+G",
                  tip="Make the selected markups one thing to click and move")
        self._act("ungroup", "Ungroup", self.ungroup_selection, "Ctrl+Shift+G")
        self._act("autosize", "Auto-size", self.autosize_text, "Alt+Z",
                  tip="Shrink the box around the words in it")
        self._act("format_painter", "Format painter", self.format_painter,
                  "Ctrl+Shift+C", "format_painter",
                  tip="Take this one's look, then click another to paint it on")
        self._act("hide", "Hide", self.hide_selection,
                  tip="Take it off the screen and out of the print, without "
                      "deleting it — Show hidden brings it back")
        self._act("show_hidden", "Show hidden", self.show_hidden,
                  tip="Bring back everything that was hidden")
        self._act("flatten", "Flatten selection", self.flatten_selection,
                  tip="Make it part of the drawing rather than a markup on top "
                      "of it — it can no longer be moved or edited")
        self._act("flatten_document", "Flatten…", self.flatten_document,
                  tip="Choose which content classes to flatten on every page")
        self._act("recover_flattened", "Recover", self.recover_flattened,
                  tip="Restore source items retained by recoverable flattening")
        self._act("preferences", "Preferences…", self.edit_preferences, "Ctrl+,",
                  tip="How the wheel behaves, how blocks start, spell checking")
        self._act("forget_defaults", "Forget defaults", self.forget_defaults,
                  tip="Put every kind of markup back to how it started")
        self._act("bookmark", "Add bookmark", self.add_bookmark_here, "Ctrl+B",
                  tip="Name this place so it can be jumped to, printed in a "
                      "contents block and exported as a PDF bookmark")
        self._act("contents", "Contents", self.insert_contents_block,
                  tip="Insert a table of contents built from document bookmarks")
        self._act("about", f"About {APP_NAME}", self.show_about)

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
                       self.act_undo, self.act_redo):
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
        self._style_widgets: dict[str, list] = {
            STROKE: [], FILL: [], WIDTH: [], DASH: [], FONT: [],
            HATCH: [], OPACITY: [], FILL_OPACITY: []}
        self._style_widgets[STROKE].append(style_bar.addWidget(QLabel(" Line ")))
        self.stroke_button = ColorButton(self.default_style.stroke, True, "Line colour")
        self.stroke_button.colorChanged.connect(self._style_stroke)
        self._style_widgets[STROKE].append(style_bar.addWidget(self.stroke_button))
        self._style_widgets[FILL].append(style_bar.addWidget(QLabel(" Fill ")))
        self.fill_button = ColorButton("", True, "Fill colour")
        self.fill_button.colorChanged.connect(self._style_fill)
        self._style_widgets[FILL].append(style_bar.addWidget(self.fill_button))
        self._style_widgets[WIDTH].append(style_bar.addWidget(QLabel(" Width ")))
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(0.0, 40.0)
        self.width_spin.setSingleStep(0.25)
        self.width_spin.setValue(self.default_style.width)
        self.width_spin.setSuffix(" pt")
        self.width_spin.valueChanged.connect(self._style_width)
        self._style_widgets[WIDTH].append(style_bar.addWidget(self.width_spin))
        self._style_widgets[DASH].append(style_bar.addWidget(QLabel(" Dash ")))
        self.dash_combo = QComboBox()
        self.dash_combo.addItems(["solid", "dash", "dot", "dashdot", "dashdotdot"])
        self.dash_combo.currentTextChanged.connect(self._style_dash)
        self._style_widgets[DASH].append(style_bar.addWidget(self.dash_combo))
        self._style_widgets[FONT].append(style_bar.addWidget(QLabel(" Text ")))
        self.font_spin = QDoubleSpinBox()
        self.font_spin.setRange(3.0, 96.0)
        self.font_spin.setValue(self.default_style.font_size)
        self.font_spin.setSuffix(" pt")
        self.font_spin.valueChanged.connect(self._style_font)
        self._style_widgets[FONT].append(style_bar.addWidget(self.font_spin))
        # Hatch and the two opacities were only ever in the Properties panel,
        # so the two surfaces disagreed about every markup that has them: the
        # panel offered a hatch and a transparency the toolbar had no way to
        # reach. They are the same setting either way, so they are here too.
        self._style_widgets[HATCH].append(style_bar.addWidget(QLabel(" Hatch ")))
        self.hatch_combo = QComboBox()
        self.hatch_combo.setObjectName("hatchPattern")
        for name in HATCH_PATTERNS:
            self.hatch_combo.addItem(name or "plain", name)
        self.hatch_combo.setToolTip("Pattern drawn over the fill")
        self.hatch_combo.currentIndexChanged.connect(
            lambda _index: self._style_hatch(self.hatch_combo.currentData()))
        self._style_widgets[HATCH].append(style_bar.addWidget(self.hatch_combo))
        self._style_widgets[OPACITY].append(style_bar.addWidget(QLabel(" Opacity ")))
        self.opacity_spin = QSpinBox()
        self.opacity_spin.setRange(5, 100)
        self.opacity_spin.setSuffix(" %")
        self.opacity_spin.setToolTip("How much of what is underneath shows through")
        self.opacity_spin.setValue(int(self.default_style.opacity * 100))
        self.opacity_spin.valueChanged.connect(self._style_opacity)
        self._style_widgets[OPACITY].append(style_bar.addWidget(self.opacity_spin))
        self._style_widgets[FILL_OPACITY].append(
            style_bar.addWidget(QLabel(" Fill % ")))
        self.fill_opacity_spin = QSpinBox()
        self.fill_opacity_spin.setRange(0, 100)
        self.fill_opacity_spin.setSuffix(" %")
        self.fill_opacity_spin.setToolTip(
            "How solid the fill is, separately from the line round it")
        self.fill_opacity_spin.setValue(int(self.default_style.fill_opacity * 100))
        self.fill_opacity_spin.valueChanged.connect(self._style_fill_opacity)
        self._style_widgets[FILL_OPACITY].append(
            style_bar.addWidget(self.fill_opacity_spin))
        self.default_button = QToolButton()
        self.default_button.setText("Set default")
        self.default_button.setToolTip(
            "Use the selected markup's compatible style for new markups of this kind")
        self.default_button.setEnabled(False)
        self.default_button.clicked.connect(self.set_selected_as_default)
        self._default_action = style_bar.addWidget(self.default_button)
        self.style_bar = style_bar
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
        self._refresh_style_controls()

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
        self.markups_panel = MarkupsPanel(self)
        self.dock_markups = self._dock("Markups", self.markups_panel,
                                       Qt.BottomDockWidgetArea, "dock_markups")
        self.toolsets_panel = ToolSetsPanel(self)
        self.dock_toolsets = self._dock("Tool sets", self.toolsets_panel,
                                        Qt.BottomDockWidgetArea, "dock_toolsets")
        self.bookmarks_panel = BookmarksPanel(self)
        self.bookmarks_panel.bookmarkActivated.connect(self.go_to_bookmark)
        self.dock_bookmarks = self._dock("Bookmarks", self.bookmarks_panel,
                                         Qt.BottomDockWidgetArea, "dock_bookmarks")
        self.reference_docks = [self.dock_markups,
                                self.dock_toolsets, self.dock_bookmarks]
        self._build_rails()
        self.resizeDocks([self.dock_pages, self.dock_properties], [220, 320],
                         Qt.Horizontal)

    # -- the icon rails ----------------------------------------------------
    #
    # Every panel is behind one icon on one of the two rails. Which side it is
    # on is remembered; dragging its icon across moves it.
    PANEL_ICONS = {
        "dock_pages": ("Pages", "panel_pages"),
        "dock_bookmarks": ("Bookmarks", "panel_bookmarks"),
        "dock_toolsets": ("Tool sets", "panel_toolsets"),
        "dock_markups": ("Markups", "panel_markups"),
        "dock_properties": ("Properties", "panel_properties"),
    }
    DEFAULT_SIDES = {
        "dock_pages": LEFT, "dock_bookmarks": LEFT, "dock_toolsets": LEFT,
        "dock_markups": LEFT,
        "dock_properties": RIGHT,
    }

    def _build_rails(self) -> None:
        self.panel_sides = load_sides(self.DEFAULT_SIDES)
        self.docks_by_name = {dock.objectName(): dock for dock in self.panels}
        for rail in (self.left_rail, self.right_rail):
            rail.toggled.connect(self.show_panel)
            rail.moved.connect(self.move_panel_to_side)
        for name in self.PANEL_ICONS:
            self._place_panel(name, self.panel_sides.get(name, LEFT), open_now=False)
        # One panel open on each side to begin with, so the rails explain
        # themselves without anything having to be read.
        self.show_panel("dock_pages", True)
        self.show_panel("dock_properties", True)

    def _place_panel(self, name: str, side: str, open_now: bool) -> None:
        dock = self.docks_by_name.get(name)
        if dock is None:
            return
        label, icon_name = self.PANEL_ICONS[name]
        rail = self.left_rail if side == LEFT else self.right_rail
        other = self.right_rail if side == LEFT else self.left_rail
        other.take(name)
        if name not in rail.buttons:
            rail.add(name, label, icon(icon_name))
        self.panel_sides[name] = side
        self.addDockWidget(AREAS[side], dock)
        dock.setVisible(open_now)
        rail.show_open(name, open_now)

    def rail_for(self, name: str) -> PanelRail:
        return (self.left_rail if self.panel_sides.get(name, LEFT) == LEFT
                else self.right_rail)

    def show_panel(self, name: str, open_now: bool) -> None:
        """Open or close a panel, keeping one active panel on each side."""
        dock = self.docks_by_name.get(name)
        if dock is None:
            return
        self._changing_panels = True
        try:
            if open_now:
                side = self.panel_sides.get(name, LEFT)
                for other_name, other_dock in self.docks_by_name.items():
                    if (other_name != name
                            and self.panel_sides.get(other_name, LEFT) == side):
                        other_dock.setVisible(False)
            dock.setVisible(bool(open_now))
            if open_now:
                dock.set_collapsed(False)
                dock.raise_()
        finally:
            self._changing_panels = False
        self.sync_rails()
        self.note_layout_change()

    def _panel_visibility_changed(self, name: str, visible: bool) -> None:
        """Apply the rail rule when a dock is opened outside the rail."""
        if self._changing_panels:
            return
        if visible:
            self.show_panel(name, True)
        else:
            self.sync_rails()
            self.note_layout_change()

    def _enforce_panel_limit(self) -> None:
        """Normalise older saved layouts that had several panels per side."""
        for side in (LEFT, RIGHT):
            visible = [name for name in self.PANEL_ICONS
                       if self.panel_sides.get(name, LEFT) == side
                       and not self.docks_by_name[name].isHidden()]
            if len(visible) > 1:
                self.show_panel(visible[0], True)
        self.sync_rails()

    def move_panel_to_side(self, name: str, side: str) -> None:
        """Drag a panel's icon to the other rail and the panel goes with it."""
        if self.panel_sides.get(name) == side:
            return
        dock = self.docks_by_name.get(name)
        was_open = dock is not None and not dock.isHidden()
        self._place_panel(name, side, open_now=False)
        if was_open:
            self.show_panel(name, True)
        save_sides(self.panel_sides)
        self.note_layout_change()

    def sync_rails(self) -> None:
        """Put the icons back in step with which panels are actually open.

        isHidden rather than isVisible: a panel in a window that has not been
        shown yet is not visible, but it has not been closed either, and its
        icon should say so.
        """
        for name, dock in self.docks_by_name.items():
            if name in self.PANEL_ICONS:
                self.rail_for(name).show_open(name, not dock.isHidden())

    def _build_menus(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("&File")
        for action in (self.act_new, self.act_new_tab, self.act_new_window, self.act_open,
                       None, self.act_save, self.act_save_as,
                       None, self.act_insert_pdf, self.act_insert_image_page,
                       self.act_import_toolset,
                       None, self.act_export_pdf,
                       self.act_export_png, self.act_export_markups,
                       None, self.act_preview, self.act_print, None, self.act_quit):
            file_menu.addSeparator() if action is None else file_menu.addAction(action)

        edit_menu = bar.addMenu("&Edit")
        for action in (self.act_undo, self.act_redo, None, self.act_cut, self.act_copy,
                       self.act_paste, self.act_paste_in_place, self.act_paste_here,
                       self.act_duplicate, self.act_delete, None,
                       self.act_select_all, self.act_lock, self.act_array):
            edit_menu.addSeparator() if action is None else edit_menu.addAction(action)
        order_menu = edit_menu.addMenu("Order")
        for action in (self.act_front, self.act_forward, self.act_backward, self.act_back):
            order_menu.addAction(action)
        align_menu = edit_menu.addMenu("Align")
        for key in ("left", "hcenter", "right", "top", "vcenter", "bottom"):
            align_menu.addAction(getattr(self, f"act_align_{key}"))
        text_menu = edit_menu.addMenu("Text")
        for action in (self.act_bold, self.act_italic, self.act_underline, None,
                       self.act_text_left, self.act_text_center, self.act_text_right,
                       None, self.act_font_increase, self.act_font_decrease):
            text_menu.addSeparator() if action is None else text_menu.addAction(action)
        view_menu = bar.addMenu("&View")
        for action in (self.act_zoom_in, self.act_zoom_out, self.act_actual_size,
                       self.act_fit_page,
                       self.act_fit_width, self.act_zoom_sel, None,
                       self.act_turn_view_cw, self.act_turn_view_acw,
                       self.act_turn_view_reset, None, self.act_grid,
                       self.act_snap, self.act_snap_items, self.act_snap_content,
                       self.act_snap_alignment, self.act_margins,
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
        self.selection_menu = markup_menu.addMenu("Selected")
        self.selection_menu.aboutToShow.connect(self._rebuild_selection_menu)
        markup_menu.addSeparator()
        markup_menu.addAction(self.act_group)
        markup_menu.addAction(self.act_ungroup)
        markup_menu.addAction(self.act_autosize)
        markup_menu.addSeparator()
        markup_menu.addAction(self.act_format_painter)
        markup_menu.addAction(self.act_sticky)
        markup_menu.addAction(self.act_lock)
        markup_menu.addAction(self.act_hide)
        markup_menu.addAction(self.act_show_hidden)
        markup_menu.addAction(self.act_flatten)
        markup_menu.addAction(self.act_flatten_document)
        markup_menu.addAction(self.act_recover_flattened)
        markup_menu.addSeparator()
        markup_menu.addAction(self.act_renumber_counts)
        markup_menu.addAction(self.act_forget_defaults)
        markup_menu.addSeparator()
        markup_menu.addAction(self.act_apply_redactions)
        markup_menu.addSeparator()
        markup_menu.addAction(self.act_export_markups)

        # Mnemonic on the "g" for the same reason: Alt+P draws freehand.
        page_menu = bar.addMenu("Pa&ge")
        self.current_page_menu = page_menu.addMenu("Current")
        self.current_page_menu.aboutToShow.connect(self._rebuild_current_page_menu)
        page_menu.addSeparator()
        for action in (self.act_bookmark, None,
                       self.act_add_page, self.act_duplicate_page, self.act_delete_page,
                       None, self.act_page_setup, self.act_scale, self.act_header_footer,
                       None, self.act_doc_props):
            page_menu.addSeparator() if action is None else page_menu.addAction(action)

        insert_menu = bar.addMenu("&Insert")
        self.insert_tool_actions: dict[str, list[QAction]] = {}
        for tool in TOOLS:
            if tool.category == "Annotate":
                action = self.give_icon(QAction(tool.label, self), tool.icon)
                action.triggered.connect(lambda _c=False, key=tool.key: self.select_tool(key))
                insert_menu.addAction(action)
                self.insert_tool_actions.setdefault(tool.key, []).append(action)
        insert_menu.addSeparator()
        # Every drawing tool, on the menu as well as on the toolbar. Somebody
        # who does not know which button the polygon is under can find it by
        # reading, which is what a menu bar is for.
        for heading in ("Navigate", "Draw", "Measure"):
            title = {"Navigate": "Navigation", "Draw": "Markup",
                     "Measure": "Measurement"}[heading]
            sub = insert_menu.addMenu(title)
            for tool in tools_in(heading):
                if tool.mode == NONE and heading != "Navigate":
                    continue
                entry = self.give_icon(QAction(tool.label, self), tool.icon)
                entry.setToolTip(tool.hint)
                entry.triggered.connect(
                    lambda _c=False, key=tool.key: self.select_tool(key))
                sub.addAction(entry)
                self.insert_tool_actions.setdefault(tool.key, []).append(entry)
        insert_menu.addSeparator()
        insert_menu.addAction(self.act_contents)
        insert_menu.addSeparator()
        insert_menu.addAction(self.act_insert_pdf)
        insert_menu.addAction(self.act_insert_image_page)

        settings_menu = bar.addMenu("&Settings")
        settings_menu.addAction(self.act_preferences)
        settings_menu.addAction(self.act_shortcuts)

        help_menu = bar.addMenu("&Help")
        help_menu.addAction(self.act_find_tool)
        help_menu.addSeparator()
        help_menu.addAction(self.act_about)

    def _build_status(self) -> None:
        status = CenteredStatusBar()
        self.setStatusBar(status)
        # What is going on and where the pointer is are both things the footer
        # says rather than things it offers, so they sit together on the left.
        # The controls are permanent widgets and gather on the right, and the
        # page navigation goes in the middle of what is left between them.
        self.status_hint = QLabel("Ready")
        status.addWidget(self.status_hint)

        self.status_position = QLabel("")
        self.status_position.setMinimumWidth(150)
        status.addWidget(self.status_position)


        self.status_scale = QToolButton()
        self.status_scale.setText("Scale 1:1")
        self.status_scale.setAutoRaise(True)
        self.status_scale.setToolTip("Click to set the page scale")
        self.status_scale.clicked.connect(self.calibrate_dialog)
        status.addPermanentWidget(self.status_scale)

        # The page bar, in the middle where Bluebeam keeps it: back a page,
        # which page, on a page — and beside it the two buttons that get used
        # constantly, fit-width and the grid.
        self.page_navigation = QWidget()
        page_bar = QHBoxLayout(self.page_navigation)
        page_bar.setContentsMargins(4, 0, 4, 0)
        page_bar.setSpacing(4)

        self.page_back = QToolButton()
        self.page_back.setText("‹")
        self.page_back.setAutoRaise(True)
        self.page_back.setToolTip("Previous page")
        self.page_back.clicked.connect(lambda: self.go_to_page(self.current_index - 1))
        page_bar.addWidget(self.page_back)

        self.page_spin = QSpinBox()
        self.page_spin.setRange(1, 1)
        self.page_spin.setPrefix("Page ")
        self.page_spin.lineEdit().setAlignment(Qt.AlignCenter)
        self.page_spin.valueChanged.connect(lambda value: self.go_to_page(value - 1))
        page_bar.addWidget(self.page_spin)

        self.page_total = QLabel("of 1")
        page_bar.addWidget(self.page_total)

        self.page_label = QLabel("")
        self.page_label.setAlignment(Qt.AlignCenter)
        self.page_label.setToolTip("Current page label")
        page_bar.addWidget(self.page_label)

        self.page_forward = QToolButton()
        self.page_forward.setText("›")
        self.page_forward.setAutoRaise(True)
        self.page_forward.setToolTip("Next page")
        self.page_forward.clicked.connect(lambda: self.go_to_page(self.current_index + 1))
        page_bar.addWidget(self.page_forward)
        status.set_center_widget(self.page_navigation)

        self.status_fit = QToolButton()
        self.status_fit.setAutoRaise(True)
        self.status_fit.setText("Fit width")
        self.status_fit.setToolTip("Fit the page across the window")
        self.status_fit.clicked.connect(self.view.fit_width)
        status.addPermanentWidget(self.status_fit)

        self.status_scroll = QToolButton()
        self.status_scroll.setAutoRaise(True)
        self.status_scroll.setText("Continuous")
        self.status_scroll.setToolTip(
            "Choose continuous document scrolling or one-page wheel navigation")
        scroll_menu = QMenu(self.status_scroll)
        scroll_group = QActionGroup(self.status_scroll)
        scroll_group.setExclusive(True)
        self.scroll_actions = {}
        for mode, label in (("continuous", "Continuous"), ("page", "Page")):
            action = scroll_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(mode == "continuous")
            action.triggered.connect(
                lambda _checked=False, wanted=mode: self.set_scroll_mode(wanted))
            scroll_group.addAction(action)
            self.scroll_actions[mode] = action
        self.status_scroll.setMenu(scroll_menu)
        self.status_scroll.setPopupMode(QToolButton.InstantPopup)
        status.addPermanentWidget(self.status_scroll)

        self.status_grid = QToolButton()
        self.status_grid.setAutoRaise(True)
        self.status_grid.setCheckable(True)
        self.status_grid.setText("Grid")
        self.status_grid.setToolTip("Show the grid on this page")
        self.status_grid.toggled.connect(
            lambda on: self.set_page_grid(self.current_index, on))
        status.addPermanentWidget(self.status_grid)

        self.status_snap = QToolButton()
        self.status_snap.setAutoRaise(True)
        self.status_snap.setText("Snap")
        self.status_snap.setToolTip("Choose what drawing points snap to")
        snap_menu = QMenu(self.status_snap)
        for action in (self.act_snap, self.act_snap_items,
                       self.act_snap_content, self.act_snap_alignment):
            snap_menu.addAction(action)
        self.status_snap.setMenu(snap_menu)
        self.status_snap.setPopupMode(QToolButton.InstantPopup)
        status.addPermanentWidget(self.status_snap)

        self.status_size = QToolButton()
        self.status_size.setAutoRaise(True)
        self.status_size.setToolTip("The paper and its margins — click to change them")
        self.status_size.clicked.connect(self.page_setup)
        status.addPermanentWidget(self.status_size)

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
        self.markups_panel.markupPicked.connect(self.pick_markup)
        self.undo_stack.cleanChanged.connect(lambda _clean: self.update_title())

    # ==================================================================
    # document lifecycle
    # ==================================================================
    # Every window built this way is kept here. A QMainWindow with nothing
    # referring to it is collected the moment the call that made it returns,
    # and the window vanishes as it is being looked at.
    _windows: list = []

    # -- one document per tab ----------------------------------------------
    def _current_document_state(self, tool: Optional[str] = None) -> dict:
        # The tool belongs to the document being worked on, not to the window:
        # coming back to a drawing should find the pen still in hand. It has
        # to be read before the switch puts the tool down, so it is passed in.
        return {"document": self.document, "scene": self.scene,
                "undo_stack": self.undo_stack, "index": self.current_index,
                "tool": tool or self.view.tool_key}

    def _adopt_document_state(self, state: dict) -> None:
        self.document = state["document"]
        self.scene = state["scene"]
        self.undo_stack = state["undo_stack"]
        self.current_index = state["index"]
        if self.scene is not None:
            self.view.setScene(self.scene)
        self.rebuild_scenes()
        self.select_tool(state.get("tool") or "select")
        self.refresh_lists()
        self.update_title()
        self._refresh_undo_actions()

    def _tab_title(self, document) -> str:
        return os.path.basename(document.path) if document.path else "Untitled"

    def open_in_new_tab(self, document=None) -> int:
        """Put another document beside this one, with a tab of its own."""
        held = self.view.tool_key
        self.view.escape_everything()
        if not self._open_documents:
            self._open_documents.append(self._current_document_state(held))
            self.document_tabs.blockSignals(True)
            self.document_tabs.addTab(self._tab_title(self.document))
            self.document_tabs.blockSignals(False)
        else:
            self._open_documents[self.document_tabs.currentIndex()] = \
                self._current_document_state(held)
        stack = QUndoStack(self)
        stack.cleanChanged.connect(lambda _clean: self.update_title())
        fresh = {"document": document if document is not None else Document(),
                 "scene": None, "undo_stack": stack, "index": 0,
                 "tool": "select"}
        self._open_documents.append(fresh)
        self.document_tabs.blockSignals(True)
        where = self.document_tabs.addTab(self._tab_title(fresh["document"]))
        self.document_tabs.setCurrentIndex(where)
        self.document_tabs.blockSignals(False)
        self.document_tabs.setVisible(self.document_tabs.count() > 1)
        self._adopt_document_state(fresh)
        return where

    def switch_to_document(self, index: int) -> None:
        """Show the document on that tab, putting this one aside as it is."""
        if not (0 <= index < len(self._open_documents)):
            return
        held = self.view.tool_key
        self.view.escape_everything()
        for position, state in enumerate(self._open_documents):
            if state["document"] is self.document:
                self._open_documents[position] = self._current_document_state(held)
                break
        self._adopt_document_state(self._open_documents[index])

    def close_document_tab(self, index: int) -> None:
        """Close one document. The last one standing keeps the window."""
        if not (0 <= index < len(self._open_documents)):
            return
        if len(self._open_documents) == 1:
            self.new_document()
            return
        going = self._open_documents.pop(index)
        self.document_tabs.blockSignals(True)
        self.document_tabs.removeTab(index)
        self.document_tabs.blockSignals(False)
        self.document_tabs.setVisible(self.document_tabs.count() > 1)
        if going["document"] is self.document:
            self._adopt_document_state(
                self._open_documents[min(index, len(self._open_documents) - 1)])

    def refresh_document_tabs(self) -> None:
        """Tab names follow the documents they stand for."""
        for position, state in enumerate(self._open_documents):
            if position < self.document_tabs.count():
                self.document_tabs.setTabText(position,
                                              self._tab_title(state["document"]))

    def open_new_window(self) -> "MainWindow":
        """A second window, with a document, pages and tool of its own.

        Nothing is shared but the application: the two windows do not reach
        into each other's document, and the arrangement each of them saves is
        stamped so a late write from one cannot land on the other's.
        """
        window = type(self)()
        MainWindow._windows.append(window)
        window.destroyed.connect(
            lambda *_: MainWindow._windows.remove(window)
            if window in MainWindow._windows else None)
        # Offset from this one, so the new window is not exactly on top of the
        # old one and apparently missing.
        here = self.geometry()
        window.setGeometry(here.adjusted(36, 36, 36, 36))
        window.show()
        window.raise_()
        window.activateWindow()
        self.status_hint.setText("Opened a second window")
        return window

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
            self.open_path(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Open document", f"Could not open the file:\n{exc}")
            return
        self.undo_stack.clear()
        self.current_index = 0
        self.rebuild_scenes()
        self.view.fit_page()
        self.update_title()

    def open_path(self, path: str) -> None:
        """Open a document, or bring in a PDF that is not one yet.

        A saved document is itself a PDF, so what decides between the two is
        what the file holds and not what it is called: a PDF carrying a
        MarkForge record is a document and opens as one, whatever its name.
        """
        if project_io.carries_a_document(path):
            project_io.load_document(self.document, path)
            return
        document = Document()
        document.mode = "pdf"
        document.title = os.path.splitext(os.path.basename(path))[0]
        document.pages = []
        count = pdfio.page_count(path)
        if count < 1:
            raise OSError("The PDF contains no pages")
        pdfio.import_pages(document, path, list(range(count)), pdfio.FIT_ORIGINAL,
                           pdfio.BEST_DPI, at=0, vectors=True)
        # Opening a PDF is opening a document, not converting one. Save writes
        # this file back — the source page comes through untouched and the
        # markups go on top of it, the way Bluebeam saves a marked-up drawing.
        document.path = path
        document.modified = True
        self.document = document

    def save_document(self) -> bool:
        # A line still being typed is part of the document being saved, so it
        # is settled first — its answers worked out, its region kept or turned
        # into the note it turned out to be.
        self.view.end_item_edit()
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
        suggested = project_io.suggested_name(self.document)
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

    def keyPressEvent(self, event) -> None:
        """Escape works wherever the keyboard happens to be.

        A key that no widget wants ends up here. Escape is the one key that
        has to work from anywhere: half-way through placing a call-out, with
        the focus sitting in a panel, it is the only way out — and it used to
        go to the panel and be swallowed. So it is caught here as well, and
        unwinds whatever the page is half-way through.
        """
        if event.key() == Qt.Key_Escape and not event.modifiers():
            self.view.escape_everything()
            event.accept()
            return
        # And the same for the rest of the keys belonging to what is being
        # written. A click on a toolbar button or a panel takes the keyboard
        # with it while the caret is still in the words, and from there
        # Backspace and Enter went to a button that has no use for them: keys
        # that had apparently stopped working. A key nothing else wanted goes
        # back to the markup — unless somebody is typing in a field, whose
        # Backspace is its own.
        if self.view.is_editing() and not typing_somewhere_else():
            self.view.setFocus(Qt.OtherFocusReason)
            self.view.keyPressEvent(event)
            if event.isAccepted():
                return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        # Nothing is settled here on purpose. Finishing an open markup touches
        # the panels, and the arrangement written a few lines further down
        # would then be the arrangement that left behind, not the one that was
        # on screen. There is nothing to lose by leaving it: a markup's text is
        # kept level with the typing as it goes, so what is in the document is
        # what was typed either way.
        if not self.confirm_discard():
            event.ignore()
            return
        self.save_layout()
        # This window's arrangement is written now. The timer must not fire
        # afterwards: a second later this window is gone, another may have
        # saved a newer arrangement, and what would land is this one's — the
        # layout of a window that has been closed overwriting the layout of
        # the one still open.
        timer = getattr(self, "_layout_timer", None)
        if timer is not None:
            timer.stop()
        self._autosave.stop()
        self.clear_autosave()
        # Every open document has an undo stack of its own, and all of them
        # report a clean change back to this window. Leaving the ones behind
        # other tabs connected means they call a window that has gone.
        stacks = [self.undo_stack] + [state["undo_stack"]
                                      for state in self._open_documents]
        for stack in stacks:
            try:
                stack.cleanChanged.disconnect()
            except (RuntimeError, TypeError):
                pass
        event.accept()

    # ==================================================================
    # autosave and recovery
    # ==================================================================
    def autosave_path(self) -> str:
        if self.document.path:
            return self.document.path + ".autosave"
        return os.path.join(self.recovery_dir(), "untitled.pdf.autosave")

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
            project_io.save_document(self.document, path, enforce_extension=False,
                                     appearance=False)
            self.document.path = saved_path     # an autosave is not a save-as
            self.document.modified = True
            return path
        except Exception:                        # noqa: BLE001 - never interrupt typing
            return None

    def clear_autosave(self) -> None:
        for path in {self.autosave_path(),
                     os.path.join(self.recovery_dir(), "untitled.pdf.autosave")}:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass

    def offer_recovery(self) -> bool:
        """On start-up, offer to reopen whatever a previous session left behind."""
        path = os.path.join(self.recovery_dir(), "untitled.pdf.autosave")
        if not os.path.exists(path):
            return False
        answer = QMessageBox.question(
            self, "Recover unsaved work",
            "MarkForge found a document from a session that did not finish.\n\n"
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
        """Let the editor keep keys that would otherwise run global commands.

        Qt asks with a ShortcutOverride before it fires a shortcut. Accepting
        it means the key goes to whatever has focus instead. Symbol bindings
        are editor input, not document commands, and Ctrl+B/I/U retain their
        normal text-formatting meaning.
        """
        if event.type() == QEvent.ShortcutOverride and self.view.is_editing():
            sequence = QKeySequence(event.keyCombination())
            portable = sequence.toString(QKeySequence.PortableText).lower()
            reserved = {key.lower() for key in self.RESERVED_FOR_TEXT}
            binding = self.shortcuts.binding_for(sequence)
            if portable not in reserved and not (
                    binding is not None and (binding.kind == SYMBOL
                                             or binding.action_id in self.EDITOR_COMMANDS)):
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
        self.show_panel("dock_pages", True)
        self.show_panel("dock_properties", True)

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
            dock.hide()
        self.show_panel("dock_pages", True)
        self.show_panel("dock_properties", True)
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

    def _save_layout_unless_overtaken(self) -> None:
        """The delayed save, dropped if somebody else has written since.

        Stopping the timer on a direct save was not enough on its own: any
        arranging done afterwards starts it again, and by the time it fires
        another window may have saved or restored a newer arrangement. This
        window's older state would then land on top of it. Each save stamps
        the settings, so a pending one can tell it has been overtaken and stay
        out of the way.
        """
        settings = QSettings(ORGANISATION, APP_NAME)
        try:
            stored = int(settings.value("window/stamp", 0))
        except (TypeError, ValueError):
            stored = 0
        if stored > getattr(self, "_layout_stamp", 0):
            return
        self.save_layout()

    def save_layout(self) -> None:
        # A direct save consumes any delayed save already waiting. Otherwise
        # that stale timer can fire after a second window has restored a newer
        # arrangement and overwrite it with this older window's state.
        timer = getattr(self, "_layout_timer", None)
        if timer is not None:
            timer.stop()
        settings = QSettings(ORGANISATION, APP_NAME)
        try:
            stamp = int(settings.value("window/stamp", 0)) + 1
        except (TypeError, ValueError):
            stamp = 1
        settings.setValue("window/stamp", stamp)
        self._layout_stamp = stamp
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
        # What this window has caught up with. A delayed save from a window
        # still holding an older arrangement checks this before writing.
        try:
            self._layout_stamp = int(settings.value("window/stamp", 0))
        except (TypeError, ValueError):
            self._layout_stamp = 0
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

    def _restore_structure(self, snapshot: dict, preserve_view: bool = False) -> None:
        scroll = (self.view.horizontalScrollBar().value(),
                  self.view.verticalScrollBar().value())
        self.document.pages = [Page.from_dict(entry) for entry in snapshot["pages"]]
        self.current_index = snapshot.get("current", 0)
        self.rebuild_scenes()
        if preserve_view:
            self.view.horizontalScrollBar().setValue(scroll[0])
            self.view.verticalScrollBar().setValue(scroll[1])
        self.update_title()

    def _structural_change(self, description: str, mutate,
                           preserve_view: bool = False) -> None:
        before = self._structure_snapshot()
        scroll = (self.view.horizontalScrollBar().value(),
                  self.view.verticalScrollBar().value())
        mutate()
        self.rebuild_scenes()
        # Adding or removing a page moves the reader to it, the way inserting a
        # page in any document viewer does. The target is held over the scroll:
        # a short page (a photo, a small PDF sheet) leaves the next page over
        # the middle of the view, and that must not steal the selection back.
        target = self.current_index
        if preserve_view:
            self.view.horizontalScrollBar().setValue(scroll[0])
            self.view.verticalScrollBar().setValue(scroll[1])
        else:
            self.view.go_to_page_top(target)
        self.current_index = target
        self.view._shown_page = target
        self.follow_scrolled_page(target)
        after = self._structure_snapshot()
        restore = (lambda snapshot: self._restore_structure(snapshot, True)) \
            if preserve_view else self._restore_structure
        self.undo_stack.push(DocumentStructureCommand(before, after, description,
                                                      restore))
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
        """Copy the page — or the whole picked run — in after the last of it."""
        wanted = self.pages_acted_on(index)
        sources = [self.document.pages[which].to_dict() for which in wanted]
        target = wanted[-1] + 1

        def mutate():
            for offset, source in enumerate(sources):
                copy = Page.from_dict(source)
                copy.uid = os.urandom(8).hex()
                self.document.pages.insert(target + offset, copy)
            self.current_index = target
        self._structural_change("Duplicate page" if len(sources) == 1
                                else f"Duplicate {len(sources)} pages", mutate)

    def copy_page(self, index: Optional[int] = None) -> None:
        """Put a page — or the whole picked run — on the clipboard.

        Backgrounds and markups and all, so what is pasted is what was copied
        and not a page with its drawing missing.
        """
        wanted = self.pages_acted_on(index)
        keys: set = set()
        for which in wanted:
            source = self.document.pages[which]
            if source.frame is not None:
                keys |= set(source.frame.assets_used())
            if source.background_key:
                keys.add(source.background_key)
        assets = {}
        for key in keys:
            blob = self.document.asset(key)
            if blob:
                assets[key] = base64.b64encode(blob).decode("ascii")
        pages = [self.document.pages[which].to_dict() for which in wanted]
        # The single-page key stays for anything written against it, including
        # a clipboard put there by an older version of this app.
        payload = {"markforge_page": pages[0], "markforge_pages": pages,
                   "assets": assets}
        QApplication.clipboard().setText(json.dumps(payload))
        self.status_hint.setText(
            f"Copied page {wanted[0] + 1}" if len(wanted) == 1
            else f"Copied {len(wanted)} pages")

    def page_on_the_clipboard(self) -> Optional[dict]:
        """The page waiting on the clipboard, if there is one."""
        try:
            payload = json.loads(QApplication.clipboard().text() or "")
        except (ValueError, TypeError):
            return None
        if not isinstance(payload, dict) or "markforge_page" not in payload:
            return None
        return payload

    def paste_page(self, index: Optional[int] = None,
                   before: bool = False) -> None:
        """Put the copied page in beside this one, and go to where it landed."""
        payload = self.page_on_the_clipboard()
        if payload is None:
            self.status_hint.setText("There is no page on the clipboard")
            return
        which = self.page_index(index)
        target = which if before else which + 1
        for key, encoded in (payload.get("assets") or {}).items():
            if not self.document.asset(key):
                try:
                    self.document.put_asset(key, base64.b64decode(encoded))
                except (ValueError, TypeError):
                    pass

        waiting = payload.get("markforge_pages") or [payload["markforge_page"]]

        def mutate():
            for offset, source in enumerate(waiting):
                page = Page.from_dict(source)
                page.uid = os.urandom(8).hex()
                self.document.pages.insert(target + offset, page)
            self.current_index = target
        self._structural_change("Paste page" if len(waiting) == 1
                                else f"Paste {len(waiting)} pages", mutate)
        # Where they went, said the way a drop says it: the slot line at the
        # landing place and the pages themselves picked out.
        self.pages_panel.show_where_it_landed(target, len(waiting))
        # Land on it, and say where it went: a page inserted somewhere out of
        # sight is a page nobody can find.
        self.go_to_page(target)
        self.pages_panel.list.setCurrentRow(target)
        self.status_hint.setText(f"Page pasted in as page {target + 1}")

    def delete_page(self, index: Optional[int] = None) -> None:
        """Take out the page — or the whole run picked out in the panel."""
        if len(self.document.pages) <= 1:
            QMessageBox.information(self, "Delete page", "A document needs at least one page.")
            return
        going = self.pages_acted_on(index)
        # Never all of them: a document has to keep a page. The last one in
        # the run stays behind rather than the first, so what is left is the
        # end of what was there rather than the start of it.
        if len(going) >= len(self.document.pages):
            going = going[:len(self.document.pages) - 1]
        if not going:
            return
        asked = (f"Delete page {going[0] + 1}?" if len(going) == 1
                 else f"Delete these {len(going)} pages?")
        if QMessageBox.question(self, "Delete page", asked) != QMessageBox.Yes:
            return

        def mutate():
            # Backwards, so each removal leaves the ones still to go where
            # they were.
            for which in reversed(going):
                self.document.remove_page(which)
            self.current_index = max(0, going[0] - 1)
        self._structural_change("Delete page" if len(going) == 1
                                else f"Delete {len(going)} pages", mutate)

    def move_page(self, source: int, target: int, count: int = 1) -> None:
        """Move a page, or a run of them, to start at *target*."""
        count = max(int(count), 1)

        def mutate():
            self.current_index = self.document.move_pages(source, count, target)
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
        chosen = dialog.selection()
        # A dialog written before any of this says nothing about the last two,
        # and the answer to both is now fixed anyway: everything the file holds
        # comes across, at the best the sheet allows.
        path, indices, fit = chosen[:3]
        dpi = chosen[3] if len(chosen) > 3 else pdfio.BEST_DPI
        vectors = bool(chosen[4]) if len(chosen) > 4 else True
        if not path or not indices:
            QMessageBox.information(self, "Insert PDF", "No pages were selected.")
            return
        target = self.page_index(index) + (0 if before else 1)
        brought: list = []

        def mutate():
            brought.extend(pdfio.import_pages(self.document, path, indices, fit,
                                              dpi, at=target, vectors=vectors))
            self.current_index = target
        try:
            self._structural_change(f"Insert {len(indices)} PDF page(s)", mutate)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Insert PDF", str(exc))
            return
        self.view.fit_page()
        lines = sum(len(page.frame.markups()) if page.frame is not None else 0
                    for page in brought)
        said = f"Inserted {len(indices)} page(s) from {os.path.basename(path)}"
        if vectors:
            said += (f" — {lines} pieces of line work came with them"
                     if lines else " — no line work could be read out of this one")
        self.status_hint.setText(said)

    def insert_files_at(self, paths: list[str], row: int) -> int:
        """Put PDFs and images in as pages, starting where they were dropped.

        The pages panel is where pages live, so dropping a drawing on it is
        the obvious way to bring it in — and the line the drag draws says
        exactly which page it will land in front of. Says how many went in.
        """
        row = max(0, min(int(row), len(self.document.pages)))
        added = 0

        def mutate():
            nonlocal added
            at = row
            for path in paths:
                try:
                    if path.lower().endswith(".pdf"):
                        pages = pdfio.import_pages(
                            self.document, path,
                            list(range(pdfio.page_count(path))),
                            pdfio.FIT_ORIGINAL, at=at)
                        added += len(pages)
                        at += len(pages)
                    else:
                        pdfio.import_image(self.document, path,
                                           pdfio.FIT_ORIGINAL, at=at)
                        added += 1
                        at += 1
                except Exception as exc:  # noqa: BLE001
                    QMessageBox.critical(self, "Insert pages", str(exc))
            self.current_index = min(row, len(self.document.pages) - 1)
        self._structural_change("Insert dropped pages", mutate)
        if added:
            self.go_to_page(min(row, len(self.document.pages) - 1))
            self.status_hint.setText(
                f"Inserted {added} page(s) as page {row + 1}")
        return added

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
            # Which way up the sheet is, and nothing else. The size in
            # millimetres is the sheet's own size — A4 is 210 by 297 whichever
            # way it is turned — and the orientation says how it is being
            # used. Turning both swapped the page straight back to the shape
            # it started as, which is why rotating a page used to move every
            # markup on it and leave the paper exactly as it was.
            setup.orientation = (PORTRAIT if setup.orientation == LANDSCAPE
                                 else LANDSCAPE)
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
                page.pdf_key = None
                page.pdf_page_index = None
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

    def set_page_grid(self, index: Optional[int] = None,
                      on: bool = True) -> None:
        """Rule this page, or stop ruling it.

        The grid is the page's own from here on, so turning the document's
        grid on later does not put one back over a drawing.
        """
        pages = self.selected_pages() or [self.page_index(index)]

        def mutate():
            for which in pages:
                self.document.pages[which].grid = bool(on)
        self._structural_change("Grid on this page", mutate, preserve_view=True)
        self.view.viewport().update()
        many = f" on {len(pages)} pages" if len(pages) > 1 else ""
        self.status_hint.setText(f"Grid {'on' if on else 'off'}{many}")

    def set_page_running_text(self, index: Optional[int], which: str,
                              on: bool) -> None:
        """Put the running header or footer on this page, or take it off.

        A drawing sheet that came in with its own title block does not want a
        second one written across it, and one page in a set is often the
        exception. Whichever pages are picked out in the panel are all done at
        once, so a run of drawings is one gesture rather than twenty.
        """
        pages = self.selected_pages() or [self.page_index(index)]

        def mutate():
            for page in pages:
                setattr(self.document.pages[page], which, bool(on))
        self._structural_change(f"{which.title()} on this page", mutate)
        many = f" on {len(pages)} pages" if len(pages) > 1 else ""
        self.status_hint.setText(
            f"{which.title()} {'on' if on else 'off'}{many}")

    def selected_pages(self) -> list[int]:
        """Which pages the page panel has picked out, if it has picked any."""
        rows = [self.pages_panel.list.row(entry)
                for entry in self.pages_panel.list.selectedItems()]
        return sorted(row for row in rows if 0 <= row < len(self.document.pages))

    def pages_acted_on(self, index: Optional[int] = None) -> list[int]:
        """The pages a page command applies to, in order.

        A run picked out in the pages panel is what the command acts on, so
        taking a header off six drawing sheets is one gesture rather than six.
        Anything done to a page outside that run is done to that page alone —
        right-clicking page nine while pages one to three are picked out means
        page nine, not a set nobody was pointing at.
        """
        which = self.page_index(index)
        picked = self.selected_pages()
        if len(picked) > 1 and which in picked:
            return picked
        return [which]

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

    def _rebuild_current_page_menu(self) -> None:
        self.current_page_menu.clear()
        self.page_menu(self.current_index, self.current_page_menu)

    def _rebuild_selection_menu(self) -> None:
        self.selection_menu.clear()
        items = self.selected_items()
        if not items:
            empty = self.selection_menu.addAction("Nothing selected")
            empty.setEnabled(False)
            return
        item = items[0]
        point = item.mapToScene(item.local_rect().center())
        self.build_context_menu(item, point, self.selection_menu)

    def page_menu(self, index: int, menu: Optional[QMenu] = None) -> QMenu:
        """Everything you can do to one page — or to the run picked out.

        The wording says which: with six sheets picked out, "Delete these 6
        pages" is what the menu offers, so nothing is taken away by a command
        that read as being about one page.
        """
        index = self.page_index(index)
        acting = self.pages_acted_on(index)
        several = len(acting) > 1
        these = f"these {len(acting)} pages" if several else "page"
        menu = menu or QMenu(self)
        here = menu.addAction("Go here", lambda: self.go_to_page(index))
        here.setToolTip("Go to this page")
        bookmark = menu.addAction("Add bookmark", lambda: self.bookmark_page(index))
        bookmark.setToolTip("Add this page to the document bookmarks")
        if not several:
            rename = menu.addAction("Rename…", lambda: self.rename_page(index))
            rename.setToolTip("Give this page a custom label")
            reset = menu.addAction("Reset label", lambda: self.reset_page_label(index))
            reset.setToolTip("Restore the imported label, or the normal page number")
            reset.setEnabled(bool(self.document.pages[index].label))
        include = menu.addAction("Print")
        include.setToolTip("Include the selected page or pages in print and export")
        include.setCheckable(True)
        include.setChecked(all(self.document.pages[i].printable for i in acting))
        include.toggled.connect(
            lambda on, pages=tuple(acting): self.set_pages_printable(pages, on))
        menu.addSeparator()
        copy = menu.addAction("Copy pages" if several else "Copy page",
                              lambda: self.copy_page(index))
        copy.setToolTip(f"Copy {these}")
        # Named with the place it lands, because "Paste page" on its own does
        # not say where the page goes and there is nothing on screen to say
        # so either.
        waiting = self.page_on_the_clipboard()
        paste = menu.addAction("Paste after",
                               lambda: self.paste_page(index))
        paste.setToolTip(f"Paste a page after page {index + 1}")
        paste.setEnabled(waiting is not None)
        if waiting is None:
            paste.setText("Paste page")
            paste.setToolTip("There is no page on the clipboard")
        before = menu.addAction("Paste before",
                                lambda: self.paste_page(index, before=True))
        before.setToolTip(f"Paste a page before page {index + 1}")
        before.setEnabled(waiting is not None)
        menu.addSeparator()
        blank_before = menu.addAction("Blank before", lambda: self.add_page_before(index))
        blank_before.setToolTip("Insert a blank page before this page")
        blank_after = menu.addAction("Blank after", lambda: self.add_page(index))
        blank_after.setToolTip("Insert a blank page after this page")
        duplicate = menu.addAction("Duplicate pages" if several else "Duplicate page",
                                   lambda: self.duplicate_page(index))
        duplicate.setToolTip(f"Duplicate {these}")
        menu.addSeparator()
        pdf_before = menu.addAction("PDF before…",
                                    lambda: self.insert_pdf(index, before=True))
        pdf_before.setToolTip("Insert PDF pages before this page")
        pdf_after = menu.addAction("PDF after…", lambda: self.insert_pdf(index))
        pdf_after.setToolTip("Insert PDF pages after this page")
        image_before = menu.addAction(
            "Image before…", lambda: self.insert_image_page(index, before=True))
        image_before.setToolTip("Insert an image page before this page")
        image_after = menu.addAction("Image after…",
                                     lambda: self.insert_image_page(index))
        image_after.setToolTip("Insert an image page after this page")
        menu.addSeparator()
        first, last = acting[0], acting[-1]
        up = menu.addAction("Move up", lambda: self.move_page(
            first, first - 1, len(acting)))
        up.setEnabled(first > 0)
        down = menu.addAction("Move down", lambda: self.move_page(
            first, first + 1, len(acting)))
        down.setEnabled(last < len(self.document.pages) - 1)
        menu.addSeparator()
        menu.addSeparator()
        turn_cw = menu.addAction("Rotate clockwise",
                                 lambda: self.rotate_page(index, True))
        turn_cw.setToolTip("Turn the paper and everything drawn on it. To turn "
                           "only the way it is shown, use View ▸ Turn view.")
        turn_acw = menu.addAction("Rotate anticlockwise",
                                  lambda: self.rotate_page(index, False))
        turn_acw.setToolTip("Turn the paper and everything drawn on it anticlockwise")
        running = menu.addMenu("Header/footer")
        for which, label in (("header", "Show header"),
                             ("footer", "Show footer")):
            entry = running.addAction(label)
            entry.setCheckable(True)
            page = self.document.pages[index]
            entry.setChecked(getattr(page, f"shows_a_{which}")(
                self.document.settings))
            entry.toggled.connect(
                lambda on, i=index, w=which: self.set_page_running_text(i, w, on))
        running.addSeparator()
        wording = running.addAction("Edit wording…", self.edit_header_footer)
        wording.setToolTip("Edit the document's header and footer wording")
        grid = menu.addAction("Page grid")
        grid.setCheckable(True)
        grid.setChecked(self.document.pages[index].shows_a_grid(
            self.document.settings))
        grid.setToolTip("A grid belongs to the page it is on, and prints with "
                        "it.\nPages that came in from a PDF start without one.")
        grid.toggled.connect(lambda on, i=index: self.set_page_grid(i, on))
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
        delete = menu.addAction("Delete pages" if several else "Delete page",
                                lambda: self.delete_page(index))
        delete.setToolTip(f"Delete {these}")
        delete.setEnabled(len(self.document.pages) > 1)
        return menu

    def rename_page(self, index: int) -> None:
        """Give one page the label shown in the Pages panel."""
        index = self.page_index(index)
        page = self.document.pages[index]
        label, accepted = QInputDialog.getText(
            self, "Rename page", "Label", text=page.label)
        if not accepted:
            return
        label = label.strip()
        if label == page.label:
            return

        def mutate():
            page.label = label

        self._structural_change("Rename page", mutate, preserve_view=True)

    def reset_page_label(self, index: int) -> None:
        """Restore the source label where there is one, otherwise no override."""
        index = self.page_index(index)
        page = self.document.pages[index]
        restored = page.source_note.strip()
        if page.label == restored:
            return

        def mutate():
            page.label = restored

        self._structural_change("Reset page label", mutate, preserve_view=True)

    def set_pages_printable(self, indices, printable: bool) -> None:
        """Include or exclude the selected page run from every rendered export."""
        indices = tuple(i for i in indices if 0 <= i < len(self.document.pages))
        if not indices:
            return
        printable = bool(printable)
        if all(self.document.pages[i].printable == printable for i in indices):
            return

        def mutate():
            for i in indices:
                self.document.pages[i].printable = printable

        self._structural_change(
            "Include pages in print" if printable else "Exclude pages from print",
            mutate, preserve_view=True)

    # ==================================================================
    # scale
    # ==================================================================
    def calibrate_scale(self, measured_pt: Optional[float] = None) -> None:
        """Set the page scale, from a drawn distance or straight from a ratio."""
        if measured_pt is not None:
            dialog = dialogs.CalibrationLengthDialog(measured_pt, self)
            if dialog.exec() != dialogs.QDialog.Accepted:
                return
            length = dialog.length_text()
            if length is None:
                return
            old = self.current_page().scale
            scale = PageScale.from_calibration(
                measured_pt, length, display_unit=old.display_unit)
            scale.area_unit = old.area_unit
            scale.precision = old.precision
            self.current_page().scale = scale
            self.apply_scale_change()
            return
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

        Every measurement on the page is a number read off the scale, so they
        all have to be told; so does the takeoff list, which is those numbers
        added up.
        """
        self.refresh_scale_label()
        # Measurements and rectangle sizes are in the takeoff list too, so it
        # goes stale unless it is rebuilt with them.
        self.refresh_lists()
        self.refresh_selection()
        self.mark_modified()

    def set_area_unit(self, unit: str) -> None:
        if unit:
            self.current_page().scale.area_unit = unit
            self.refresh_lists()
            self.mark_modified()

    def refresh_scale_label(self) -> None:
        scale = self.current_page().scale
        self.status_scale.setText(f"Scale {scale.label}")
        self.status_scale.setToolTip(
            f"1 page point = {format_quantity(scale.length_per_pt, 5)}\nClick to change")
        self.refresh_page_bar()

    def refresh_page_bar(self) -> None:
        """The bar along the bottom, saying what this page is."""
        total = len(self.document.pages)
        self.page_total.setText(f"of {total}")
        self.page_back.setEnabled(self.current_index > 0)
        self.page_forward.setEnabled(self.current_index < total - 1)
        page = self.current_page()
        self.page_label.setText(f"· {page.label.strip()}" if page.label.strip() else "")
        setup = page.setup
        # The paper and the room round the writing, which is what somebody is
        # actually asking when they look down here.
        margins = {setup.margin_left, setup.margin_top,
                   setup.margin_right, setup.margin_bottom}
        room = (f"{setup.margin_left:g} mm" if len(margins) == 1
                else f"{setup.margin_left:g}/{setup.margin_top:g}/"
                     f"{setup.margin_right:g}/{setup.margin_bottom:g} mm")
        wide = setup.width_pt * PT_TO_MM
        tall = setup.height_pt * PT_TO_MM
        self.status_size.setText(f"{setup.size_name} {wide:.0f}×{tall:.0f}")
        self.status_size.setToolTip(
            f"{setup.size_name}, {setup.orientation} — {wide:.0f} × {tall:.0f} mm\n"
            f"Margins {room}\nClick to change the paper or the margins")
        self.status_grid.blockSignals(True)
        self.status_grid.setChecked(bool(page.shows_a_grid(self.document.settings)))
        self.status_grid.blockSignals(False)
        self._say_snap_state()

    # ==================================================================
    # tools & style
    # ==================================================================
    # ==================================================================
    # keyboard
    # ==================================================================
    COMMAND_ACTIONS = {
        "fit_page": "act_fit_page", "fit_width": "act_fit_width",
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
        # And everything else the window owns, which registered itself as it
        # was built.
        for key, action_id in self.action_ids.items():
            action = getattr(self, f"act_{key}", None)
            if action is None:
                continue
            sequence = self.shortcuts.sequence(action_id)
            current = action.shortcut().toString()
            if current in self.RESERVED_FOR_TEXT:
                continue
            action.setShortcut(QKeySequence(sequence) if sequence
                               else QKeySequence())
        for action_id, action in getattr(self, "symbol_actions", {}).items():
            action.setShortcut(QKeySequence(self.shortcuts.sequence(action_id)))

    def insert_symbol(self, text: str) -> None:
        """Put a symbol in at the cursor, wherever the cursor is."""
        if self.view.insert_symbol(text):
            return
        self.status_hint.setText(
            f"{text} has nowhere to go — start typing a markup first")

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
        self._refresh_style_controls()

    def _show_tool_extras(self, key: str) -> None:
        """Show the toolbar bits that belong to the tool now in hand."""
        for action in getattr(self, "_stamp_widgets", ()):
            action.setVisible(key == "stamp")
        for action in getattr(self, "_count_widgets", ()):
            action.setVisible(key == "count")

    def set_scroll_mode(self, mode: str) -> None:
        """Choose smooth document scrolling or one-page wheel navigation."""
        mode = "page" if mode == "page" else "continuous"
        self.view.scroll_mode = mode
        label = "Page" if mode == "page" else "Continuous"
        self.status_scroll.setText(label)
        for key, action in self.scroll_actions.items():
            action.setChecked(key == mode)
        self.status_hint.setText(f"{label} scrolling")


    def _refresh_style_controls(self) -> None:
        """Show only style controls meaningful for the selection or tool."""
        if not hasattr(self, "_style_widgets"):
            return
        items = self.selected_items()
        active = items[0] if items else None
        self._style_own_look = False
        if items:
            supported = common_capabilities(items)
        else:
            active = self._style_default_item()
            # Nothing is selected, so these controls set what the next markup
            # of this kind starts as, which is a different question from what
            # can be changed about one that already exists.
            supported = capabilities(active, for_default=True) \
                if active is not None else set()
            if isinstance(active, (ImageItem, SnapshotItem)):
                # These two are not drawn with the toolbar's pen, so what the
                # controls show and change is the look remembered for them.
                self._style_own_look = True
                toolsets.apply_default(active)
        for field, actions in self._style_widgets.items():
            for action in actions:
                action.setVisible(field in supported)
        # With nothing selected and a tool that styles nothing, every control
        # on this bar is hidden and what is left is an empty band with one
        # disabled button stranded in it. A toolbar with nothing to offer is
        # not a toolbar, so it goes until there is something to put on it.
        self._default_action.setVisible(bool(supported))
        self.style_bar.setVisible(bool(supported))
        if active is None:
            return
        controls = ((self.stroke_button, active.style.stroke, "set_color"),
                    (self.fill_button, active.style.fill, "set_color"),
                    (self.width_spin, active.style.width, "setValue"),
                    (self.dash_combo, active.style.line_style, "setCurrentText"),
                    (self.font_spin, active.style.font_size, "setValue"),
                    (self.hatch_combo, active.style.hatch or "plain",
                     "setCurrentText"),
                    (self.opacity_spin, int(round(active.style.opacity * 100)),
                     "setValue"),
                    (self.fill_opacity_spin,
                     int(round(active.style.fill_opacity * 100)), "setValue"))
        for control, value, method in controls:
            control.blockSignals(True)
            getattr(control, method)(value)
            control.blockSignals(False)

    # -- undo --------------------------------------------------------------
    def _open_editor_document(self):
        """The text document being typed into, if anything is being typed into."""
        item = self.view.editing_item()
        editor = getattr(item, "_editor", None) if item is not None else None
        return editor.document() if editor is not None else None

    def undo_something(self) -> None:
        """Take back the typing first, then the document change under it."""
        document = self._open_editor_document()
        if document is not None and document.isUndoAvailable():
            document.undo()
        elif self.undo_stack.canUndo():
            self.undo_stack.undo()
        self._refresh_undo_actions()

    def redo_something(self) -> None:
        document = self._open_editor_document()
        if document is not None and document.isRedoAvailable():
            document.redo()
        elif self.undo_stack.canRedo():
            self.undo_stack.redo()
        self._refresh_undo_actions()

    def _refresh_undo_actions(self, *_args) -> None:
        document = self._open_editor_document()
        self.act_undo.setEnabled(
            bool(self.undo_stack.canUndo()
                 or (document is not None and document.isUndoAvailable())))
        self.act_redo.setEnabled(
            bool(self.undo_stack.canRedo()
                 or (document is not None and document.isRedoAvailable())))

    def toggle_sticky(self, on: bool) -> None:
        self.view.sticky_tool = on

    def _style_stroke(self, colour: str) -> None:
        self._style_change(STROKE, lambda style: setattr(style, "stroke", colour),
                           "Line colour")

    def _style_fill(self, colour: str) -> None:
        self._style_change(FILL, lambda style: setattr(style, "fill", colour),
                           "Fill colour")

    def _style_width(self, value: float) -> None:
        self._style_change(WIDTH, lambda style: setattr(style, "width", value),
                           "Line width")

    def _style_dash(self, value: str) -> None:
        self._style_change(DASH, lambda style: setattr(style, "line_style", value),
                           "Line style")

    def _style_font(self, value: float) -> None:
        self._style_change(FONT, lambda style: setattr(style, "font_size", value),
                           "Font size")

    def _style_hatch(self, value: str) -> None:
        self._style_change(HATCH, lambda style: setattr(style, "hatch", value or ""),
                           "Hatch")

    def _style_opacity(self, percent: int) -> None:
        value = max(percent, 1) / 100.0
        self._style_change(OPACITY, lambda style: setattr(style, "opacity", value),
                           "Opacity")

    def _style_fill_opacity(self, percent: int) -> None:
        value = percent / 100.0
        self._style_change(FILL_OPACITY,
                           lambda style: setattr(style, "fill_opacity", value),
                           "Fill opacity")

    def _style_change(self, field: str, mutate, description: str) -> None:
        """One toolbar control moved: change the selection, or the default.

        Most markups are drawn with the toolbar's own settings, so with nothing
        selected the toolbar is those settings. A photo and a snapshot are not:
        neither is drawn with a pen, and the frame each is given is remembered
        for that kind of markup on its own. With one of those tools in hand the
        toolbar edits that remembered look instead, which is what makes a line
        type settable for them at all.
        """
        if self._remember_style_default(mutate):
            return
        mutate(self.default_style)
        self._push_style(mutate, description,
                         predicate=lambda item: field in capabilities(item))

    def _remember_style_default(self, mutate) -> bool:
        """Change the stored look of the tool in hand. True if that is what this is."""
        if self.selected_items() or not getattr(self, "_style_own_look", False):
            return False
        item = self._style_default_item()
        if item is None:
            return False
        toolsets.apply_default(item)
        mutate(item.style)
        toolsets.remember_default(item)
        return True

    def _style_default_item(self):
        """A markup of the kind the tool in hand makes, for setting its look.

        The snapshot tool's factory makes the marquee that is dragged out, not
        the snapshot that comes back, so it is asked for by name.
        """
        tool = self.view.current_tool()
        if tool.key == "snapshot":
            return SnapshotItem()
        if tool.key == "calibrate" or tool.factory is None:
            return None
        return tool.factory()

    def _push_style(self, mutate, description: str, predicate=None) -> None:
        items = self.selected_items()
        if predicate is not None:
            items = [item for item in items if predicate(item)]
        if not items:
            return
        self.view.begin_snapshot()
        for item in items:
            mutate(item.style)
            if hasattr(item, "apply_style"):
                item.apply_style()
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

    def set_selected_as_default(self) -> None:
        items = self.selected_items()
        if len(items) == 1:
            self.set_as_default(items[0])

    def forget_defaults(self) -> None:
        """Put every kind of markup back to how it started."""
        toolsets.save_defaults({})
        self.status_hint.setText("Markups are back to their original look")

    def _apply_toolbar_style(self, item: MarkupItem) -> None:
        style = self.default_style
        if isinstance(item, (NoteItem, ImageItem, StampItem, FlagItem,
                             SnapshotItem)):
            # None of these is drawn with the pen the toolbar holds. A photo
            # and a snapshot each remember a look of their own, which is
            # applied straight after this; giving them the pen as well is how
            # a pasted image used to arrive wearing whatever colour the last
            # rectangle was drawn in.
            return
        if isinstance(item, TypewriterItem):
            # Words with no box round them is the whole of what a typewriter
            # is. It takes the toolbar's text settings and leaves the border
            # and the fill alone — either can still be turned on afterwards.
            item.style.text_color = style.stroke or item.style.text_color
            item.style.font_size = style.font_size
            item.style.font_family = style.font_family
            return
        if isinstance(item, RectItem) and item.kind in ("highlight", "redact"):
            item.style.opacity = style.opacity
            return
        if isinstance(item, PolyItem) and item.kind == "highlighter":
            if style.stroke:
                item.style.stroke = style.stroke
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
        self.default_button.setEnabled(len(items) == 1)
        self._refresh_style_controls()
        if len(items) == 1:
            self.status_hint.setText(items[0].display_name())
        # The list and the drawing are two views of one thing: what is picked
        # on the page is picked in the list, without either sending the choice
        # back to the other and fighting over it.
        self.markups_panel.follow_the_canvas()
        # The box round a group and the handles are painted over the canvas
        # rather than by the items, and Qt only repaints the part of the
        # canvas that changed. Selecting something changed no part of it, so
        # nothing was redrawn and the selection had nothing round it until a
        # menu opening forced the whole viewport to be painted again.
        self.view.viewport().update()

    def delete_selection(self) -> None:
        if self.view.editing_item() is not None:
            return                      # Delete belongs to the text being edited
        items = [item for item in self.selected_items() if self.view.editable(item)]
        if not items:
            return
        self.view.begin_snapshot()
        for item in items:
            detach(item)
        self.view.commit_snapshot("Delete markup")
        self.refresh_selection()

    SNAPSHOT_DPI = 300.0

    def take_snapshot(self, frame, region: QRectF) -> None:
        """Take a copy of *region* on *frame*.

        A snapshot brings the drawing across, not a photograph of it: what is
        stored is every line, letter and image that was under the marquee,
        recorded as the instructions that drew them. So it stays sharp however
        far it is zoomed into, and it prints as vectors rather than as a
        rectangle of pixels.

        It is not a rebuilt copy of the markups either — nothing recalculates,
        renumbers or shifts about when it lands somewhere else. It is the
        drawing as it stood, and it is its own kind of markup, not an image
        with a different name.

        A picture of it goes on the system clipboard as well, so it can still
        be pasted straight into an email or a report.
        """
        region = region.normalized()
        if frame is None or region.width() < 2 or region.height() < 2:
            self.status_hint.setText("Snapshot: drag a region to copy")
            return

        taken = frame.picture_items(region)
        picture = frame.render_items_picture(taken, region)
        if picture.isNull():
            self.status_hint.setText("Nothing in that region to copy")
            return
        data = bytes(picture.data())
        key = self.document.put_asset(f"snapshot-{os.urandom(6).hex()}.qpic", data)
        # What it was taken of travels with it. A recording can be replayed and
        # nothing else, so without this a snapshot could never be asked to
        # change colour — which is the one thing a redline snapshot is for.
        kept = []
        for item in taken:
            recorded = item.serialize()
            recorded["x"] = recorded.get("x", 0.0) - region.left()
            recorded["y"] = recorded.get("y", 0.0) - region.top()
            kept.append(recorded)
        payload = [{"type": "snapshot", "asset": key, "x": 0.0, "y": 0.0,
                    "rect": [0, 0, region.width(), region.height()],
                    "source_rect": [0, 0, region.width(), region.height()],
                    "source_items": kept,
                    "source_page": self.document.pages.index(frame.page) + 1
                    if frame.page in self.document.pages else 0,
                    "keep_aspect": True, "uid": os.urandom(8).hex()}]
        assets = {key: base64.b64encode(data).decode("ascii")}

        self._clipboard = payload
        mime = QMimeData()
        mime.setText(json.dumps({CLIPBOARD_TAG: payload, "assets": assets}))
        # For everything outside this application, which cannot read a
        # recording: rasterise this same filtered picture at printing
        # resolution. Rendering the page again here would put its background
        # and excluded worksheet items back into the system clipboard.
        scale = self.SNAPSHOT_DPI / 72.0
        cut = QImage(max(round(region.width() * scale), 1),
                     max(round(region.height() * scale), 1),
                     QImage.Format_ARGB32)
        cut.fill(Qt.transparent)
        painter = QPainter(cut)
        painter.scale(scale, scale)
        painter.drawPicture(0, 0, picture)
        painter.end()
        if not cut.isNull():
            mime.setImageData(cut)
        QApplication.clipboard().setMimeData(mime)
        self.status_hint.setText(
            "Snapshot taken — paste it back, or into anything else")

    def _clipboard_is_a_foreign_picture(self) -> bool:
        """Whether the clipboard holds a picture that did not come from here."""
        mime = QApplication.clipboard().mimeData()
        if mime is None or not mime.hasImage():
            return False
        text = (mime.text() or "").strip()
        if text.startswith("{") and CLIPBOARD_TAG in text:
            return False               # our own snapshot, with its items
        return True

    def paste_picture_from_clipboard(self) -> bool:
        """Put a picture from another program onto the page."""
        image = QApplication.clipboard().image()
        if image.isNull():
            return False
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        if not image.save(buffer, "PNG"):
            self.status_hint.setText("That picture could not be pasted")
            return False
        data = bytes(buffer.data())
        key = self.document.put_asset(f"pasted-{os.urandom(6).hex()}.png", data)
        # At 300 dpi if it is big enough to have come from a screen at that
        # size; otherwise at its own size in points, so it lands legibly.
        scale = 300.0 / 72.0 if image.width() > 900 else 1.0
        width, height = image.width() / scale, image.height() / scale
        payload = [{"type": "image", "asset": key, "x": 0.0, "y": 0.0,
                    "rect": [0, 0, width, height], "keep_aspect": True,
                    "uid": os.urandom(8).hex()}]
        self._paste_payload(payload)
        self.status_hint.setText("Picture pasted")
        return True

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
        lines = [item for item in (page.frame.markups() if page.frame else [])
                 if getattr(item, "from_drawing", False)]
        changed = self._ask_recolour(image, lines)
        if changed is None:
            return

        def mutate():
            page.background_key = changed
            # A deliberately recoloured raster no longer represents the
            # untouched source PDF and must not be replaced by it on export.
            page.pdf_key = None
            page.pdf_page_index = None
            if page.frame is not None:
                page.frame._background = None
            self.current_index = which
        self._structural_change("Change page colours", mutate)

    def recolour_item(self, item) -> None:
        """Change the colours of a picture on the page — a snapshot, say."""
        if isinstance(item, SnapshotItem):
            self.recolour_snapshot(item)
            return
        image = QImage()
        data = self.document.asset(getattr(item, "asset_key", ""))
        if not data or not image.loadFromData(data) or image.isNull():
            # Doing nothing at all, silently, is how this looked broken: the
            # menu entry was there and clicking it appeared to do nothing.
            QMessageBox.information(
                self, "Change colours",
                "There is no picture in this one to recolour.")
            return
        changed = self._ask_recolour(image)
        if changed is None:
            return
        self.view.begin_snapshot(self.view.involved_frames(item))
        item.asset_key = changed
        item.load_from_document(self.document)
        self.view.commit_snapshot("Change colours")
        self.refresh_selection()

    def recolour_snapshot(self, item) -> None:
        """Change a snapshot's colours, in the drawing rather than in a picture.

        A snapshot is a recording, and a recording cannot be asked what colour
        anything in it is. What it was taken of is kept beside it, so the
        colour change is made there and the recording is made again — which is
        why it stays sharp at any size afterwards, exactly as it was.
        """
        source = item.source_markups()
        if not source:
            QMessageBox.information(
                self, "Change colours",
                "This snapshot was taken before MarkForge kept what a snapshot "
                "was made of, so there is nothing left in it to recolour. Take "
                "it again and the colours will be yours to change.")
            return
        dialog = dialogs.RecolourDialog(self._snapshot_preview(item), self)
        if dialog.exec() != dialogs.QDialog.Accepted:
            return
        if not dialog.apply_to_lines(source):
            self.status_hint.setText("Nothing in that snapshot used that colour")
            return
        self.view.begin_snapshot(self.view.involved_frames(item))
        picture = item.redraw_from(source)
        self.document.put_asset(item.asset_key, bytes(picture.data()))
        self.view.commit_snapshot("Change colours")
        item.update()
        self.refresh_selection()

    def _snapshot_preview(self, item) -> QImage:
        """A picture of a snapshot, for the dialog to read its colours off."""
        taken = item.natural_size()
        width = max(int(taken.width()), 1)
        height = max(int(taken.height()), 1)
        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(0xFFFFFFFF)
        picture = item.picture()
        if picture is not None and not picture.isNull():
            painter = QPainter(image)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.drawPicture(0, 0, picture)
            painter.end()
        return image

    def _background_image(self, page):
        image = QImage()
        data = self.document.asset(page.background_key)
        if not data or not image.loadFromData(data) or image.isNull():
            return None
        return image

    def _ask_recolour(self, image, line_work=None) -> Optional[str]:
        """Run the dialog and store the result; the new asset key, or None.

        *line_work* is the page's own lines, when it has any. A PDF page keeps
        its line work as the page's own line work, so a colour
        change has to reach that too: repainting only the picture underneath
        left every line its old colour on top of a recoloured sheet.
        """
        dialog = dialogs.RecolourDialog(image, self)
        if dialog.exec() != dialogs.QDialog.Accepted:
            return None
        if line_work:
            dialog.apply_to_lines(line_work)
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

    def import_toolset(self, path: str = "") -> bool:
        """Bring a Bluebeam tool set in from a ``.btx`` file.

        Years of an engineer's own tools live in those files — sections, weld
        symbols, review stamps — and nobody rebuilds that by hand. What comes
        in are ordinary markups: they can be recoloured, resized, put in
        another set and drawn again like anything else.
        """
        if not path:
            path, _filter = QFileDialog.getOpenFileName(
                self, "Import a tool set", "",
                "Bluebeam tool sets (*.btx);;All files (*)")
            if not path:
                return False
        from ..io import btx
        try:
            group, skipped = toolsets.toolset_from_btx(path)
        except btx.BtxError as problem:
            QMessageBox.warning(self, "Import a tool set",
                                f"That file could not be read as a Bluebeam "
                                f"tool set.\n\n{problem}")
            return False
        if not group.entries:
            QMessageBox.information(self, "Import a tool set",
                                    "There was nothing in that tool set that "
                                    "could be brought across.")
            return False
        group = toolsets.add_toolset(group)
        self.toolsets_panel.rebuild()
        self.toolsets_panel.select_set(group.name)
        self.show_panel("dock_toolsets", True)
        message = f"Imported {len(group.entries)} tool(s) into “{group.name}”"
        if skipped:
            message += f" — {skipped} could not be read"
        self.status_hint.setText(message)
        return True

    def clipboard_payload(self) -> list:
        """What was copied, from here or from another window of this."""
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
        return payload

    def paste_in_place(self) -> None:
        """Put what was copied back exactly where it was, as Bluebeam does.

        Ctrl+V lands under the pointer, which is what you want most of the
        time. This is for the other times: the same detail on the next page,
        or the same note in the same corner of every sheet, where "the same
        place" is the whole point and hunting for the right pixel is not.
        """
        payload = self.clipboard_payload()
        if not payload:
            self.status_hint.setText("Nothing copied to paste")
            return
        self.view.begin_snapshot()
        self.view.scene().clearSelection()
        renamed: dict = {}
        frame = self.view.typing_frame()
        placed = 0
        for entry in payload:
            copy = dict(entry)
            copy["uid"] = os.urandom(8).hex()
            if copy.get("group"):
                copy["group"] = renamed.setdefault(copy["group"], os.urandom(6).hex())
            item = build_item(copy)
            if item is None:
                continue
            if hasattr(item, "load_from_document"):
                item.load_from_document(self.document)
            frame.add_markup(item)
            item.setSelected(True)
            placed += 1
        self.view.commit_snapshot("Paste in place")
        self.refresh_selection()
        self.status_hint.setText(
            f"Pasted {placed} markup(s) in the same place on this page")

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
        self.copy_selection()
        self.delete_selection()

    def paste_items(self) -> None:
        if self.view.text_clipboard("paste"):
            return
        payload = self._clipboard
        text = QApplication.clipboard().text()
        # A picture copied in another program is what the person wants pasted,
        # not whatever this window happened to copy last. Only the clipboard
        # knows what is really on it, so it is asked first.
        if self._clipboard_is_a_foreign_picture():
            if self.paste_picture_from_clipboard():
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
        self._paste_payload(payload)

    def _paste_payload(self, payload: list) -> None:
        """Put a clipboard payload down under the pointer."""
        self.view.begin_snapshot()
        self.view.scene().clearSelection()
        # A paste lands under the pointer, the way it does in Bluebeam.
        target = self.view.pointer_scene_pos()
        offset = None
        if target is not None and payload:
            frame = self.view.frame_at(target) or self.view.frame()
            local = frame.mapFromScene(target)
            first = payload[0]
            anchored_at_bottom = (len(payload) > 1
                                  or any(entry.get("group") for entry in payload)
                                  or first.get("type") in ("image", "snapshot")
                                  or first.get("kind") == "cloud")
            if anchored_at_bottom:
                extent = QRectF()
                for entry in payload:
                    preview = build_item(entry)
                    if preview is None:
                        continue
                    box = preview.mapRectToParent(
                        preview.local_rect().normalized())
                    extent = box if extent.isNull() else extent.united(box)
                offset = QPointF(local.x() - extent.left(),
                                 local.y() - extent.bottom())
            elif first.get("type") == "callout":
                rect = first.get("rect", [0, 0, 160, 50])
                offset = QPointF(local.x() - float(first.get("x", 0))
                                 - float(rect[0]),
                                 local.y() - float(first.get("y", 0))
                                 - float(rect[1]) - float(rect[3]) / 2)
            else:
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
            if hasattr(item, "load_from_document"):
                item.load_from_document(self.document)
            frame.add_markup(item)
            item.setSelected(True)
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
                if hasattr(copy, "load_from_document"):
                    copy.load_from_document(self.document)
                self.view.frame().add_markup(copy)
                copy.setSelected(True)
        self.view.commit_snapshot("Duplicate")
        self.refresh_selection()

    def select_all(self) -> None:
        for item in self.view.frame().markups():
            if item.isVisible():
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
        items = [i for i in self.selected_items() if not i.from_drawing]
        if not items:
            return
        scene = self.view.scene()
        self.view.begin_snapshot()
        # Only against what somebody drew. The page's own line work is the
        # page, so "send to back" means behind the other markups — not under
        # the drawing, where nothing would be seen of it again.
        others = [i for i in scene.markups()
                  if i not in items and not i.from_drawing]
        floor = max((i.zValue() for i in scene.markups() if i.from_drawing),
                    default=0.0)
        if mode == "front":
            top = max((i.zValue() for i in others), default=floor)
            for offset, item in enumerate(items, start=1):
                item.setZValue(top + offset)
        elif mode == "back":
            bottom = min((i.zValue() for i in others), default=floor + 1.0)
            for offset, item in enumerate(items, start=1):
                item.setZValue(bottom - offset)
        else:
            step = 1.5 if mode == "forward" else -1.5
            for item in items:
                item.setZValue(item.zValue() + step)
        self._keep_the_markups_over_the_drawing(floor)
        self.view.commit_snapshot("Change order")

    def _keep_the_markups_over_the_drawing(self, floor: float) -> None:
        """Nothing drawn on the page ends up under the page's own line work.

        Send the only markup on a sheet to the back and there is nothing to go
        behind, so it would go below the drawing itself and not be seen again.
        When an order change pushes anything down that far, the whole pile is
        renumbered from just above the drawing, keeping the order it has now.
        """
        drawn = [item for item in self.view.scene().markups()
                 if not item.from_drawing]
        if not drawn or min(item.zValue() for item in drawn) > floor:
            return
        for step, item in enumerate(sorted(drawn, key=lambda i: i.zValue()),
                                    start=1):
            item.setZValue(floor + step)

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
                    if hasattr(copy, "load_from_document"):
                        copy.load_from_document(self.document)
                    copy.setPos(item.pos() + offset)
                    self.view.frame().add_markup(copy)
                    copy.setSelected(True)
                    made += 1
                elif step_index == count:
                    item.setPos(item.pos() + offset)
                    item.setSelected(True)
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

    def pick_markup(self, page_index: int, uid: str) -> None:
        """Select the markup a row in the markups list stands for.

        Unlike a double-click it does not move the view: running an eye down
        a list should not drag the drawing about under the reader.
        """
        if self.current_index != page_index:
            self.go_to_page(page_index)
        scene = self.view.scene()
        scene.clearSelection()
        for item in scene.markups():
            if item.uid == uid:
                item.setSelected(True)
                break
        self.refresh_selection()

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

    def find_a_tool(self) -> None:
        """Type what you want to do; it says which tool does it.

        Fifty tools is more than anybody keeps in their head, and the answer
        to "how do I cloud this" should not be hunting along a toolbar. What
        is searched is every tool's name, what it is for, and the key it is
        on, so "revision", "cloud" and "C" all find the same thing.
        """
        from PySide6.QtWidgets import QInputDialog

        wanted, said = QInputDialog.getText(
            self, "Find a tool", "What do you want to do?")
        if not said or not wanted.strip():
            return
        found = self.tools_matching(wanted)
        if not found:
            self.status_hint.setText(f"Nothing here matches “{wanted.strip()}”")
            return
        best = found[0]
        self.select_tool(best.key)
        others = ", ".join(tool.label for tool in found[1:4])
        self.status_hint.setText(
            f"{best.label}"
            + (f" · {best.shortcut}" if best.shortcut else "")
            + (f" — also: {others}" if others else ""))

    @staticmethod
    def tools_matching(wanted: str) -> list:
        """Every tool whose name, description or key matches, best first."""
        words = [word for word in wanted.lower().split() if word]
        if not words:
            return []
        scored = []
        for tool in TOOLS:
            haystack = f"{tool.label} {tool.hint} {tool.category}".lower()
            key = tool.shortcut.lower()
            score = 0
            for word in words:
                if word == tool.label.lower() or word == key:
                    score += 10
                elif tool.label.lower().startswith(word):
                    score += 6
                elif word in haystack:
                    score += 2
            if score:
                scored.append((score, tool.label, tool))
        scored.sort(key=lambda row: (-row[0], row[1]))
        return [tool for _score, _label, tool in scored]


    def refresh_lists(self) -> None:
        self.markups_panel.rebuild(self.document)
        self.bookmarks_panel.rebuild(self.document)

    # ==================================================================
    # bookmarks
    # ==================================================================
    def add_bookmark_here(self) -> None:
        """Bookmark the page and place the reader is looking at."""
        # Ctrl+B belongs to the words wherever there are words: a run selected
        # inside a text box, the box being typed into, the cells picked out in
        # a table, or a text markup picked out on the page. Only with none of
        # those does it reach for a bookmark — being asked for a bookmark name
        # half-way through emboldening a heading is nobody's idea of help.
        if self.toggle_bold():
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

    # -- format painter ----------------------------------------------------
    #
    # Bluebeam's: pick up one markup's look, then click others to paint it on.
    # It is held until it is used or Esc is pressed, and the status bar says so
    # the whole time, because an invisible mode that changes what clicking does
    # is the kind of thing that ruins an afternoon.
    def format_painter(self) -> None:
        items = self.selected_items()
        if self._held_style is not None:
            self.put_the_format_painter_down()
            return
        if not items:
            self.status_hint.setText("Pick the markup whose look you want first")
            return
        source = items[0]
        style = source.style
        self._held_style = {
            "source_type": source.TYPE,
            "style": {key: getattr(style, key) for key in
                      ("stroke", "fill", "width")},
        }
        if isinstance(source, CalloutItem):
            self._held_style["callout"] = {
                key: getattr(style, key) for key in
                ("arrow_start", "arrow_end", "font_family", "font_size",
                 "bold", "italic", "underline", "text_color", "align", "valign")
            }
        brush = icon("format_painter").pixmap(24, 24)
        self.view.setCursor(QCursor(brush, 2, 22))
        self.status_hint.setText(
            f"Format painter: click what should look like this "
            f"{items[0].display_name().lower()} · Esc to put it down")

    def put_the_format_painter_down(self) -> None:
        """Drop the held look, if one is held. Escape's business."""
        if self._held_style is not None:
            self._held_style = None
            self.view.setCursor(self.view._cursor_for_tool(self.view.current_tool()))
            self.status_hint.setText("Format painter put down")

    def holding_a_format(self) -> bool:
        return self._held_style is not None

    def paint_format_onto(self, item) -> bool:
        """Give *item* the look the format painter is holding."""
        if self._held_style is None or item is None:
            return False
        if isinstance(item, ImageItem):
            self.status_hint.setText("Format painter: image content has no markup style")
            return False
        self.view.begin_snapshot(self.view.involved_frames(item))
        linework = isinstance(item, (RectItem, PolyItem, MeasureItem, _TextBase))
        fillable = isinstance(item, (RectItem, _TextBase))
        held = self._held_style["style"]
        if linework:
            item.style.stroke = held["stroke"]
            item.style.width = held["width"]
        if fillable:
            item.style.fill = held["fill"]
        if (self._held_style.get("source_type") == CalloutItem.TYPE
                and isinstance(item, CalloutItem)):
            for key, value in self._held_style.get("callout", {}).items():
                setattr(item.style, key, value)
            item.apply_style()
        item.touch()
        item.update()
        self.view.commit_snapshot("Format painter")
        self.refresh_selection()
        return True

    def hide_selection(self) -> None:
        """Take the selected markups off the page without deleting them."""
        items = [i for i in self.selected_items() if isinstance(i, MarkupItem)]
        if not items:
            return
        self.view.begin_snapshot(self.view.involved_frames(*items))
        for item in items:
            item.hidden = True
            item.setVisible(False)
        self.view.commit_snapshot("Hide markup")
        self.status_hint.setText(
            f"{len(items)} markup(s) hidden — Markup ▸ Show hidden brings them back")
        self.refresh_selection()

    def show_hidden(self) -> None:
        """Bring back everything that was hidden."""
        brought = 0
        frames = [page.frame for page in self.document.pages if page.frame]
        self.view.begin_snapshot(frames)
        for frame in frames:
            for item in frame.markups():
                if getattr(item, "hidden", False):
                    item.hidden = False
                    item.setVisible(True)
                    brought += 1
        self.view.commit_snapshot("Show hidden markups")
        self.status_hint.setText(f"{brought} markup(s) brought back")

    def flatten_selection(self) -> None:
        """Make selected items part of the page, using the recovery preference."""
        items = [i for i in self.selected_items() if isinstance(i, MarkupItem)]
        if not items:
            return
        from . import preferences

        recoverable = preferences.current().recover_flattened
        if self.interactive_prompts and QMessageBox.question(
                self, "Flatten",
                f"Flatten {len(items)} markup(s) into the page?\n\n"
                "They become part of the drawing: no longer movable, editable "
                "or selectable. " + (
                    "Recover can restore their source data."
                    if recoverable else
                    "Recovery data is disabled; saving discards their editable source.")) \
                != QMessageBox.Yes:
            return
        self._flatten_items(items, recoverable)


    @staticmethod
    def _flatten_class(item) -> str:
        """Which of the flatten dialog's classes *item* belongs to.

        Three, because they are flattened for different reasons. Words are
        flattened so nobody can retype them; a measurement is flattened so the
        number cannot drift off the scale it was taken at; everything else is
        flattened to make it part of the drawing.
        """
        from ..items.measure import CountItem, MeasureItem
        from ..items.text import _TextBase, FlagItem, NoteItem, StampItem

        if isinstance(item, (_TextBase, NoteItem, StampItem, FlagItem)):
            return "text"
        if isinstance(item, (MeasureItem, CountItem)):
            return "measurements"
        return "markups"

    def flatten_document(self) -> None:
        """Choose content classes and flatten matching items on every page."""
        from . import preferences

        recoverable = preferences.current().recover_flattened
        dialog = dialogs.FlattenDialog(recoverable, self)
        if dialog.exec() != dialogs.QDialog.Accepted:
            return
        chosen = dialog.chosen()
        items = [item for page in self.document.pages if page.frame is not None
                 for item in page.frame.markups()
                 if not item.flattened
                 and not item.from_drawing
                 and self._flatten_class(item) in chosen]
        if not items:
            self.status_hint.setText("Nothing matched those flatten choices")
            return
        self._flatten_items(items, recoverable)

    def _flatten_items(self, items: list[MarkupItem], recoverable: bool) -> None:
        """Flatten *items*, either retaining source or baking visual records."""
        self.view.begin_snapshot(self.view.involved_frames(*items))
        if recoverable:
            for item in items:
                item.locked_before_flatten = item.locked
                item.flattened = True
                item.flatten_recoverable = True
                item.set_locked(True)
                item.setFlag(QGraphicsItem.ItemIsSelectable, False)
                item.setSelected(False)
                # Part of the page means the pointer goes through it, not just
                # that it cannot be picked up: it must not take a click meant
                # for something in front of or behind it, and it must not
                # light up under the pointer either.
                item.setAcceptedMouseButtons(Qt.NoButton)
                item.setAcceptHoverEvents(False)
        else:
            by_frame = {}
            for item in items:
                frame = item.parentItem()
                if frame is not None:
                    by_frame.setdefault(frame, []).append(item)
            for frame, members in by_frame.items():
                region = QRectF()
                for item in members:
                    box = item.mapRectToParent(item.boundingRect())
                    region = box if region.isNull() else region.united(box)
                picture = frame.render_items_picture(members, region)
                if picture.isNull():
                    continue
                data = bytes(picture.data())
                key = self.document.put_asset(
                    f"flattened-{os.urandom(6).hex()}.qpic", data)
                baked = SnapshotItem(QRectF(0, 0, region.width(), region.height()))
                baked.asset_key = key
                baked.set_picture(picture)
                baked.source_rect = QRectF(0, 0, region.width(), region.height())
                baked.source_page = self.document.pages.index(frame.page) + 1
                baked.flattened = True
                baked.flatten_recoverable = False
                baked.set_locked(True)
                baked.setFlag(QGraphicsItem.ItemIsSelectable, False)
                baked.setZValue(min(member.zValue() for member in members))
                for member in members:
                    detach(member)
                frame.add_markup(baked, region.topLeft())
        self.view.commit_snapshot("Flatten")
        suffix = " · Recover can restore them" if recoverable else " · source discarded"
        self.status_hint.setText(f"{len(items)} item(s) flattened{suffix}")
        self.refresh_selection()

    def recover_flattened(self) -> None:
        """Restore every flattened item whose editable source was retained."""
        frames = [page.frame for page in self.document.pages if page.frame]
        items = [item for frame in frames for item in frame.markups()
                 if item.flattened and item.flatten_recoverable]
        if not items:
            self.status_hint.setText("No recoverable flattened items")
            return
        self.view.begin_snapshot(self.view.involved_frames(*items))
        for item in items:
            item.flattened = False
            item.set_locked(item.locked_before_flatten)
            item.setFlag(QGraphicsItem.ItemIsSelectable, True)
            # Give the pointer back what flattening took away, or a recovered
            # markup is visible, listed and selectable in the panel and still
            # cannot be touched on the page.
            item.setAcceptedMouseButtons(Qt.AllButtons)
            item.setAcceptHoverEvents(True)
        self.view.commit_snapshot("Recover flattening")
        self.status_hint.setText(f"Recovered {len(items)} item(s)")
        self.refresh_lists()
        self.view.viewport().update()

    def apply_to_pages(self, item) -> None:
        """Put a copy of this markup on other pages, in the same place."""
        if item is None or len(self.document.pages) < 2:
            self.status_hint.setText("There is only one page to put it on")
            return
        here = self.document.index_of(self.current_page())
        others = [index for index in range(len(self.document.pages)) if index != here]
        choice, accepted = QInputDialog.getItem(
            self, "Apply to pages", "Put a copy of this markup on:",
            ["Every other page", "Every page after this one",
             "Every page before this one"], 0, False)
        if not accepted:
            return
        if choice.endswith("after this one"):
            others = [index for index in others if index > here]
        elif choice.endswith("before this one"):
            others = [index for index in others if index < here]
        if not others:
            self.status_hint.setText("No pages to put it on")
            return
        payload = item.serialize()
        frames = [self.document.pages[index].frame for index in others
                  if self.document.pages[index].frame is not None]
        self.view.begin_snapshot(frames)
        for frame in frames:
            copy = build_item(dict(payload, uid=os.urandom(8).hex()))
            if copy is not None:
                frame.add_markup(copy, QPointF(item.pos()))
        self.view.commit_snapshot("Apply to pages")
        self.status_hint.setText(f"Copied onto {len(frames)} page(s)")

    def show_properties_panel(self) -> None:
        self.show_panel("dock_properties", True)
        self.refresh_selection()

    def _fill_leader_menu(self, menu, item, scene_pos: QPointF) -> None:
        """Adding and taking away leaders, on the menu itself.

        One comment about three bolts wants three leaders, and the only way to
        get the second one used to be to know that dragging did something. So
        it is written down — and written down on the menu rather than inside a
        sub-menu of it, because a thing you have to open a sub-menu to find is
        a thing nobody finds.

        Adding one asks which kind: an arrow at a place, or a cloud round a
        region. They are the same leader drawn two ways, and one call-out can
        carry both.
        """
        arrow = menu.addAction("Add arrow leader",
                               lambda: self.add_leader_to(item, "arrow"))
        arrow.setToolTip("A line with a head on it, dragged to what it is about")
        cloud = menu.addAction("Add cloud leader",
                               lambda: self.add_leader_to(item, "cloud"))
        cloud.setToolTip("A revision cloud round the area, joined to the note "
                         "by a plain line")
        which = item.leader_near(item.mapFromScene(scene_pos))
        if which is None and item.leaders:
            which = len(item.leaders) - 1
        if which is not None:
            menu.addAction("Remove leader",
                           lambda i=which: self.remove_leader_from(item, i))

    def add_leader_to(self, item, kind: str = "arrow") -> None:
        """Another leader on this note, clear of the ones it already has.

        A text box given a leader is a call-out, so it becomes one — the three
        are one object in different states, and this is the state changing.
        """
        if kind == "cloud":
            self.view.begin_cloud_leader(item)
            return
        self.view.begin_snapshot(self.view.involved_frames(item))
        item = self.becomes_a_callout(item)
        item.add_leader()
        item.touch()
        item.update()
        self.view.commit_snapshot("Add leader")
        self.refresh_selection()
        self.status_hint.setText(
            f"{len(item.leaders)} leader(s) — drag it to what it points at")

    def finish_cloud_leader(self, item, scene_rect: QRectF) -> None:
        """Attach a cloud leader around the region chosen on the canvas."""
        item = self.becomes_a_callout(item)
        corners = [scene_rect.topLeft(), scene_rect.topRight(),
                   scene_rect.bottomRight(), scene_rect.bottomLeft()]
        item.add_cloud_leader([item.mapFromScene(point) for point in corners])
        item.touch()
        item.update()
        self.view.commit_snapshot("Add cloud leader")
        self.refresh_selection()
        self.status_hint.setText(
            f"{len(item.leaders)} leader(s) — cloud attached where it was drawn")

    @staticmethod
    def room_for_a_cloud(item) -> list:
        """Where a fresh cloud leader starts out: beside the note, clear of it."""
        rect = item.local_rect().normalized()
        width = max(rect.width() * 0.7, 60.0)
        height = max(rect.height() * 0.9, 40.0)
        left = rect.right() + 48.0
        top = rect.center().y() - height / 2
        box = QRectF(left, top, width, height)
        return [box.topLeft(), box.topRight(), box.bottomRight(), box.bottomLeft()]

    def remove_leader_from(self, item, index: int) -> None:
        """Take one leader off — and the note with it, if it was the last."""
        self.view.begin_snapshot(self.view.involved_frames(item))
        item.remove_leader(index)
        item = self.becomes_a_text_box(item)
        item.touch()
        item.update()
        self.view.commit_snapshot("Remove leader")
        self.refresh_selection()

    def set_leader(self, item, wanted: bool) -> None:
        """Give a text box or call-out a leader, or take its leaders away."""
        if item is None or not isinstance(item, _TextBase):
            return
        if item.leader_shown == wanted:
            return
        self.view.begin_snapshot(self.view.involved_frames(item))
        if wanted:
            item = self.becomes_a_callout(item)
            item.add_leader()
        else:
            item.remove_leader()
            item = self.becomes_a_text_box(item)
        item.touch()
        item.update()
        self.view.commit_snapshot("Add leader" if wanted else "Remove leader")
        self.refresh_selection()

    # -- one object, three states -----------------------------------------
    #
    # A text box, a call-out and a cloud call-out are the same thing with
    # different leaders on it: none, an arrow, a cloud. So they are not three
    # things to convert between by hand — the last leader coming off makes a
    # text box, and the first one going on makes a call-out, and neither is
    # something anybody has to ask for.
    def becomes_a_callout(self, item):
        """A text box given a leader is a call-out. Says which item to use."""
        if isinstance(item, CalloutItem) or not isinstance(item, TextItem):
            return item
        return self._swap_text_kind(item, CalloutItem)

    def becomes_a_text_box(self, item):
        """A call-out whose last leader has gone is a text box."""
        if not isinstance(item, CalloutItem) or item.leaders:
            return item
        return self._swap_text_kind(item, TextItem)

    def _swap_text_kind(self, item, kind):
        """Put a *kind* in this item's place, keeping everything about it."""
        frame = item.parentItem()
        if frame is None:
            return item
        data = item.serialize()
        fresh = kind()
        fresh.deserialize(data)
        fresh.setPos(item.pos())
        fresh.setRotation(item.rotation())
        fresh.setZValue(item.zValue())
        was_selected = item.isSelected()
        frame.remove_markup(item)
        frame.add_markup(fresh)
        if was_selected:
            self.view.scene().clearSelection()
            fresh.setSelected(True)
        return fresh

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

    def toggle_bold(self) -> bool:
        """Embolden the words. Says whether it found any.

        Four places count, in the order the caret would be found in them: a
        run of text selected inside a box being typed into, that whole box,
        the cells picked out in a table, and the text markups selected on the
        page. Returning False is what tells Ctrl+B it is free to mean
        "bookmark" instead.
        """
        if self.bold_the_selected_run():
            return True

        item = self.view.editing_item()
        if item is None:
            items = [i for i in self.selected_items()
                     if isinstance(i, _TextBase) and not i.locked]
            if not items:
                return False
            self.view.begin_snapshot(self.view.involved_frames(*items))
            wanted = not all(i.style.bold for i in items)
            for markup in items:
                markup.style.bold = wanted
                markup.apply_style()
                markup.touch()
                markup.update()
            self.view.commit_snapshot("Bold")
            return True

        if not hasattr(item, "style") or item.locked:
            return False
        self.view.begin_snapshot(self.view.involved_frames(item))
        item.style.bold = not item.style.bold
        if hasattr(item, "apply_style"):
            item.apply_style()
        item.touch()
        item.update()
        self.view.commit_snapshot("Bold")
        return True

    def bold_the_selected_run(self) -> bool:
        """Embolden just the words picked out under the caret, if any are."""
        return self._style_the_selected_run("bold")

    def toggle_italic(self) -> bool:
        """Italicise the words, in the same four places Bold looks in."""
        return self._toggle_text_style("italic")

    def toggle_underline(self) -> bool:
        """Underline the words, in the same four places Bold looks in."""
        return self._toggle_text_style("underline")

    def _toggle_text_style(self, which: str) -> bool:
        """Bold, italic or underline, wherever the words happen to be."""
        if self._style_the_selected_run(which):
            return True
        item = self.view.editing_item()
        if item is None:
            items = [i for i in self.selected_items()
                     if isinstance(i, _TextBase) and not i.locked]
            if not items:
                return False
            self.view.begin_snapshot(self.view.involved_frames(*items))
            wanted = not all(getattr(i.style, which) for i in items)
            for markup in items:
                setattr(markup.style, which, wanted)
                markup.apply_style()
                markup.touch()
                markup.update()
            self.view.commit_snapshot(which.capitalize())
            return True
        if not hasattr(item, "style") or item.locked:
            return False
        self.view.begin_snapshot(self.view.involved_frames(item))
        setattr(item.style, which, not getattr(item.style, which))
        if hasattr(item, "apply_style"):
            item.apply_style()
        item.touch()
        item.update()
        self.view.commit_snapshot(which.capitalize())
        return True

    def _style_the_selected_run(self, which: str) -> bool:
        """Style just the words picked out under the caret, if any are.

        The run, not the box. Picking three words out of a sentence and
        pressing Ctrl+B has to embolden those three and leave the rest of the
        sentence alone; the whole-box style is what happens when nothing is
        picked out.
        """
        editor = self.view.text_editor()
        if editor is None:
            return False
        cursor = editor.textCursor()
        if not cursor.hasSelection():
            return False
        fmt = QTextCharFormat()
        current = cursor.charFormat().font()
        if which == "bold":
            fmt.setFontWeight(QFont.Normal if current.bold() else QFont.Bold)
        elif which == "italic":
            fmt.setFontItalic(not current.italic())
        else:
            fmt.setFontUnderline(not current.underline())
        cursor.mergeCharFormat(fmt)
        return True

    def format_content(self, alignment: str = "", font_delta: float = 0.0) -> bool:
        """Align or resize the text-bearing selection in its active context."""
        item = self.view.editing_item()

        editor = self.view.text_editor()
        if editor is not None and isinstance(item, _TextBase) and not item.locked:
            self.view.begin_snapshot(self.view.involved_frames(item))
            cursor = editor.textCursor()
            if not cursor.hasSelection():
                cursor.select(QTextCursor.BlockUnderCursor)
            if alignment:
                block = QTextBlockFormat()
                block.setAlignment({"left": Qt.AlignLeft,
                                    "center": Qt.AlignHCenter,
                                    "right": Qt.AlignRight}[alignment])
                cursor.mergeBlockFormat(block)
            if font_delta:
                current = cursor.charFormat().fontPointSize() or item.style.font_size
                fmt = QTextCharFormat()
                fmt.setFontPointSize(max(3.0, min(current + font_delta, 96.0)))
                cursor.mergeCharFormat(fmt)
            editor.setTextCursor(cursor)
            item.touch()
            item.update()
            self.view.commit_snapshot("Format text")
            self.status_hint.setText("Text formatted")
            return True

        selected = [entry for entry in self.selected_items() if not entry.locked]
        text_items = [entry for entry in selected if isinstance(entry, _TextBase)]
        if not text_items:
            return False
        self.view.begin_snapshot(self.view.involved_frames(*text_items))
        for entry in text_items:
            if alignment:
                entry.style.align = alignment
            if font_delta:
                entry.style.font_size = max(
                    3.0, min(entry.style.font_size + font_delta, 96.0))
            entry.apply_style()
            entry.touch()
        self.view.commit_snapshot("Format text")
        self.status_hint.setText("Text formatted")
        return True

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


    def _printer(self) -> QPrinter:
        printer = QPrinter(QPrinter.HighResolution)
        printer.setDocName(self.document.title or "MarkForge document")
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
        """Snap to the page grid, or stop.

        Two things switch this — the View menu and the button on the page bar
        — and until now neither told the other. Turn it off on the bar and the
        menu still read "on"; turn it off in the menu and the bar still looked
        armed. Whichever is used, both now say the same thing, which is the
        whole of "the toggle isn't being respected".
        """
        self.document.settings.snap_to_grid = bool(on)
        self._say_snap_state()

    def _say_snap_state(self) -> None:
        """Put every control that shows a snap setting back in step."""
        settings = self.document.settings
        for widget, value in (
                (getattr(self, "act_snap", None), settings.snap_to_grid),
                (getattr(self, "act_snap_items", None), settings.snap_to_items),
                (getattr(self, "act_snap_content", None), settings.snap_to_content),
                (getattr(self, "act_snap_alignment", None),
                 settings.snap_to_alignment)):
            if widget is None or widget.isChecked() == bool(value):
                continue
            widget.blockSignals(True)
            widget.setChecked(bool(value))
            widget.blockSignals(False)

    def toggle_item_snap(self, on: bool) -> None:
        self.document.settings.snap_to_items = bool(on)
        self._say_snap_state()

    def toggle_content_snap(self, on: bool) -> None:
        self.document.settings.snap_to_content = bool(on)
        self._say_snap_state()

    def toggle_alignment_snap(self, on: bool) -> None:
        self.document.settings.snap_to_alignment = bool(on)
        self._say_snap_state()

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
    def _fill_outline_menu(self, menu, item, scene_pos: QPointF) -> None:
        """What can be done to this shape's corners and sides.

        The same four things the held keys do, for anyone who would rather
        read them than remember them: a point in or out, a corner rounded, a
        side bent into an arc — and the drafting break symbol, which has no
        key of its own.

        The pointer picks which corner and which side, and when it is not near
        either of them — right in the middle of a big rectangle, say — the
        nearest are offered and the wording says so. This used to show nothing
        at all in that case, which is how a feature that is on every shape
        came to be one nobody could find.
        """
        local = item.mapFromScene(scene_pos)
        reach = 12.0 / max(self.view.zoom(), 0.05)
        corners = item.corner_points()
        vertex = self.view._point_near(item, local, reach)
        segment = self.view._segment_near(item, local, reach)
        on_a_corner = vertex is not None
        on_a_side = segment is not None
        if vertex is None:
            vertex = self._nearest_corner(corners, local)
        if segment is None:
            segment = self.view._segment_near(item, local, float("inf"))
        this_corner = "this" if on_a_corner else "the nearest"
        this_side = "this" if on_a_side else "the nearest"

        outline = menu.addMenu("This outline")
        if vertex is not None:
            round_off = outline.addAction(
                "Sharpen corner" if item.is_rounded(vertex) else "Round corner",
                lambda: self._reshape(item, "round", vertex))
            round_off.setToolTip(
                f"{'Sharpen' if item.is_rounded(vertex) else 'Round'} {this_corner} "
                "corner; Ctrl and the pointer over a corner does this too")
            if len(corners) > 2:
                take_out = outline.addAction("Remove point",
                    lambda: self._reshape(item, "delete", vertex))
                take_out.setToolTip(
                    f"Remove {this_corner} point; Shift and the pointer does this too")
        if segment is not None:
            add = outline.addAction(
                "Add point", lambda: self._reshape(
                    item, "add", segment, local if on_a_side else None))
            add.setToolTip(f"Put a point in {this_side} side")
            curve = outline.addAction(
                "Straighten side" if item.is_curved(segment) else "Arc side",
                lambda: self._reshape(item, "curve", segment))
            curve.setToolTip(f"Change {this_side} side between straight and arced")
            broken = bool(item.broken.get(segment))
            break_action = outline.addAction(
                "Remove break" if broken else "Insert break",
                lambda: self._reshape(item, "break", segment))
            break_action.setToolTip(
                f"{'Remove' if broken else 'Insert'} the structural break symbol "
                f"on {this_side} side")
        if outline.isEmpty():
            menu.removeAction(outline.menuAction())

    @staticmethod
    def _nearest_corner(corners, local: QPointF) -> Optional[int]:
        """Which corner is closest to the pointer, or nothing when there are none."""
        best, nearest = None, None
        for index, point in enumerate(corners):
            gap = (point.x() - local.x()) ** 2 + (point.y() - local.y()) ** 2
            if nearest is None or gap < nearest:
                best, nearest = index, gap
        return best

    def _reshape(self, item, what: str, index: int,
                 local: Optional[QPointF] = None) -> None:
        """One change to a shape's outline, as one undo step."""
        self.view.begin_snapshot(self.view.involved_frames(item))
        # A rectangle cannot hold any of this, so it stops being one first.
        item = self.view.swap_for_a_polygon(item)
        if what == "round":
            item.round_corner(index)
            said = "Round off a corner"
        elif what == "delete":
            item.delete_point(index)
            said = "Take out a point"
        elif what == "add":
            item.insert_point(local if local is not None
                              else item.curve_apex(index))
            said = "Put in a point"
        elif what == "break":
            item.break_segment(index)
            said = "Break symbol"
        else:
            item.curve_segment(index)
            said = "Bend into an arc"
        self.view.commit_snapshot(said)
        self.refresh_selection()

    def rectangle_to_polygon(self, item) -> None:
        """Swap a rectangle for the same shape drawn as a polygon.

        Asked for outright from the menu. It also happens on its own the
        moment anything is done to a rectangle's outline that a rectangle
        cannot hold — a fifth corner, a rounded one, a bowed side.
        """
        self.view.begin_snapshot(self.view.involved_frames(item))
        self.view.swap_for_a_polygon(item)
        self.view.commit_snapshot("Turn into a polygon")
        self.refresh_selection()

    def build_context_menu(self, item, scene_pos: QPointF,
                           menu: Optional[QMenu] = None) -> QMenu:
        menu = menu or QMenu(self)
        if item is not None:
            if isinstance(item, _TextBase):
                menu.addAction("Edit…", lambda: self.view.begin_item_edit(item))
            if isinstance(item, (ImageItem, SnapshotItem)):
                menu.addAction("Change colours…", lambda: self.recolour_item(item))
            if self.view.has_an_outline(item):
                # Rectangles and clouds included: four corners and four sides
                # is an outline like any other, and everything offered on a
                # polygon's is offered on theirs.
                self._fill_outline_menu(menu, item, scene_pos)
            if isinstance(item, RectItem) and item.kind in SIZED_SHAPES:
                convert = menu.addAction("Convert polygon",
                               lambda: self.rectangle_to_polygon(item))
                convert.setToolTip("Turn this rectangle or ellipse into a polygon")
                menu.addAction("Exact size…",
                               lambda: self.set_rectangle_size(item))
                show = menu.addAction("Show size")
                show.setCheckable(True)
                show.setChecked(item.show_size)
                show.toggled.connect(lambda on: self.set_size_visible(item, on))
            if isinstance(item, MeasureItem):
                menu.addAction("Edit text…", lambda: self.edit_measure_text(item))
                straight = menu.addAction("Inline text")
                straight.setToolTip("Keep the measurement text in line with its line")
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
            if isinstance(item, _TextBase):
                self._fill_leader_menu(menu, item, scene_pos)
            default = menu.addAction("Set default", lambda: self.set_as_default(item))
            default.setToolTip("Use these properties for new markups of this kind")
            add_tool = menu.addAction("Add tool…", lambda: self.add_to_toolset(item))
            add_tool.setToolTip("Add this item to a tool set")
            menu.addSeparator()
            menu.addAction(self.act_cut)
            menu.addAction(self.act_copy)
            menu.addAction(self.act_paste)
            menu.addAction(self.act_duplicate)
            menu.addAction(self.act_format_painter)
            menu.addAction(self.act_delete)
            menu.addSeparator()
            order = menu.addMenu("Order")
            for action in (self.act_front, self.act_forward, self.act_backward, self.act_back):
                order.addAction(action)
            align = menu.addMenu("Align")
            align.setEnabled(len(self.selected_items()) > 1)
            for key in ("left", "hcenter", "right", "top", "vcenter", "bottom"):
                align.addAction(getattr(self, f"act_align_{key}"))
            menu.addAction(self.act_array)
            menu.addAction(self.act_lock)
            menu.addAction(self.act_hide)
            menu.addSeparator()
            menu.addAction(self.act_flatten)
            apply_pages = menu.addAction("Apply pages…",
                                         lambda: self.apply_to_pages(item))
            apply_pages.setToolTip("Copy this markup to chosen pages")
            menu.addAction("Properties", self.show_properties_panel)
        else:
            menu.addAction(self.act_paste)
            menu.addAction(self.act_paste_in_place)
            menu.addAction(self.act_paste_here)
            menu.addSeparator()
            insert = menu.addMenu("Insert here")
            for key in ("text", "callout", "note", "stamp", "image"):
                tool = TOOL_MAP[key]
                insert.addAction(icon(tool.icon), tool.label,
                                 lambda _c=False, k=key, p=scene_pos: self._insert_at(k, p))
            menu.addSeparator()
            menu.addAction(self.act_page_setup)
            menu.addAction(self.act_scale)
            menu.addAction(self.act_select_all)
        return menu

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
        if hasattr(item, "set_local_rect"):
            item.set_local_rect(QRectF(0, 0, width, height))
        if isinstance(item, ImageItem) and not self.load_image_into(item):
            return
        frame.add_markup(item, point)
        self.view.scene().clearSelection()
        item.setSelected(True)
        self.view.commit_snapshot(f"Add {tool.label.lower()}")
        if isinstance(item, _TextBase):
            self.view.begin_item_edit(item)
        self.refresh_selection()

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
        # Redaction is destructive. Keeping the original PDF here would put
        # the removed text and vectors straight back during export.
        page.pdf_key = None
        page.pdf_page_index = None
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
            self.act_snap_content.setChecked(self.document.settings.snap_to_content)
            self.act_snap_alignment.setChecked(
                self.document.settings.snap_to_alignment)
            self.act_margins.setChecked(self.document.settings.show_margins)
            self._refresh_all_scenes()
            self.update_title()

    def show_shortcuts(self) -> None:
        """F1 opens the one shortcut window there is."""
        self.edit_shortcuts()

    def show_about(self) -> None:
        dialogs.AboutDialog(self).exec()

