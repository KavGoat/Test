"""The CalcForge main window."""
from __future__ import annotations

import sys

import base64
import json
import os
import re
from typing import Optional

from PySide6.QtCore import (QBuffer, QByteArray, QEvent, QIODevice, QMimeData, QModelIndex, QObject,
                            QPoint, QPointF, QRect, QRectF,
                            QSize, Qt, QTimer, Signal)
from PySide6.QtGui import (QAction, QActionGroup, QColor, QFont, QFontInfo, QImage, QPixmap,
                           QKeySequence, QPainter, QTextBlockFormat,
                           QTextCharFormat, QTextCursor, QTransform, QUndoStack)
from PySide6.QtWidgets import (QAbstractButton, QTabBar, QApplication, QComboBox,
                               QDoubleSpinBox, QFontComboBox,
                               QFileDialog, QGraphicsItem, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QMainWindow,
                               QMenu, QMessageBox, QSizePolicy, QSpinBox,
                               QStatusBar, QToolBar, QToolButton, QVBoxLayout, QSplitter,
                               QWidget)

from ..core.document import (LANDSCAPE, MM_TO_PT, PAGE_SIZES, PORTRAIT,
                             PT_TO_MM, Document, Page, PageScale,
                             PageSetup)
from ..core.units import format_quantity, parse_unit
from ..io import export as export_io
from ..io import pdfio
from ..io import project as project_io
from ..items.base import (DASH_ARRAYS, HATCH_PATTERNS, MarkupItem, Style, build_item,
                          covered_rect, rename_groups)
from ..items.contents import ContentsItem
from ..items.measure import MeasureItem
from ..items.media import ImageItem
from ..items.shapes import PolyItem, RectItem
from ..items.snapshot import SnapshotItem
from ..items.text import (CalloutItem, FlagItem, NoteItem, StampItem,
                          TextItem, TypewriterItem, _TextBase)
from ..settings import app_settings
from . import dialogs
from .commands import DocumentStructureCommand
from . import bindable
from .icons import icon
from .panels import (_hatch_icon, fill_hatch_combo, hatch_index,
                     fill_line_style_combo, line_style_index,
                     BookmarksPanel, MarkupsPanel, PagesPanel, PropertiesPanel, ToolSetsPanel)
from .docks import PanelDock, load_panel_state, save_panel_state
from .rail import (AREAS, LEFT, RIGHT, PanelRail, RailBar, load_order,
                   load_sides, save_order, save_sides)
from .scene import DocumentScene, detach
from .shortcuts import MARKUP, COMMAND, INSERT, TOOL, ShortcutManager
from .shortcuts import SYMBOL as TYPED_SYMBOL
from .stylecaps import (CLOUD, CORNER, SYMBOL)
from .propbar import TOTALS as TOTALS_GROUP
from .stylecaps import (ARROW_SIZE, DASH, FILL, FILL_OPACITY, FONT, HATCH,
                        OPACITY, STROKE, WIDTH, capabilities,
                        common_capabilities)
from . import toolsets
from .tools import CATEGORIES, NONE, SKETCH, TOOL_MAP, TOOLS, tools_in
from .view import SIZED_SHAPES
from .view import PageView, typing_somewhere_else
from .widgets import ColorButton, keep_the_wheel_with_the_scroller, arrow_combo

APP_NAME = "CalcForge"
ORGANISATION = "CalcForge"
CLIPBOARD_TAG = "application/x-calcforge-items"


def _our_clipboard() -> Optional[dict]:
    """CalcForge's own copy on the clipboard, decoded, or None.

    Under its own type since phase 5, beside plain text and a picture for
    other programs; as JSON in the text before then, which is still read.
    """
    mime = QApplication.clipboard().mimeData()
    if mime is None:
        return None
    raw = ""
    if mime.hasFormat(CLIPBOARD_TAG):
        raw = bytes(mime.data(CLIPBOARD_TAG)).decode("utf-8", "replace")
    elif (mime.text() or "").strip().startswith("{"):
        raw = mime.text()
    if not raw:
        return None
    try:
        decoded = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return decoded if isinstance(decoded, dict) and CLIPBOARD_TAG in decoded else None


def _plain_text_of(item) -> str:
    """A copied markup as plain text: an equation as it reads
    ("Mu = 54 kN·m"), words as they are, anything else by what it is."""
    region = getattr(item, "region", None)
    if getattr(item, "IS_CALC", False) and region is not None:
        from ..calc.record import plain_text
        return plain_text(region)
    doc = getattr(item, "doc", None)
    if doc is not None and hasattr(doc, "toPlainText"):
        return doc.toPlainText()
    return item.summary() if hasattr(item, "summary") else ""


def _command_id(method: str) -> str:
    """Binding id for a command method, e.g. fit_page -> fit_page."""
    return {"fit_page": "fit_page", "fit_width": "fit_width",
            "renumber_counts": "renumber_counts"}.get(method, method)


#: What is read rather than looked at: equations, calculation text and
#: blocks, tables, spreadsheets, charts. A copy of one a little down and to
#: the right prints over the original and neither can be read (QA F-31).
READ_TYPES = frozenset({"calc", "calc_drawing", "calc_text", "calc_block", "table",
                        "sheet_run", "chart", "contents"})

#: How far a duplicate of a drawn markup lands from its original, down and
#: to the right (Revu), and the gap left beside something that is read.
COPY_NUDGE = 12.0


def copy_step(items, beside: bool = False) -> QPointF:
    """Where a copy of *items* goes, from them: Revu's step down and to the
    right for markups; for equations, tables and the like, just below them
    (or just to the right if they are at the foot of the page) so the copy
    can be read. *beside*: always just to the right (Multiply's default)."""
    box = QRectF()
    reads = False
    frame = None
    for item in items:
        try:
            rect = covered_rect(item)
        except (AttributeError, RuntimeError):
            continue
        box = rect if box.isNull() else box.united(rect)
        reads = reads or getattr(item, "TYPE", "") in READ_TYPES
        frame = frame or item.parentItem()
    if box.isNull():
        return QPointF(COPY_NUDGE, COPY_NUDGE)
    if beside:
        return QPointF(box.width() + COPY_NUDGE, 0.0)
    if not reads:
        return QPointF(COPY_NUDGE, COPY_NUDGE)
    page = frame.page_rect() if hasattr(frame, "page_rect") else None
    below = QPointF(0.0, box.height() + COPY_NUDGE)
    if page is None or box.translated(below).bottom() <= page.bottom():
        return below
    right = QPointF(box.width() + COPY_NUDGE, 0.0)
    if box.translated(right).right() <= page.right():
        return right
    return below


class ElidedLabel(QLabel):
    """A one-line label that ends in "…" when it has less room than its
    words, and never draws past its own edge. ``text()`` is still all of it
    (the tooltip shows it whole)."""

    def paintEvent(self, event) -> None:
        from PySide6.QtGui import QPainter
        painter = QPainter(self)
        room = self.contentsRect()
        words = " ".join(self.text().split())
        shown = self.fontMetrics().elidedText(words, Qt.ElideRight, room.width())
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(room, int(self.alignment()) | Qt.TextSingleLine, shown)
        painter.end()

    def setText(self, text: str) -> None:
        super().setText(text)
        self.setToolTip(text if text and len(text) > 40 else "")


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

    #: Narrowest the bar asks for, whatever it holds: what is left when every
    #: droppable control is gone is the toggles, the page navigation and the
    #: zoom box, and those are laid out in less than this.
    MINIMUM_WIDTH = 420

    def __init__(self, parent=None):
        super().__init__(parent)
        self.center_widget = None
        self._spacers = (None, None)
        self._droppable: list = []          # least important first
        self._dropped: list = []
        self._overflow = None
        self._fitting = False

    # Every control in the footer used to be fixed, so the footer alone asked
    # for 1174 px and the window could not be made narrower than about 1180 —
    # no half-screen snapping on a 1920 px monitor (QA, 2026-10-15). Revu's
    # footer drops its less important controls as it narrows and brings them
    # back when there is room; so does this one. What is dropped is still on
    # the » menu at the right, so nothing becomes unreachable.
    def set_droppable(self, widgets: list, overflow: QToolButton) -> None:
        """*widgets* may be hidden when the bar is short of room, the first
        of them first. *overflow* is shown while any of them is, and lists
        them."""
        self._droppable = list(widgets)
        self._overflow = overflow
        overflow.setVisible(False)
        self.fit_to_width()

    def dropped(self) -> list:
        """The controls hidden for want of room, in the order they went."""
        return list(self._dropped)

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        if not self._droppable:
            return hint
        return QSize(min(hint.width(), self.MINIMUM_WIDTH), hint.height())

    @staticmethod
    def _natural_width(widget: QWidget) -> int:
        """The width *widget* is laid out at when there is room for it."""
        if widget.sizePolicy().horizontalPolicy() == QSizePolicy.Ignored:
            return widget.minimumWidth()
        hint = widget.sizeHint().expandedTo(widget.minimumSize())
        return hint.boundedTo(widget.maximumSize()).width()

    def _needed_width(self, kept: list) -> int:
        """How wide the bar has to be to show everything it always shows
        plus *kept*, each at its natural width."""
        spacing = 6                         # QStatusBar's own, between items
        # its margins and the grip's gap, and the spacing either side of the
        # two centring spacers and the stretch between the bar's two halves
        needed = 2 + 2 + 1 + 3 * spacing + 4
        left, right = self._spacers
        dropping = set(self._droppable)
        for child in self.children():
            if (not isinstance(child, QWidget) or child.isWindow()
                    or child in (left, right) or child in dropping):
                continue
            if child.isHidden() and child is not self._overflow:
                continue
            if child is self._overflow and not (set(self._droppable) - set(kept)):
                continue
            needed += self._natural_width(child) + spacing
        for widget in kept:
            needed += self._natural_width(widget) + spacing
        return needed

    def fit_to_width(self) -> None:
        """Hide the least important controls the bar has no room for, and
        bring back the ones it has room for again."""
        if not self._droppable or self._fitting:
            return
        self._fitting = True
        try:
            room = self.width()
            kept = list(self._droppable)
            while kept and self._needed_width(kept) > room:
                kept.pop(0)
            dropped = [w for w in self._droppable if w not in kept]
            for widget in self._droppable:
                if widget.isHidden() == (widget in kept):
                    widget.setVisible(widget in kept)
            self._dropped = dropped
            if self._overflow is not None and self._overflow.isHidden() == bool(dropped):
                self._overflow.setVisible(bool(dropped))
            # the spacers that centre the page navigation keep the widths they
            # were given for a wider bar: with them the navigation was laid
            # out narrower than itself, its buttons over the page number
            left, right = self._spacers
            if left is not None and self._squeezed_by() > 0:
                left.setMinimumWidth(0)
                right.setMinimumWidth(0)
        finally:
            self._fitting = False

    def _squeezed_by(self) -> int:
        """How much narrower than itself the page navigation is laid out."""
        widget = self.center_widget
        if widget is None or not widget.isVisible():
            return 0
        return max(0, widget.minimumSizeHint().width() - widget.width())

    #: Called once the bar is laid out again (a hovered command's tip
    #: follows the controls it stands between).
    after_layout = None

    def resizeEvent(self, event) -> None:
        self.fit_to_width()
        super().resizeEvent(event)
        if self.after_layout is not None:
            self.after_layout()

    def event(self, event) -> bool:
        # a control grew or shrank (the page size or the zoom changed what
        # it says): see again what fits
        if event.type() == QEvent.LayoutRequest:
            self.fit_to_width()
        done = super().event(event)
        if event.type() == QEvent.LayoutRequest and self.after_layout is not None:
            self.after_layout()
        return done

    def set_center_widget(self, widget: QWidget) -> None:
        self.center_widget = widget
        left, right = _stretch(self), _stretch(self)
        self._spacers = (left, right)
        self.addWidget(left, 1)
        self.addWidget(widget)
        self.addWidget(right, 1)

    def center_on(self, global_x: float) -> None:
        """Put the centre widget's middle under *global_x* (the middle of the
        page view, not of the status bar): as close as the room between the
        texts on the left and the controls on the right allows. Still in the
        layout — one spacer is made wider than the other — so nothing is ever
        drawn over anything else."""
        left, right = self._spacers
        widget = self.center_widget
        if widget is None or left is None or not self.isVisible():
            return
        # how far the widget's middle is from where it should be, measured as
        # laid out now (spacing and margins included), moved by exactly that
        # as far as the two spacers have room
        now = widget.mapToGlobal(QPoint(widget.width() // 2, 0)).x()
        shift = int(round(global_x - now))
        # never more than the bar can spare (a narrowed bar's spacers can be
        # wider than that until it is laid out again)
        room = max(0, left.width() + right.width() - self._squeezed_by())
        before = min(max(left.width() + shift, 0), room)
        after = room - before
        # equal stretches share the room; the side that needs more than half
        # is given it as its minimum, the other takes what is left
        left.setMinimumWidth(before if before > after else 0)
        right.setMinimumWidth(after if after > before else 0)


class _SizeFollower(QObject):
    """Calls *callback* (soon, once) whenever a watched widget is resized,
    moved or shown."""

    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self._callback = callback
        self._posted = False

    def eventFilter(self, watched, event) -> bool:
        if event.type() in (QEvent.Resize, QEvent.Move, QEvent.Show) and not self._posted:
            self._posted = True
            QTimer.singleShot(0, self, self._run)
        return False

    def _run(self) -> None:
        self._posted = False
        self._callback()


class _DoubleClickToggle(QObject):
    """Calls *callback* when the watched widget is double-clicked."""

    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self._callback = callback

    def eventFilter(self, watched, event) -> bool:
        if (event.type() == QEvent.MouseButtonDblClick
                and event.button() == Qt.LeftButton):
            self._callback()
            return True
        return False


class _OnResize(QObject):
    """Calls *callback* whenever a watched widget is resized: straight away,
    and once more when the events of the moment are over, when whatever was
    being shown or laid out with it has caught up."""

    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self._callback = callback

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Resize:
            self._callback()
            QTimer.singleShot(0, self, self._callback)
        return False


class _OnRelayout(QObject):
    """Calls *callback* when a watched toolbar's contents change size (the
    Markup Styles bar rebuilds itself for each tool), so its row can wrap."""

    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self._callback = callback

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.LayoutRequest:
            self._callback()
        return False


class DetachableTabBar(QTabBar):
    """A document tab bar that reports a drag released outside itself."""

    detachRequested = Signal(int, QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._preview = None
        self.setFocusPolicy(Qt.StrongFocus)
        self.tabMoved.connect(self._track_dragged_tab)

    def _track_dragged_tab(self, before, after):
        """Keep hold of the dragged tab as the tabs are moved. A tab dragged
        past another is reported either way round — as itself moving, or as
        the other moving past it — so every move shifts the index; following
        only the first kind lost the tab and moved its neighbour instead
        (QA, 2026-10-16)."""
        dragged = getattr(self, "_dragged_tab", -1)
        if dragged < 0:
            return
        if dragged == before:
            dragged = after
        elif before < dragged <= after:
            dragged -= 1
        elif after <= dragged < before:
            dragged += 1
        self._dragged_tab = dragged

    def mousePressEvent(self, event) -> None:
        self._press_position = event.position().toPoint()
        self._dragged_tab = (self.tabAt(event.position().toPoint())
                             if event.button() == Qt.LeftButton else -1)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        index = getattr(self, "_dragged_tab", -1)
        outside = not self.rect().adjusted(-8, -8, 8, 8).contains(event.position().toPoint())
        if index >= 0 and event.buttons() & Qt.LeftButton and outside:
            if self._preview is None:
                self.setFocus(Qt.MouseFocusReason)
                self._preview = QLabel(None, Qt.ToolTip | Qt.FramelessWindowHint)
                self._preview.setAttribute(Qt.WA_TransparentForMouseEvents)
                self._preview.setAttribute(Qt.WA_ShowWithoutActivating)
                self._preview.setPixmap(self.grab(self.tabRect(index)))
                self._preview.setWindowOpacity(0.88)
            self._preview.move(event.globalPosition().toPoint() + QPoint(12, 12))
            self._preview.show()
            return
        self._clear_preview()
        super().mouseMoveEvent(event)

    def _clear_preview(self):
        if self._preview is not None:
            self._preview.close()
            self._preview.deleteLater()
            self._preview = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._dragged_tab = -1
            self._clear_preview()
            event.accept()
            return
        super().keyPressEvent(event)

    def event(self, event):
        if (event.type() == QEvent.ShortcutOverride and self._preview is not None
                and event.key() == Qt.Key_Escape):
            event.accept()
            return True
        return super().event(event)

    def mouseReleaseEvent(self, event) -> None:
        index = getattr(self, "_dragged_tab", -1)
        outside = (index >= 0
                   and (event.position().toPoint() - self._press_position).manhattanLength()
                       >= QApplication.startDragDistance()
                   and not self.rect().contains(event.position().toPoint()))
        self._dragged_tab = -1
        self._clear_preview()
        super().mouseReleaseEvent(event)
        if outside:
            self.detachRequested.emit(index, event.globalPosition().toPoint())


#: How many files Open Recent remembers.
RECENT_FILES = 10


def recent_files() -> list:
    """File ▸ Open Recent: the newest first."""
    from ..settings import app_settings
    value = app_settings().value("files/recent", []) or []
    if isinstance(value, str):
        value = [value]
    return [str(v) for v in value if v][:RECENT_FILES]


def start_folder(document=None) -> str:
    """Where a file dialog opens: beside the document, else where the last
    file was opened, else the person's Documents folder — never the folder
    CalcForge happened to be started in (exercise round 1, F-36)."""
    from PySide6.QtCore import QStandardPaths
    path = getattr(document, "path", "") if document is not None else ""
    if path and os.path.isdir(os.path.dirname(path)):
        return os.path.dirname(path)
    for recent in recent_files():
        folder = os.path.dirname(recent)
        if folder and os.path.isdir(folder):
            return folder
    documents = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
    return documents if documents and os.path.isdir(documents) else os.path.expanduser("~")


def in_start_folder(name: str, document=None) -> str:
    """*name* in the folder a dialog opens in, unless it already has one."""
    if os.path.dirname(name):
        return name
    return os.path.join(start_folder(document), name)


def remember_recent_file(path: str) -> None:
    from ..settings import app_settings
    path = os.path.abspath(path)
    kept = [p for p in recent_files() if os.path.normcase(p) != os.path.normcase(path)]
    app_settings().setValue("files/recent", ([path] + kept)[:RECENT_FILES])


def forget_recent_files(path: str = "") -> None:
    """Take *path* off the list, or clear it."""
    from ..settings import app_settings
    kept = [p for p in recent_files() if path and p != path]
    app_settings().setValue("files/recent", kept)


class ViewPane:
    """One view in the window: its document tabs over its canvas.

    A window has one of these, or two side by side in Split View (the user,
    2026-10-16: "if solo in one window then one; if split in two then two;
    each window has one menu"). The window's menus, toolbars and panels act
    on the pane last clicked: the active pane's view, tab bar and documents
    are the window's own `view`, `document_tabs` and `_open_documents`, and
    the other pane keeps its tabs' states here until it is clicked.
    """

    def __init__(self, widget, layout, view, tabs, sheet_tabs):
        self.widget = widget          # the pane: tabs over the canvas
        self.layout = layout
        self.view = view
        self.tabs = tabs
        self.sheet_tabs = sheet_tabs
        #: its tabs' states, and which is showing, while it is not active
        self.documents: list = []
        self.active = 0

    def documents_held(self) -> list:
        return [state["document"] for state in self.documents]


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
    "calc_mode": "command.calc_mode",
}

# Keys that mean one command in Markup mode and another in Calc mode (the
# user, 2026-10-15: Ctrl+M is Revu's Multiply in Markup mode and SMath's
# Matrix in Calc mode). Only the action of the mode in force carries the key
# (MainWindow._apply_mode_keys); the shortcut list does not count the pair as
# a clash because the two modes are never on together.
_SHORTCUT_SCOPES = {"array": "markup", "insert_matrix": "calc"}

_SHORTCUT_GROUPS = {
    "calculate": "SMath", "insert_matrix": "SMath", "auto_calc": "SMath",
    "new": "File", "open": "File", "save": "File", "save_as": "File",
    "insert_pdf": "File", "insert_image_page": "File", "import_toolset": "File",
    "manage_toolsets": "File",
    "insert_workbook": "File",
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
    "strikethrough": "Text", "superscript": "Text", "subscript": "Text",
    "zoom_in": "View", "zoom_out": "View", "zoom_sel": "View",
    "fit_page": "View", "fit_width": "View", "actual_size": "View",
    "prev_page": "View", "next_page": "View", "grid": "View", "snap": "View",
    "snap_items": "View", "snap_content": "View", "snap_alignment": "View",
    "snap_pdf_alignment": "View", "markups_list": "View",
    "margins": "View", "dark": "View",
    "turn_view_cw": "View", "turn_view_acw": "View",
    "turn_view_reset": "View",
    "group": "Markup", "ungroup": "Markup", "autosize": "Markup",
    "format_painter": "Markup", "hide": "Markup", "show_hidden": "Markup",
    "flatten": "Markup", "forget_defaults": "Markup",
    "add_page": "Pages", "crop_page": "Pages", "extract_pages": "Pages",
    "split_pages": "Pages", "duplicate_page": "Pages", "delete_page": "Pages",
    "page_setup": "Pages", "scale": "Pages", "viewports": "Pages", "header_footer": "Pages",
    "bookmark": "Pages", "contents": "Pages", "doc_props": "Pages",
    "rotate_pages_cw": "Pages", "rotate_pages_acw": "Pages",
    "insert_page_break": "Spreadsheet", "remove_page_break": "Spreadsheet",
    "reset_page_breaks": "Spreadsheet", "set_print_area": "Spreadsheet",
    "clear_print_area": "Spreadsheet", "sheet_page_setup": "Spreadsheet",
    "replace_text": "Edit", "show_panels": "Window",
    "panel_pages": "Window", "panel_bookmarks": "Window", "panel_toolsets": "Window",
    "panel_properties": "Window", "panel_search": "Window", "panel_page": "Window",
    "panel_maths": "Window", "panel_variables": "Window",
    "renumber_counts": "Markup", "check_spelling": "Markup",
    "shortcuts": "Help", "sample": "Help",
    "find_tool": "Help", "find_text": "Edit",
    "about": "Help",
}




def snug_number_box(spin) -> None:
    """Size a spin box to its widest value, suffix and arrows."""
    metrics = spin.fontMetrics()
    widest = max((spin.prefix() + spin.textFromValue(value) + spin.suffix() for value in
                  (spin.minimum(), spin.maximum())), key=metrics.horizontalAdvance)
    # the text, the theme's padding round it, and the arrows (18 px)
    spin.setFixedWidth(int(metrics.horizontalAdvance(widest)) + 18 + 22)


#: On a Mac the menus go in the Mac's own bar at the top of the screen, as
#: every Mac application's do; on Windows (and Linux) the window has its own,
#: with the Markup | Calc switch and the search box after Help. The Mac's bar
#: has no room for those two (the user, 2026-10-08: "I don't like the separate
#: menu bar, put it back so it works in Windows only").
NATIVE_MENU_BAR = sys.platform == "darwin"

def _bar_ink() -> str:
    """The ink the theme draws its icons in."""
    from .icons import _THEME_INK, icon_theme
    return _THEME_INK.get(icon_theme(), "#2c3340")

def _a_field_being_typed_in(widget) -> bool:
    """A box that takes typing: a line edit, a spin box's or an editable
    list's line, or a text editor — not read-only."""
    from PySide6.QtWidgets import QAbstractSpinBox, QPlainTextEdit, QTextEdit
    if isinstance(widget, QLineEdit):
        return not widget.isReadOnly()
    if isinstance(widget, (QTextEdit, QPlainTextEdit)):
        return not widget.isReadOnly()
    return isinstance(widget, QAbstractSpinBox)


#: The events MainWindow's application-wide filter acts on (eventFilter).
_FILTERED_INPUT = frozenset((QEvent.ShortcutOverride, QEvent.KeyPress,
                             QEvent.MouseButtonPress))


def _moves_documents(method):
    """Nothing is let go of while *method* carries a document from one pane
    or window to another (it is shown by neither on the way); whatever it
    left behind is let go of once it has (ui/release.py)."""
    import functools

    @functools.wraps(method)
    def run(self, *args, **kwargs):
        from . import release
        with release.holding():
            result = method(self, *args, **kwargs)
        self._let_go()
        return result
    return run


class MainWindow(QMainWindow):
    """Everything the user sees: canvas, toolbars, panels and menus."""

    def __init__(self):
        super().__init__()
        type(self)._windows.append(self)
        self.destroyed.connect(
            lambda *_: type(self)._windows.remove(self)
            if self in type(self)._windows else None)
        self._syncing_view = False
        from ..items import hatches
        hatches.load_custom()          # the hatch patterns of one's own, from before
        from ..items import linestyles
        linestyles.load_custom()       # and the line styles
        self._undo_clean_slot = lambda _clean: self.update_title()
        self._connected_undo_stacks = []
        keep_the_wheel_with_the_scroller(QApplication.instance())
        from . import release as _release
        _release.keep_dialogs_with_their_parents()     # (once; see there)
        self.document = Document()
        self.undo_stack = QUndoStack(self)
        self.undo_stack.setUndoLimit(200)
        from . import release
        release.STACKS.add(self.undo_stack)
        #: closed for good: nothing it showed is kept for it (see _let_go)
        self._closed_for_good = False
        self.current_index = 0
        self.default_style = Style()
        self.shortcuts = ShortcutManager(self)
        # Every menu entry and panel button a person can click is a named
        # command that any key can be given (the user, 2026-10-16)
        from .bindable import CommandRouter
        self.commands = CommandRouter(self)
        # Which binding each action carries, so a rebinding can find it again.
        self.action_ids: dict[str, str] = {}
        self.second_key_ids: dict[str, str] = {}
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
        self._active_tab = -1
        self.toolbars: list = []
        # toolbars a row break was put before because their row had no room
        # for them (_wrap_toolbar_rows): not the user's, never saved
        self._auto_breaks: set = set()
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
        self.mark_menu_buttons()
        from . import nativeframe
        nativeframe.install(self)                 # Windows: the menus in its own title bar
        self._connect()
        self._file_commands_by_menu()
        self.apply_shortcuts()
        from . import preferences as _prefs
        self.view.use_the_graphics_card(_prefs.current().gpu_drawing)

        self._autosave = QTimer(self)
        self._autosave.setInterval(120_000)
        self._autosave.timeout.connect(self.write_autosave)
        self._autosave.start()

        self.new_document(confirm=False)
        self._open_documents = [self._current_document_state()]
        self._active_tab = 0
        self.document_tabs.blockSignals(True)
        self.document_tabs.addTab(self._tab_title(self.document))
        self.document_tabs.blockSignals(False)
        from ..app import current_theme
        from ..theme import DARK
        self.act_dark.setChecked(current_theme() == DARK)
        from ..settings import app_settings as _settings
        for key in ("rulers", "crosshair"):          # as they were left
            if str(_settings().value(f"view/{key}", "false")).lower() == "true":
                getattr(self, f"act_{key}").setChecked(True)
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
            dock.dockLocationChanged.connect(
                lambda _area, panel=dock.objectName(): self._panel_landed_soon(panel))
            # opened beside another (from outside the rail): tabs, not a stack
            dock.visibilityChanged.connect(
                lambda visible, panel=dock.objectName():
                self._panel_landed_soon(panel) if visible else None)
            dock.topLevelChanged.connect(
                lambda floating, panel=dock.objectName():
                None if floating else self._panel_landed_soon(panel))
            dock.topLevelChanged.connect(
                lambda floating, panel=dock: self._panel_floated(panel, floating))
            name = dock.objectName()
            dock.visibilityChanged.connect(
                lambda visible, panel=name:
                self._panel_visibility_changed(panel, visible))
            dock.pinnedChanged.connect(lambda *_: self.note_layout_change())
            dock.collapsedChanged.connect(lambda *_: self.note_layout_change())
        for toolbar in self.toolbars:
            toolbar.topLevelChanged.connect(lambda *_: self.note_layout_change())
            toolbar.visibilityChanged.connect(lambda *_: self.note_layout_change())
            toolbar.visibilityChanged.connect(lambda *_: self._wrap_toolbar_rows_soon())
            toolbar.movableChanged.connect(lambda *_: self.note_layout_change())
        self._enforce_panel_limit()
        self._initial_fit = QTimer(self)
        self._initial_fit.setSingleShot(True)
        self._initial_fit.timeout.connect(self.view.fit_page)
        self._initial_fit.start(0)

    # ==================================================================
    # construction
    # ==================================================================
    def _build_central(self) -> None:
        central = QWidget()
        # each side of the canvas, the edge a hidden panel column leaves,
        # to double-click or drag it back by (docks.PanelEdge)
        from .docks import PanelEdge
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.panel_edges = {LEFT: PanelEdge(LEFT), RIGHT: PanelEdge(RIGHT)}
        inner = QWidget()
        inner.setObjectName("canvasColumn")
        row.addWidget(self.panel_edges[LEFT])
        row.addWidget(inner, 1)
        row.addWidget(self.panel_edges[RIGHT])
        for side, edge in self.panel_edges.items():
            edge.hide()
            edge.doubleClicked.connect(lambda s=side: self.toggle_panel_column(s))
            edge.draggedOut.connect(lambda width, s=side: self.open_panel_column(s, width))
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)


        # One document per tab, one view for all of them. Each tab keeps its
        # own document, canvas, undo history and page, and switching hands the
        # view a different canvas — so nothing has to be re-wired, and nothing
        # of one document can reach into another.
        self.document_tabs = self._make_document_tabs()

        # The markups list sits under the canvas, as Bluebeam's does: a bar
        # that is dragged up to open the list and down to close it again.
        self.bottom_split = QSplitter(Qt.Vertical)
        self.bottom_split.setObjectName("markupsSplit")
        self.bottom_split.setChildrenCollapsible(True)
        self.bottom_split.setHandleWidth(7)
        # Split View puts a second pane beside this one, in the same window
        # (ViewPane): one set of menus, toolbars and panels for both
        self.view_split = QSplitter(Qt.Horizontal)
        self.view_split.setObjectName("viewSplit")
        self.view_split.setChildrenCollapsible(False)
        # the canvas with Excel's sheet tabs along its foot (ui/sheettabs.py)
        from .sheettabs import SheetTabs
        self.sheet_tabs = SheetTabs(self)
        # Excel's place for them: left of the horizontal scroll bar, one row
        self.view.addScrollBarWidget(self.sheet_tabs, Qt.AlignLeft)
        pane = self._make_pane(self.view, self.document_tabs, self.sheet_tabs)
        self._panes = [pane]
        self._active_pane = pane
        self.bottom_split.addWidget(self.view_split)
        self.bottom_split.setCollapsible(0, False)
        self.bottom_split.splitterMoved.connect(self._markups_list_moved)
        # Excel's formula bar, over the canvas while a table is open; it goes
        # with the pane being worked in
        from .tableedit import FormulaBar
        self.formula_bar = FormulaBar(self.view.tables)
        self.view.tables.bar = self.formula_bar
        pane.layout.insertWidget(pane.layout.indexOf(pane.tabs) + 1, self.formula_bar)
        layout.addWidget(self.bottom_split, 1)
        # Revu's empty workspace, once the last document is closed (novice
        # 24): no page and no "Untitled", only the way to a document
        self.empty_workspace = self._build_empty_workspace()
        layout.addWidget(self.empty_workspace, 1)
        self.empty_workspace.hide()
        self._workspace_empty = False
        self._enabled_before_empty: dict = {}
        self.setCentralWidget(central)

        # The rails go in the toolbar areas, which is what puts them hard
        # against the window's own edges — outside the panels, the way
        # Bluebeam's are.
        self.left_rail = PanelRail(LEFT, self)
        self.right_rail = PanelRail(RIGHT, self)
        self.left_rail_bar = RailBar(self.left_rail, self)
        self.right_rail_bar = RailBar(self.right_rail, self)
        self.addToolBar(Qt.LeftToolBarArea, self.left_rail_bar)
        self.addToolBar(Qt.RightToolBarArea, self.right_rail_bar)

    def _make_document_tabs(self) -> "DetachableTabBar":
        tabs = DetachableTabBar()
        tabs.setDocumentMode(True)
        tabs.setExpanding(False)
        tabs.setTabsClosable(True)
        tabs.setMovable(True)
        tabs.setDrawBase(False)
        tabs.setVisible(True)

        def mine(slot):
            # a split window has a tab bar per view: each speaks only while
            # its view is the one in hand (a press on it makes it so first)
            return lambda *args: slot(*args) if self.document_tabs is tabs else None

        tabs.currentChanged.connect(mine(self.switch_to_document))
        tabs.tabCloseRequested.connect(mine(self.close_document_tab))
        tabs.tabMoved.connect(mine(self._tab_moved))
        tabs.setContextMenuPolicy(Qt.CustomContextMenu)
        tabs.customContextMenuRequested.connect(mine(self._tab_context_menu))
        tabs.detachRequested.connect(mine(self.tear_off_document))
        return tabs

    def _make_pane(self, view, tabs, sheet_tabs) -> ViewPane:
        """A pane of the window: its document tabs over its canvas."""
        widget = QWidget()
        widget.setObjectName("viewPane")
        column = QVBoxLayout(widget)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        # Split View: a line over the view in hand, so which one the
        # menus and panels act on is never a guess
        marker = QWidget()
        marker.setObjectName("activeViewMarker")
        marker.setFixedHeight(2)
        marker.setAutoFillBackground(True)
        marker.hide()
        column.addWidget(marker)
        column.addWidget(tabs)
        column.addWidget(view, 1)
        self.view_split.addWidget(widget)
        pane = ViewPane(widget, column, view, tabs, sheet_tabs)
        pane.marker = marker
        return pane

    def _mark_active_pane(self) -> None:
        from PySide6.QtGui import QPalette
        from ..app import current_theme
        from ..theme import tokens
        accent = QColor(tokens(current_theme())["accent"])
        for pane in self._panes:
            pane.marker.setVisible(self.is_split)
            palette = pane.marker.palette()
            palette.setColor(QPalette.Window,
                             accent if pane is self._active_pane else QColor(0, 0, 0, 0))
            pane.marker.setPalette(palette)

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

    # The three that belong to the words while words are being written. Bold,
    # italic and underline mean what they mean in every program there has ever
    # been, so inside a markup being typed into they format the text and no
    # command fires — whatever a command may be bound to them outside it.
    #
    # They are in the shortcut list like everything else: a key the
    # application answers to that cannot be seen or changed is a key nobody
    # knows about, which is how Ctrl+I came to insert a PDF.
    RESERVED_FOR_TEXT = ("Ctrl+B", "Ctrl+I", "Ctrl+U")
    EDITOR_COMMANDS = {
        "command.text_left", "command.text_center", "command.text_right",
        "command.font_increase", "command.font_decrease"}

    def _act(self, key: str, text: str, slot, shortcut: str = "", icon_name: str = "",
             checkable: bool = False, tip: str = "", name: str = "") -> QAction:
        """A window command. *name* is what the shortcut list calls it when
        the menu's own wording is short for it (Insert ▸ "Pages" is Insert
        Pages there); by default the menu's text."""
        action = QAction(text, self)
        if icon_name:
            self.give_icon(action, icon_name)
        # Every command goes in the shortcut list, with a key or without one,
        # so it can be seen in one place and given any key (the user,
        # 2026-10-16). What is registered is the default; a binding already
        # changed keeps the change.
        already = _ALREADY_BOUND.get(key)
        if already:
            # This command is already in the list under its own name; a
            # second entry for the same key would read as a clash with
            # itself.
            shortcut = self.shortcuts.sequence(already) or shortcut
            self.action_ids[key] = already
        else:
            shortcut = self.shortcuts.register(
                f"command.{key}", (name or text).rstrip("…"), shortcut,
                _SHORTCUT_GROUPS.get(key, ""),
                scope=_SHORTCUT_SCOPES.get(key, "always"))
            self.action_ids[key] = f"command.{key}"
        action.setProperty(bindable.COMMAND, self.action_ids[key])
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
        self._act("new", "New PDF", lambda: self.new_document(), "Ctrl+N", "new")
        self._act("new_tab", "New Tab", lambda: self.open_in_new_tab(), "Ctrl+T",
                  tip="Open another document beside this one, in its own tab")
        # Ctrl+Shift+N is Revu's Insert Blank Page (audit L2); New Window
        # moved up a modifier rather than losing its key.
        self._act("new_window", "New Window", self.open_new_window, "Ctrl+Alt+Shift+N",
                  tip="Open a second window with a document of its own")
        self._act("markups_list", "Markups List", self.show_markups_list, "Alt+L",
                  checkable=True,
                  tip="Open or close the markups list under the drawing — or "
                      "drag its bar up and down")
        # Revu's keys for Crop Pages and Extract Pages (audit B1)
        self._act("crop_page", "Crop Pages…", lambda: self.crop_pages(), "Alt+Shift+O",
                  tip="Cut margins off the chosen pages, or drag the part to keep "
                      "(Get Window); Undo restores the rest")
        self._act("extract_pages", "Extract Pages…", lambda: self.extract_pages(),
                  "Ctrl+Shift+X",
                  tip="Save chosen pages, with their markups, as a new PDF")
        self._act("split_pages", "Split Document…", lambda: self.split_into_files(),
                  tip="Save the document as several PDFs of so many pages each")
        # Revu's four page layouts (View menu), one of them always on
        self.page_layout_group = QActionGroup(self)
        self.page_layout_group.setExclusive(True)
        for key, text, tip in (
                ("single", "Single Page Mode", "One page at a time, fitted to the window; the wheel "
                 "scrolls it and turns to the next page at its end"),
                ("continuous", "Continuous Mode", "Every page in one column"),
                ("side", "Side-by-Side Mode", "Two pages at a time: odd on the left, even on the right"),
                ("continuous_side", "Continuous Side-by-Side Mode",
                 "Every page, two to a row, in one column")):
            action = self._act(f"layout_{key}", text,
                               lambda _checked=False, mode=key: self.set_page_layout(mode),
                               tip=tip)
            action.setCheckable(True)
            action.setChecked(key == "continuous")
            self.page_layout_group.addAction(action)
        self._act("rulers", "Rulers", self.show_rulers, checkable=True,
                  tip="Rulers along the top and left of the drawing, from the page's "
                      "corner; right-click one for its units")
        self._act("crosshair", "Full-Screen Crosshair", self.show_crosshair, checkable=True,
                  tip="Lines across the whole drawing that meet at the pointer")
        self._act("dim_content", "Dim Content", self.set_dimmer, "Ctrl+F5", checkable=True,
                  tip="Tone down the page's own content so the markups stand out "
                      "(on screen only)")
        # the dimmer is every open drawing's: a window opened while it is on
        # shows its tick, not a dimmed page under a cleared one
        from .scene import DIMMER
        self.act_dim_content.blockSignals(True)
        self.act_dim_content.setChecked(bool(DIMMER["on"]))
        self.act_dim_content.blockSignals(False)
        self.dimmer_levels = QActionGroup(self)
        self.dimmer_levels.setExclusive(True)
        for percent in range(0, 101, 10):
            level = self.dimmer_levels.addAction(f"{percent}%")
            level.setCheckable(True)
            level.setData(percent)
            level.setChecked(percent == 40)
            level.triggered.connect(lambda _c=False, p=percent: self.set_dimmer_level(p))
        self._act("full_screen", "Full Screen", self.set_full_screen, "F11", checkable=True,
                  tip="The window over the whole screen, without the system's frame")
        self._act("presentation", "Presentation", self.set_presentation, "Ctrl+Return",
                  checkable=True,
                  tip="Only the page, one at a time over the whole screen: arrows, Space "
                      "and Page Up/Down turn the pages, Esc ends it")
        self._act("cover_page", "Show Cover Page in Side-by-Side", self.set_cover_page,
                  checkable=True,
                  tip="In the side-by-side layouts the first page stands alone, as a cover")
        self._act("split_view", "Split View", self.toggle_split_view,
                  checkable=True,
                  tip="View this document beside another editable pane; "
                      "choose again to turn the split off")
        self._act("separate_views", "Separate Views", self.separate_views,
                  tip="Return split panes to independent windows")
        self._act("open", "Open…", self.open_document, "Ctrl+O", "open")
        self._act("close_tab", "Close", lambda: self.close_document_tab(self._active_tab),
                  "Ctrl+W", tip="Close the document in view")
        self._act("close_all", "Close All", self.close_all_documents,
                  tip="Close every document in this window, asking about unsaved changes")
        self._act("save_all", "Save All", self.save_all_documents,
                  tip="Save every open document that has unsaved changes")
        self._act("save", "Save", self.save_document, "Ctrl+S", "save")
        self._act("save_as", "Save As…", self.save_document_as, "Ctrl+Shift+S")
        # Not Ctrl+I. That belongs to italic wherever there are words, and
        # while somebody was typing it inserted a PDF instead — which is the
        # exact thing the requirement says must never happen. It never reached
        # the shortcut list either, because keys reserved for the text are not
        # registered, so it was a binding nobody could see or change.
        #
        # The ways of putting pages in are one family, offered the same way
        # wherever they are (bug hunt E1–E4): under Insert ▸ (and File ▸
        # Import ▸) each is a submenu of Before / After the page in view,
        # as on the page menu; the key, or a click on the toolbar button,
        # puts it after the page in view (_build_insert_family).
        self._act("insert_pdf", "Pages", lambda: self.insert_pdf(),
                  "Ctrl+Shift+I", "pdf", name="Insert Pages",
                  tip="Insert Pages: pages from a PDF, before or after this page")
        self._act("insert_workbook", "Excel Workbook", lambda: self.insert_workbook(),
                  name="Insert Excel Workbook",
                  tip="Insert Excel Workbook: its worksheets as spreadsheet pages "
                      "(cells, formulas, formats, names and page layout)")
        self._act("import_toolset", "Tool Set…",
                  lambda: self.import_toolset(), name="Import Tool Set",
                  tip="Import Tool Set: bring in a Bluebeam tool set — a .btx file")
        self._act("manage_toolsets", "Manage Tool Sets…", lambda: self.manage_toolsets(),
                  tip="Show, hide, order, rename and remove tool sets")
        self._act("insert_image_page", "Image Page",
                  lambda: self.insert_image_page(), "", "image", name="Insert Image Page",
                  tip="Insert Image Page: a picture as a page of its own")
        self._act("export_pdf", "PDF…", self.export_pdf, "Ctrl+E", "pdf", name="Export PDF",
                  tip="Export PDF: a plain PDF of the document, markups drawn in")
        self._act("export_png", "Images…", self.export_images, name="Export Images",
                  tip="Export Images: every printable page as an image")
        self._act("export_markups", "Markups Summary…", self.export_markups,
                  tip="Export the document's markup list")
        self._act("print", "Print…", self.print_document, "Ctrl+P", "print",
                  tip="Print: Revu's Print dialog, with a preview of each page")
        self._act("preview", "Print Preview…", self.print_preview,
                  tip="Print Preview: the Print dialog, whose preview shows each "
                      "page as it will print")
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
        self.act_undo.setProperty(bindable.COMMAND, "command.undo")
        self.act_redo = QAction("Redo", self)
        self.act_redo.triggered.connect(self.redo_something)
        self.undo_stack.canRedoChanged.connect(self._refresh_undo_actions)
        self.act_redo.setShortcut(QKeySequence(self.shortcuts.register(
            "command.redo", "Redo", "Ctrl+Shift+Z", "Edit")))
        self.give_icon(self.act_redo, "redo")
        self.action_ids["redo"] = "command.redo"
        self.act_redo.setProperty(bindable.COMMAND, "command.redo")

        self._act("cut", "Cut", self.cut_selection, "Ctrl+X")
        self._act("copy", "Copy", self.copy_selection, "Ctrl+C")
        self._act("paste", "Paste", self.paste_items, "Ctrl+V")
        self._act("paste_in_place", "Paste in Place", self.paste_in_place,
                  "Ctrl+Shift+V",
                  tip="Put it back at the same place on this page, as Bluebeam does")
        self._act("paste_here", "Paste Here…", self.paste_with_preview,
                  "Ctrl+Alt+V",
                  tip="Carry what was copied on the pointer and click to drop it")
        # Ctrl+D is Revu's Document Properties (audit L2): Duplicate takes
        # Ctrl+J, the key it has in drawing programs.
        self._act("duplicate", "Duplicate", self.duplicate_selection, "Ctrl+J",
                  tip="A copy of the selection, a little down and to the right")
        self._act("delete", "Delete", self.delete_selection, "", "delete")
        self._act("select_all", "Select All", self.select_all, "Ctrl+A")
        # SMath (decisions 5, 6 and 18): the mode switch and the calculation
        # commands the document has whatever is going on. SMath's keys inside
        # an equation are in the shortcut manager's SMath section.
        self._act("calc_mode", "Calc Mode", self.toggle_calc_mode, "F12", checkable=True,
                  tip="Calc mode: typing on the page starts an equation, as in SMath. "
                      "Markup mode: the markup tools' keys")
        self._act("calculate", "Calculate", self.calculate, "F9",
                  tip="Recalculate every equation in the document")
        self._act("auto_calc", "Auto-Calc", self.set_auto_calc, checkable=True,
                  tip="Recalculate what depends on an equation as soon as it is left")
        self.act_auto_calc.setChecked(True)
        self._act("insert_matrix", "Matrix", self.insert_matrix, "Ctrl+M",
                  tip="Insert a matrix into the equation, or start one "
                      "(Ctrl+M in Calc mode; in Markup mode Ctrl+M is Multiply)")
        self._act("insert_plot", "Plot", self.insert_plot,
                  tip="A 2-D plot at the red cross or the pointer (@ in Calc mode)")
        self._act("insert_block", "Calculation Block", self.insert_block,
                  tip="A calculation block round the selected equations, or at the red "
                      "cross: its equations move, copy and delete with it, and it can "
                      "keep what they define to itself (Self-contained)")
        self._act("insert_table", TOOL_MAP["table"].label, self.insert_table,
                  tip=TOOL_MAP["table"].hint)
        self._act("insert_chart", "Chart", lambda: self.insert_chart(),
                  tip="A chart of the cells picked out in a table: XY scatter, line or "
                      "column, with log axes, error bars and trendlines (double-click it "
                      "to change it)")
        self._act("calc_rules", "Conditional Formatting…", self.conditional_formatting_rules,
                  tip="Presets of rules that colour and size equations by their result "
                      "(DCR > 1 red…), and which variable names use them")
        self._act("insert_calc_text", "Calc Text", self.insert_calc_text,
                  tip="Calculation text: words among the equations, on their grid "
                      "(\" in Calc mode)")
        # WebSMath's Calculation menu, on the selected part of an equation (or
        # the operand at the cursor)
        from . import calcedit as _calcedit
        for key, label, command, tip in (
                ("solve", "Solve", _calcedit.solve_selection,
                 "Solve for the variable under the cursor; the roots go below"),
                ("calculate_selection", "Calculate selection", _calcedit.calculate_selection,
                 "Replace the selected part of the equation by its value"),
                ("invert", "Invert", _calcedit.invert_selection,
                 "The selected part to the power −1"),
                ("determinant", "Determinant", _calcedit.determinant_selection,
                 "det() round the selected part")):
            self._act(key, label, lambda _checked=False, run=command: run(self.view.calc),
                      tip=tip)
        self._act("insert_operator", "Operator…", self.insert_operator,
                  tip="Every operator, by group; the chosen one goes into the equation")
        for name, label, tip in (
                ("if", "If", "if … else: a condition, in a program block"),
                ("for", "For", "for: a loop over a range, in a program block"),
                ("while", "While", "while: a loop while a condition holds"),
                ("line", "Line", "Add a line to a program block (] in an equation)")):
            self._act(f"prog_{name}", label,
                      lambda _checked=False, which=name: self.insert_program(which),
                      tip=tip)
        # Keys inside an equation only (the SMath section of the shortcut
        # manager): on the menu without a window shortcut, since outside an
        # equation Ctrl+E is Export PDF and Ctrl+Shift+D is Delete Pages.
        self._act("insert_function", "Function…", self.insert_function,
                  tip="Insert a function into the equation (Ctrl+E in an equation)")
        self._act("constants", "Constants…", self.show_constants,
                  tip="SMath's constants; double-click one to insert it (Ctrl+K in an equation)")
        self._act("double_check", "Double-Check", self.double_check,
                  tip="Recalculate every result independently and compare "
                      "(Ctrl+Shift+D in an equation)")
        self._act("lock", "Lock", self.toggle_lock, "Ctrl+L",
                  tip="Lock the selection so it cannot be moved, or let it go")
        self._act("offset", "Offset", self.start_offset, "O",
                  tip="A copy of the selected markup a set distance away, on the side "
                      "the pointer is — Revu's Offset")
        # Revu's Ctrl+M in Markup mode; Ctrl+Shift+D is Revu's Delete Pages
        # (the user, 2026-10-15)
        self._act("array", "Multiply…", self.array_selection, "Ctrl+M",
                  tip="Repeat the selection at a fixed spacing, any number of times "
                      "(Ctrl+M in Markup mode; in Calc mode Ctrl+M is Matrix)")
        self._act("front", "Bring to Front", lambda: self.reorder("front"), "Ctrl+Shift+]",
                  tip="Bring the selection to the front")
        self._act("back", "Send to Back", lambda: self.reorder("back"), "Ctrl+Shift+[", tip="Send the selection behind every other markup")
        self._act("forward", "Bring Forward", lambda: self.reorder("forward"), "Ctrl+]")
        self._act("backward", "Send Backward", lambda: self.reorder("backward"), "Ctrl+[")
        for key, label in (("left", "Align Left"), ("hcenter", "Align Centre"),
                           ("right", "Align Right"), ("top", "Align Top"),
                           ("vcenter", "Align Middle"), ("bottom", "Align Bottom")):
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
        # Revu's other Font Styles (its Font toolbar and Properties panel)
        self._act("strikethrough", "Strikethrough", self.toggle_strikethrough, "",
                  tip="Strike through the words picked out, or the whole markup")
        self._act("superscript", "Superscript", self.toggle_superscript, "",
                  tip="Set the words picked out, or the whole markup, above the line")
        self._act("subscript", "Subscript", self.toggle_subscript, "",
                  tip="Set the words picked out, or the whole markup, below the line")
        self._act("text_left", "Align Left",
                  lambda: self.format_content(alignment="left"), "Ctrl+Alt+Left")
        self._act("text_center", "Align Centre",
                  lambda: self.format_content(alignment="center"), "Ctrl+Alt+Home")
        self._act("text_right", "Align Right",
                  lambda: self.format_content(alignment="right"), "Ctrl+Alt+Right")
        self._act("font_increase", "Increase Font Size",
                  lambda: self.format_content(font_delta=1.0), "Ctrl+Alt+Up")
        self._act("font_decrease", "Decrease Font Size",
                  lambda: self.format_content(font_delta=-1.0), "Ctrl+Alt+Down")

        # lambdas: the view in hand when pressed (Split View has two)
        self._act("zoom_in", "Zoom In", lambda: self.view.zoom_in(), "Ctrl++", "zoom_in")
        self._act("zoom_out", "Zoom Out", lambda: self.view.zoom_out(), "Ctrl+-", "zoom_out")
        # Revu's zoom keys (audit L2): Fit Page Ctrl+9, Fit Width Ctrl+0,
        # Actual Size Ctrl+8
        self._act("fit_page", "Fit Page", lambda: self.view.fit_page(), "Ctrl+9", "fit")
        self._act("fit_width", "Fit Width", lambda: self.view.fit_width(), "Ctrl+0")
        self._act("zoom_sel", "Zoom to Selection", lambda: self.view.zoom_to_selection(), "Ctrl+2",
                  tip="Zoom to the selected markups")
        # Turning the view is a way of looking at the page, not a change to
        # it: for reading a drawing that came in sideways. Rotating the page
        # itself is on the page menu, and does change the document.
        self._act("turn_view_cw", "Rotate Clockwise",
                  lambda: self.view.rotate_view(True), "Ctrl+Shift+.",
                  tip="Turn the page on screen, for reading a drawing "
                      "sideways — the page itself is not changed")
        self._act("turn_view_acw", "Rotate Anticlockwise",
                  lambda: self.view.rotate_view(False), "Ctrl+Shift+,",
                  tip="Turn the page on screen the other way — the page "
                      "itself is not changed")
        self._act("turn_view_reset", "Reset Rotation",
                  lambda: self.view.reset_view_rotation(),
                  tip="Put the view back the way up the page is")
        # Bare Page Up/Down scroll a screenful, as they do in any reader; with
        # Ctrl they jump a whole page.
        self._act("prev_page", "Previous Page", lambda: self.go_to_page(self.current_index - 1),
                  "Ctrl+PgUp")
        self._act("next_page", "Next Page", lambda: self.go_to_page(self.current_index + 1),
                  "Ctrl+PgDown")
        self._act("actual_size", "Actual Size", lambda: self.view.set_zoom(1.0), "Ctrl+8")
        self._act("pin_panels", "Pin Panels", self.pin_all_panels, "", checkable=True,
                  tip="Keep the panels where they are, so a stray drag cannot move them")
        # Revu's Hide Panels (Shift+F4): every panel away, and back again
        self._act("show_panels", "Hide/Show Panels", self.hide_or_show_panels, "Shift+F4",
                  tip="Hide every panel for more room for the drawing; again brings "
                      "them back (the default ones when none were open)")
        self._act("reset_layout", "Reset Layout", self.reset_layout,
                  tip="Put the panels and toolbars back where they started")
        self._act("lock_toolbars", "Lock Toolbars", self.lock_toolbars, "",
                  checkable=True, tip="Stop the toolbars being dragged about")
        self._act("customise_toolbar", "Customise Toolbars…",
                  self.customise_toolbar,
                  tip="Pick which tools appear on the markup toolbar")

        # Ctrl+Shift+N is Revu's Insert Blank Page (audit L2)
        self._act("add_page", "Blank Page", lambda: self.add_page(), "Ctrl+Shift+N",
                  name="Insert Blank Page",
                  tip="Insert Blank Page: the size, how many, and where they go")
        self._act("add_sheet_page", "Spreadsheet Page", lambda: self.insert_sheet_page(),
                  name="Insert Spreadsheet Page",
                  tip="Insert Spreadsheet Page: a page of spreadsheet cells; on a "
                      "spreadsheet it is one more page of that sheet")
        self._act("sheet_page_setup", "Sheet Layout…", lambda: self.sheet_page_setup(),
                  tip="Print area, titles, fit to page width, centring, gridlines and headings")
        self._act("duplicate_page", "Duplicate Page", lambda: self.duplicate_page())
        # Revu's Ctrl+Shift+D (audit L2)
        self._act("delete_page", "Delete Pages…", lambda: self.delete_page(), "Ctrl+Shift+D",
                  tip="Delete Pages: choose which pages to take out")
        # Revu's Rotate Pages, on the Document menu as well as the page menu
        # (bug hunt E7): the same two choices in both
        self._act("rotate_pages_cw", "Clockwise", lambda: self.rotate_page(None, True),
                  name="Rotate Pages Clockwise",
                  tip="Turn the page in view and everything drawn on it a quarter "
                      "turn clockwise. To turn only the way it is shown, use View ▸ "
                      "Rotate View.")
        self._act("rotate_pages_acw", "Anticlockwise", lambda: self.rotate_page(None, False),
                  name="Rotate Pages Anticlockwise",
                  tip="Turn the page in view and everything drawn on it a quarter "
                      "turn anticlockwise")
        # No key: Ctrl+Shift+P shows the problems panel, and page setup is on
        # the Page menu and on a page's own right-click menu.
        self._act("page_setup", "Page Setup…", self.page_setup, "", "page")
        # Revu's name, the same everywhere (bug hunt E11, novice 13)
        self._act("scale", "Set Scale…", self.calibrate_dialog,
                  "Ctrl+Shift+K", "calibrate",
                  tip="Set Scale: what a length on this page measures")
        self._act("viewports", "Viewports…", self.viewports_dialog, "", "viewport",
                  tip="The regions of this page drawn at their own scale")
        self._act("doc_props", "Document Properties…", lambda: self.document_properties(),
                  "Ctrl+D")
        self._act("header_footer", "Headers && Footers…", self.edit_header_footer, "",
                  tip="Page numbers, the date, a title and a logo on every page")

        # Ctrl+G is Group, here as in Bluebeam, so the grid takes the key
        # next to it rather than fighting for one. Ctrl+Alt+G is Greek gamma.
        self._act("grid", "Show Grid", self.toggle_grid, "Ctrl+'", checkable=True)
        self._act("snap", "Snap to Grid", self.toggle_snap, "", checkable=True,
                  tip="Snap points to the page grid")
        self._act("snap_items", "Snap to Markup", self.toggle_item_snap, "",
                  checkable=True,
                  tip="Catch corners, centres, side middles and line ends of "
                      "the markups already on the page")
        self._act("snap_content", "Snap to Content", self.toggle_content_snap,
                  "", checkable=True,
                  tip="Catch the corners and ends of the line work that came "
                      "in on the page — and only those, because a drawing has "
                      "thousands of them")
        self._act("snap_alignment", "Align to Markups",
                  self.toggle_alignment_snap, "", checkable=True,
                  tip="Line a new markup up level with, or directly under, a "
                      "point on a markup already drawn")
        self._act("snap_pdf_alignment", "Align to Content",
                  self.toggle_pdf_alignment_snap, "", checkable=True,
                  tip="Line a new markup up level with, or directly under, a "
                      "corner or line end in the PDF drawing itself")
        # Revu's key for Dark Mode (QA, 2026-10-15). Inside an equation
        # Ctrl+3 is still SMath's ≠: there SMath's keys win, as with Ctrl+0.
        self._act("dark", "Dark Mode", self.toggle_theme, "Ctrl+3", checkable=True)
        self._act("margins", "Show Margins", self.toggle_margins, "", checkable=True)
        self.act_margins.setChecked(True)
        self._act("name_tags", "Name Tags", self.toggle_name_tags, "", checkable=True,
                  tip="A small printed tag with the name on each named cell, "
                      "table and sheet")
        self.act_name_tags.setChecked(True)
        self.act_snap_items.setChecked(True)
        self.act_snap_content.setChecked(True)
        self.act_snap_alignment.setChecked(True)
        self._act("sticky", "Reuse", self.toggle_sticky, "", "pin",
                  checkable=True,
                  tip="Stay on the current tool after drawing instead of returning to Select")
        self._act("check_spelling", "Check Spelling in Markups…", self.check_spelling, "F7",
                  tip="Go through every text markup in the document, word by "
                      "word, and correct what the dictionary does not know")
        self._act("apply_redactions", "Apply Redactions…", self.apply_redactions, "",
                  tip="Permanently remove what the black boxes cover")

        self._act("shortcuts", "Keyboard Shortcuts…", self.show_shortcuts, "F1",
                  tip="Every shortcut, and the keys you want them on")
        # Revu calls it Search, on its Edit menu and its page menu, and it
        # opens the panel of the same name (QA, 2026-10-15).
        self._act("find_text", "Search", self.find_in_document, "Ctrl+F",
                  tip="Find words in the drawing and in the markups, on every "
                      "page, and replace them in the markups")
        self._act("find_tool", "Find Tools + Commands", self.find_a_tool, "Shift+F1",
                  tip="Type what you want to do, and it says which tool does "
                      "it and which key it is on")
        self._act("renumber_counts", "Renumber Counts", self.renumber_counts,
                  tip="Renumber the count markers in page order")
        self._act("group", "Group", self.group_selection, "Ctrl+G",
                  tip="Make the selected markups one thing to click and move")
        self._act("ungroup", "Ungroup", self.ungroup_selection, "Ctrl+Shift+G")
        self._act("autosize", "Auto-Size", self.autosize_text, "Alt+Z",
                  tip="Shrink the box around the words in it")
        self._act("format_painter", "Format Painter", self.format_painter,
                  "Ctrl+Shift+C", "format_painter",
                  tip="Take this one's look, then click another to paint it on")
        self._act("hide", "Hide", self.hide_selection,
                  tip="Take it off the screen and out of the print, without "
                      "deleting it — Show Hidden brings it back")
        self._act("show_hidden", "Show Hidden", self.show_hidden,
                  tip="Bring back everything that was hidden")
        self._act("flatten", "Flatten", self.flatten_selection,
                  tip="Make it part of the drawing rather than a markup on top "
                      "of it — it can no longer be moved or edited")
        # Revu's keys for Flatten… and Unflatten (QA, 2026-10-15)
        self._act("flatten_document", "Flatten…", self.flatten_document, "Ctrl+Shift+M",
                  tip="Flatten Markups: choose the types, which markups and pages, "
                      "and whether Unflatten can bring them back")
        self._act("recover_flattened", "Unflatten", self.recover_flattened, "Ctrl+Shift+U",
                  tip="Restore source items retained by recoverable flattening")
        self._act("preferences", "Preferences…", self.edit_preferences, "Ctrl+,",
                  tip="How the wheel behaves, how blocks start, spell checking")
        self._act("forget_defaults", "Forget Defaults", self.forget_defaults,
                  tip="Put every kind of markup back to how it started")
        self._act("bookmark", "Add Bookmark", self.add_bookmark_here, "Ctrl+B",
                  tip="Name this place so it can be jumped to, printed in a "
                      "contents block and exported as a PDF bookmark")
        self._act("contents", "Table of Contents", self.insert_contents_block,
                  tip="Insert a table of contents built from document bookmarks")
        self._act("about", f"About {APP_NAME}", self.show_about)
        self._act("color_processing", "Colour Processing…", lambda: self.color_processing(),
                  tip="Bluebeam's Colour Processing: change the page's own colours — modify, "
                      "colourise, greyscale, black and white, luminosity/saturation/hue, "
                      "mask images")
        self._act("record_slowdowns", "Record Slow-Downs", self.record_slowdowns, checkable=True,
                  tip="Note what the window was doing whenever it stalled, in a file to send back")
        # Excel's and Word's Ctrl+H (novice 19): the Search panel, ready to
        # replace. In an open table Ctrl+H is the cells' own Replace.
        self._act("replace_text", "Replace", self.replace_in_document, "Ctrl+H",
                  tip="Search for words and replace them in the markups (the "
                      "Search panel, with the Replace box ready)")
        # Excel's Page Layout ▸ Breaks and Print Area (novice 11), on the menu
        # bar as well as the cells' right-click menu: they act on the
        # spreadsheet open for typing, at its active cell
        self._act("insert_page_break", "Insert Page Break", self.insert_page_break,
                  tip="A page break above the active cell's row and left of its column")
        self._act("remove_page_break", "Remove Page Break", self.remove_page_break,
                  tip="Take away the page breaks at the active cell's top and left")
        self._act("reset_page_breaks", "Reset All Page Breaks", self.reset_page_breaks,
                  tip="Every page break of this spreadsheet back to where it falls by itself")
        self._act("set_print_area", "Set Print Area", self.set_print_area,
                  tip="Print only the cells picked out")
        self._act("clear_print_area", "Clear Print Area", self.clear_print_area,
                  tip="Print the whole spreadsheet again")
        for key, revu in self.REVU_SECOND_KEYS.items():
            self._second_key(key, revu)

    # Revu's keys for commands that already had one of ours. Both work: ours
    # are kept so nobody's fingers are broken, and Revu's goes first so the
    # menus show the key a Revu user expects (QA, 2026-10-15). Ctrl+Left and
    # Ctrl+Right are the page keys on Revu's own page menu; Ctrl+Y is Revu's
    # (and Windows') Redo, which Linux spells Ctrl+Shift+Z.
    REVU_SECOND_KEYS = {
        "next_page": "Ctrl+Right", "prev_page": "Ctrl+Left",
        "redo": "Ctrl+Y", "lock": "Ctrl+Shift+L",
    }

    def _second_key(self, key: str, default: str) -> None:
        """Give act_<key> a second key, in the shortcut list under its own
        name so it can be seen and changed like any other."""
        action = getattr(self, f"act_{key}")
        action_id = f"command.{key}.also"
        self.shortcuts.register(action_id, f"{action.text().rstrip('…')} (Revu's key)",
                                default, _SHORTCUT_GROUPS.get(key, "Document"))
        self.second_key_ids[key] = action_id
        action.setShortcuts(self._keys_for(key, self.shortcuts.sequence(self.action_ids[key])))

    def _keys_for(self, key: str, sequence: str) -> list:
        """The keys act_<key> answers to: its second (Revu's) key first, then
        its own."""
        keys = []
        second = self.second_key_ids.get(key)
        for text in (self.shortcuts.sequence(second) if second else "", sequence):
            if text and QKeySequence(text) not in keys:
                keys.append(QKeySequence(text))
        return keys

    def _add_toolbar(self, bar) -> None:
        """Toolbars go on any edge, and remember where they were put. On the
        left or right edge one is a column of its own outside the panel rail
        (arrange_side_toolbars); the Properties toolbar, whose boxes do not
        work on end, goes top or bottom only."""
        bar.setMovable(True)
        bar.setFloatable(False)
        if bar.objectName() in self.TOP_AND_BOTTOM_ONLY:
            bar.setAllowedAreas(Qt.TopToolBarArea | Qt.BottomToolBarArea)
        else:
            bar.setAllowedAreas(Qt.AllToolBarAreas)
        bar.orientationChanged.connect(
            lambda orientation, b=bar: self._toolbar_stood_on_end(b, orientation))
        bar.topLevelChanged.connect(
            lambda floating: None if floating else self._arrange_side_toolbars_soon())
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
        # The Calculation bar and the measuring tools share the first row with
        # the file actions, which use barely a third of it. Beside the markup
        # tools the Calculation bar was left 63 px and showed one button of
        # twelve at 1280 px wide, even in Calc mode, and the markup tools hid
        # fifteen of their own (QA, 2026-10-15). Revu has Markup and Measure
        # as toolbars of their own too. A row with too little room for its
        # bars wraps, the last bar going to a row of its own, as Revu's do
        # (_wrap_toolbar_rows).
        self._add_toolbar(self._calculation_bar())

        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_actions: dict[str, QAction] = {}
        tool_bar = QToolBar("Tools")
        tool_bar.setObjectName("toolbar_tools")
        tool_bar.setIconSize(QSize(22, 22))
        measure_bar = QToolBar("Measure")
        measure_bar.setObjectName("toolbar_measure")
        measure_bar.setIconSize(QSize(22, 22))
        for category in CATEGORIES:
            # Sketch to Scale's shapes sit with the measurements they share
            # the page scale with, as on Revu's Measure toolbar
            bar = measure_bar if category in ("Measure", SKETCH) else tool_bar
            if bar.actions():
                bar.addSeparator()
            for tool in tools_in(category):
                action = self.give_icon(QAction(tool.label, self), tool.icon)
                action.setCheckable(True)
                action.setToolTip(f"{tool.label}"
                                  + (f"  ({tool.shortcut})" if tool.shortcut else "")
                                  + (f"\n{tool.hint}" if tool.hint else ""))
                if tool.shortcut and len(tool.shortcut) == 1:
                    action.setShortcut(QKeySequence(tool.shortcut))
                if tool.key == "table":
                    # the same command as Calculation ▸ Table (novice 21)
                    action.triggered.connect(lambda _checked=False: self.insert_table())
                else:
                    action.triggered.connect(lambda _checked=False, key=tool.key:
                                             self.select_tool(key))
                self.tool_group.addAction(action)
                # Sketch to Scale's Rectangle and Ellipse are buttons of their
                # own, as on Revu's Measure toolbar (the user, 2026-10-17: the
                # one drop-down they shared drew its arrow over the icon)
                bar.addAction(action)
                self.tool_actions[tool.key] = action
                action.setProperty(bindable.COMMAND, f"tool.{tool.key}")
        tool_bar.addSeparator()
        tool_bar.addAction(self.act_sticky)
        # The Calculation bar's Table is the Tools bar's Table — one button
        # in two places, so it reads, tips and lights up the same (novice 21)
        self.calculation_bar.insertAction(self.act_insert_table, self.tool_actions["table"])
        self.calculation_bar.removeAction(self.act_insert_table)
        self._add_toolbar(measure_bar)
        # The markup tools get a row to themselves: there are enough of them
        # that sharing one with anything else hides the last few.
        self.addToolBarBreak()
        self._add_toolbar(tool_bar)
        self._build_markup_styles_bar()       # beside the tools, or wrapped below them
        self.addToolBarBreak()

        # Revu's Properties toolbar (ui/propbar.py): what the selected markup
        # is, then Line, Fill, Hatch and Font, each control as narrow as what
        # it shows
        self.default_cloud_size = 2.0       # Bluebeam's cloud Size
        from . import propbar
        style_bar = propbar.build(self)
        self._show_tool_extras("select")
        self._add_toolbar(style_bar)
        self._refresh_style_controls()

    def _build_markup_styles_bar(self) -> None:
        """The Markup Styles toolbar (markupstyles.py), on the Main bar's row:
        Tools ▸ Toolbars ▸ Markup Styles shows and hides it."""
        from .markupstyles import MarkupStyles
        self.markup_styles = MarkupStyles(self)
        self._add_toolbar(self.markup_styles.bar)
        # it grows and shrinks with the tool in hand: its row wraps to suit
        self._styles_relayout = _OnRelayout(self._wrap_toolbar_rows_soon, self)
        self.markup_styles.bar.installEventFilter(self._styles_relayout)

    def _calculation_bar(self) -> QToolBar:
        """Decision 18: MarkForge's toolbars, and a condensed Calculation
        section beside the tools. Result format, font, size and colours are
        not here: their defaults are in Preferences, and each equation's own
        are on its right-click menu and in Properties."""
        bar = QToolBar("Calculation")
        bar.setObjectName("toolbar_calculation")
        bar.setIconSize(QSize(22, 22))
        for key, name in (("calculate", "recalc"), ("auto_calc", "calc_auto"),
                          (None, None), ("insert_plot", "calc_plot"),
                          ("insert_matrix", "calc_matrix"),
                          ("insert_calc_text", "calc_text"), ("insert_block", "calc_block"),
                          ("insert_table", "table"),
                          (None, None),
                          ("prog_if", "prog_if"), ("prog_for", "prog_for"),
                          ("prog_while", "prog_while"), ("prog_line", "prog_line")):
            if key is None:
                bar.addSeparator()
                continue
            action = getattr(self, f"act_{key}")
            self.give_icon(action, name)
            bar.addAction(action)
        self.calculation_bar = bar
        return bar

    def _dock(self, title: str, widget: QWidget, area: Qt.DockWidgetArea,
              name: str) -> PanelDock:
        dock = PanelDock(title, widget, name, self)
        dock.hide()                 # closed until its rail opens it (_build_rails)
        self.addDockWidget(area, dock)
        self.panels.append(dock)
        return dock

    def _build_docks(self) -> None:
        self.panels: list[PanelDock] = []
        self.pages_panel = PagesPanel(self)
        self.dock_pages = self._dock("Thumbnails", self.pages_panel, Qt.LeftDockWidgetArea,
                                     "dock_pages")
        self.properties_panel = PropertiesPanel(self)
        self.dock_properties = self._dock("Properties", self.properties_panel,
                                          Qt.RightDockWidgetArea, "dock_properties")
        self.markups_panel = MarkupsPanel(self)
        self.markups_panel.setObjectName("markupsList")
        self.bottom_split.addWidget(self.markups_panel)
        self.bottom_split.setCollapsible(1, True)
        self._markups_height = 220
        self.bottom_split.setSizes([1, 0])
        # Double-clicking the list's handle bar hides it, or brings it back
        # at the height it had (as Revu's Markups List does).
        self._markups_handle_toggle = _DoubleClickToggle(
            lambda: self.show_markups_list(not self.markups_list_open()), self)
        self.bottom_split.handle(1).installEventFilter(self._markups_handle_toggle)
        self.toolsets_panel = ToolSetsPanel(self)
        self.dock_toolsets = self._dock("Tool Chest", self.toolsets_panel,
                                        Qt.LeftDockWidgetArea, "dock_toolsets")
        self.bookmarks_panel = BookmarksPanel(self)
        self.bookmarks_panel.bookmarkActivated.connect(self.go_to_bookmark)
        self.dock_bookmarks = self._dock("Bookmarks", self.bookmarks_panel,
                                         Qt.LeftDockWidgetArea, "dock_bookmarks")
        from .searchpanel import SearchPanel
        self.search_panel = SearchPanel(self)
        self.dock_search = self._dock("Search", self.search_panel,
                                      Qt.LeftDockWidgetArea, "dock_search")
        from .pagepanel import PagePanel
        self.page_panel = PagePanel(self)
        # "Page", not "Page Setup": that is the dialog (bug hunt E12). Alt+U,
        # Revu's Measurements key: the scale and viewports live here.
        self.dock_page = self._dock("Page", self.page_panel,
                                    Qt.RightDockWidgetArea, "dock_page")
        from .mathspanel import MathsPanel
        self.maths_panel = MathsPanel(self)
        self.dock_maths = self._dock("Maths", self.maths_panel,
                                     Qt.RightDockWidgetArea, "dock_maths")
        from .variablespanel import VariablesPanel
        self.variables_panel = VariablesPanel(self)
        self.dock_variables = self._dock("Variables", self.variables_panel,
                                         Qt.RightDockWidgetArea, "dock_variables")
        self.reference_docks = [self.dock_toolsets, self.dock_bookmarks]
        self._build_rails()
        self.resizeDocks([self.dock_pages, self.dock_properties], [220, 320],
                         Qt.Horizontal)

    # -- the icon rails ----------------------------------------------------
    #
    # Every panel is behind one icon on one of the two rails. Which side it is
    # on is remembered; dragging its icon across moves it.
    PANEL_ICONS = {
        "dock_pages": ("Thumbnails", "panel_pages"),
        "dock_bookmarks": ("Bookmarks", "panel_bookmarks"),
        "dock_toolsets": ("Tool Chest", "panel_toolsets"),
        "dock_properties": ("Properties", "panel_properties"),
        "dock_search": ("Search", "panel_search"),
        "dock_page": ("Page", "panel_page"),
        "dock_maths": ("Maths", "panel_maths"),
        "dock_variables": ("Variables", "panel_variables"),
    }
    DEFAULT_SIDES = {
        "dock_pages": LEFT, "dock_bookmarks": LEFT, "dock_toolsets": LEFT,
        "dock_search": LEFT,
        "dock_properties": RIGHT, "dock_page": RIGHT, "dock_maths": RIGHT,
        "dock_variables": RIGHT,
    }

    # -- the markups list under the canvas ---------------------------------
    def markups_list_open(self) -> bool:
        sizes = self.bottom_split.sizes()
        return len(sizes) > 1 and sizes[1] > 0

    def show_markups_list(self, open_now: bool = True) -> None:
        """Open the list at the height it last had, or close it."""
        total = max(sum(self.bottom_split.sizes()), 400)
        if open_now:
            height = max(min(self._markups_height, total - 120), 120)
            self.bottom_split.setSizes([total - height, height])
            self.markups_panel.rebuild(self.document)
        else:
            if self.markups_list_open():
                self._markups_height = self.bottom_split.sizes()[1]
            self.bottom_split.setSizes([total, 0])
        self._say_markups_list()
        self.note_layout_change()

    def _markups_list_moved(self, _position: int, _index: int) -> None:
        if self.markups_list_open():
            self._markups_height = self.bottom_split.sizes()[1]
        self._say_markups_list()
        self.note_layout_change()

    def _say_markups_list(self) -> None:
        action = getattr(self, "act_markups_list", None)
        if action is not None and action.isChecked() != self.markups_list_open():
            action.blockSignals(True)
            action.setChecked(self.markups_list_open())
            action.blockSignals(False)

    def _build_rails(self) -> None:
        self.panel_sides = load_sides(self.DEFAULT_SIDES)
        self.docks_by_name = {dock.objectName(): dock for dock in self.panels}
        for rail in (self.left_rail, self.right_rail):
            rail.toggled.connect(self.show_panel)
            rail.moved.connect(self.move_panel_to_side)
        stored = [name for name in load_order() if name in self.PANEL_ICONS]
        ordered = stored + [name for name in self.PANEL_ICONS if name not in stored]
        for name in ordered:
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
        if dock.isFloating() or self.dockWidgetArea(dock) != AREAS[side]:
            self.addDockWidget(AREAS[side], dock)
        dock.setVisible(open_now)
        rail.show_open(name, open_now)
        self.tabify_panels()

    # Panels on one side are tabs of one another, one shown at a time, as
    # Revu's are; the rail's icons switch between them. They are never split
    # one above the other (the user, 2026-10-15: "There shouldn't be panel
    # stacked on panel on the side"): a panel dropped beside or below another
    # joins its tabs instead, and an arrangement saved with panels stacked
    # is tabbed when it is put back.
    def tabify_panels(self) -> None:
        """Make the open panels in each dock area one set of tabs.

        Only open ones: the rail keeps one panel open on a side, so a closed
        one can never be stacked under another, and Qt left the tab bars of
        sets of closed panels lying about (one showed "Tool Chest" under the
        Thumbnails in a tall window)."""
        groups: dict = {}
        for dock in self.panels:
            if dock.isFloating() or dock.isHidden():
                continue
            area = self.dockWidgetArea(dock)
            if area == Qt.NoDockWidgetArea:
                continue
            groups.setdefault(area, []).append(dock)
        # the moves this makes are not taken for a user's drop
        self._tabifying = True
        try:
            for docks in groups.values():
                first = docks[0]
                together = set(self.tabifiedDockWidgets(first))
                for dock in docks[1:]:
                    if dock not in together:
                        self.tabifyDockWidget(first, dock)
        finally:
            self._tabifying = False

    def _panel_landed(self, name: str) -> None:
        """A panel was dragged somewhere: into its side's tabs, and onto that
        side's rail if it went to the other side."""
        dock = self.docks_by_name.get(name)
        if dock is None or dock.isFloating():
            return
        side = {Qt.LeftDockWidgetArea: LEFT,
                Qt.RightDockWidgetArea: RIGHT}.get(self.dockWidgetArea(dock))
        if side is not None and self.panel_sides.get(name) != side \
                and name in self.PANEL_ICONS:
            was_open = not dock.isHidden()
            self.move_panel_to_side(name, side)
            if was_open:
                self.show_panel(name, True)
        self.tabify_panels()

    def _panel_floated(self, dock, floating: bool) -> None:
        """A panel came off its side. By its float button it stays a window
        of its own; by a drag it is put back on its side if the drag ends
        anywhere but on a side (the user, 2026-10-16: dragged into the middle
        it was left lying over the canvas and the other panels)."""
        if not floating:
            dock.floated_on_purpose = False
            return
        if dock.floated_on_purpose:
            return
        timer = getattr(self, "_drag_watch", None)
        if timer is None:
            timer = self._drag_watch = QTimer(self)
            timer.setInterval(40)
            timer.timeout.connect(self._panel_drag_over)
        self._dragged_panels = getattr(self, "_dragged_panels", set())
        self._dragged_panels.add(dock)
        timer.start()

    def _panel_drag_over(self) -> None:
        if QApplication.mouseButtons() & Qt.LeftButton:
            return                              # still being dragged
        self._drag_watch.stop()
        for dock in list(getattr(self, "_dragged_panels", ())):
            self.put_panel_back(dock)
        self._dragged_panels = set()

    def put_panel_back(self, dock) -> None:
        """A panel a drag left floating, or a saved arrangement left along
        the top or bottom, goes back to its own side, open, among its tabs."""
        from shiboken6 import isValid
        if not isValid(dock) or dock.floated_on_purpose:
            return
        area = self.dockWidgetArea(dock)
        if not dock.isFloating() and area in (Qt.LeftDockWidgetArea, Qt.RightDockWidgetArea):
            return
        name = dock.objectName()
        side = self.panel_sides.get(name, self.DEFAULT_SIDES.get(name, LEFT))
        was_open = not dock.isHidden()
        dock.setFloating(False)
        self.addDockWidget(AREAS[side], dock)
        if was_open and name in self.PANEL_ICONS:
            self.show_panel(name, True)
        self.tabify_panels()
        self.note_layout_change()

    # -- a panel column's edge (the user, 2026-10-17) -----------------------
    # Double-clicking the edge between a panel column and the canvas hides
    # the column, as double-clicking the Markups List's bar does; the column
    # leaves a thin edge (docks.PanelEdge) that a double-click or a drag
    # brings it back from, at the width it had.
    def open_panel_on(self, side: str):
        """The panel open on *side*, docked there, or None."""
        for name, dock in self.docks_by_name.items():
            if (name in self.PANEL_ICONS and not dock.isHidden() and not dock.isFloating()
                    and self.dockWidgetArea(dock) == AREAS[side]):
                return dock
        return None

    def panel_column_edge(self, side: str) -> Optional[QRect]:
        """Where the edge between *side*'s panel column and the canvas is,
        in window coordinates (QMainWindow's own separator), or None."""
        dock = self.open_panel_on(side)
        central = self.centralWidget()
        if dock is None or central is None:
            return None
        panel, canvas = dock.geometry(), central.geometry()
        if side == LEFT:
            left, right = panel.right() + 1, canvas.left() - 1
        else:
            left, right = canvas.right() + 1, panel.left() - 1
        # the separator, and a pixel or two either side of it
        return QRect(left - 2, panel.top(), max(right - left + 1, 1) + 4, panel.height())

    def toggle_panel_column(self, side: str) -> None:
        """Hide *side*'s panel column, or bring it back."""
        dock = self.open_panel_on(side)
        if dock is None:
            self.open_panel_column(side)
            return
        memory = getattr(self, "_edge_hidden", {})
        memory[side] = (dock.objectName(), dock.width())
        self._edge_hidden = memory
        self.show_panel(dock.objectName(), False)
        self.status_hint.setText(
            f"{'Left' if side == LEFT else 'Right'} panels hidden — double-click the edge "
            "to bring them back")

    def open_panel_column(self, side: str, width: Optional[int] = None) -> None:
        """Bring *side*'s panel column back: the panel last open there, at
        the width it had (or *width*, dragged out from the edge)."""
        memory = getattr(self, "_edge_hidden", {})
        name, old_width = memory.pop(side, (None, None))
        if name is None or name not in self.docks_by_name:
            hidden = [n for n in getattr(self, "_panels_hidden", None) or []
                      if self.panel_sides.get(n, LEFT) == side]
            name = hidden[0] if hidden else ("dock_pages" if side == LEFT else "dock_properties")
            if self.panel_sides.get(name, LEFT) != side:
                name = next((n for n in self.PANEL_ICONS
                             if self.panel_sides.get(n, LEFT) == side), None)
        if name is None:
            return
        self.show_panel(name, True)
        width = width if width is not None else old_width
        dock = self.docks_by_name[name]
        if width:
            width = max(int(width), 120)
            self.resizeDocks([dock], [width], Qt.Horizontal)
            # once it is laid out too: Qt sizes a dock just shown on the next pass
            QTimer.singleShot(0, self, lambda: self.resizeDocks([dock], [width], Qt.Horizontal))

    def _show_panel_edges(self) -> None:
        edges = getattr(self, "panel_edges", None)
        if not edges or not hasattr(self, "docks_by_name") or self._closed_for_good:
            return                  # (its docks report going as the window goes)
        import shiboken6
        if not shiboken6.isValid(self):
            return
        for side, edge in edges.items():
            empty = self.open_panel_on(side) is None
            if edge.isHidden() == empty:
                edge.setVisible(empty)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            at = event.position().toPoint()
            for side in (LEFT, RIGHT):
                zone = self.panel_column_edge(side)
                if zone is not None and zone.contains(at):
                    self.toggle_panel_column(side)
                    event.accept()
                    return
        super().mouseDoubleClickEvent(event)

    def _panel_landed_soon(self, name: str) -> None:
        if getattr(self, "_tabifying", False):
            return
        from shiboken6 import isValid
        QTimer.singleShot(0, self, lambda: self._panel_landed(name)
                          if isValid(self) else None)

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

    def move_panel_to_side(self, name: str, side: str, position: int = -1) -> None:
        """Drag a panel's icon along its rail, or to the other rail.

        Dropped on the other rail the panel goes with it; dropped on its own
        rail it only changes place in the column.
        """
        rail = self.left_rail if side == LEFT else self.right_rail
        if self.panel_sides.get(name) != side:
            dock = self.docks_by_name.get(name)
            was_open = dock is not None and not dock.isHidden()
            self._place_panel(name, side, open_now=False)
            if was_open:
                self.show_panel(name, True)
            save_sides(self.panel_sides)
        rail.place_at(name, position)
        save_order(self.left_rail.order() + self.right_rail.order())
        self.note_layout_change()

    def sync_rails(self) -> None:
        """Put the icons back in step with which panels are actually open.

        isHidden rather than isVisible: a panel in a window that has not been
        shown yet is not visible, but it has not been closed either, and its
        icon should say so.
        """
        self._show_panel_edges()
        for name, dock in self.docks_by_name.items():
            if name in self.PANEL_ICONS:
                self.rail_for(name).show_open(name, not dock.isHidden())
                # and its tick in Window ▸ Panels
                action = getattr(self, f"act_panel_{name[5:]}", None)
                if action is not None and action.isChecked() == dock.isHidden():
                    action.blockSignals(True)
                    action.setChecked(not dock.isHidden())
                    action.blockSignals(False)

    def _build_search(self) -> None:
        # The Markup | Calc switch and the search box sit after Help in the
        # window's own menu bar (Windows); on a Mac the menus are the Mac's.
        self.menuBar().setNativeMenuBar(NATIVE_MENU_BAR)
        """The search field in the menu bar's corner, with its live dropdown."""
        from PySide6.QtGui import QStandardItemModel
        from PySide6.QtWidgets import QCompleter

        field = QLineEdit(self)
        field.setObjectName("searchField")
        field.setPlaceholderText("Search")
        field.setToolTip("Search tools, commands, markups and pages as you type")
        field.setClearButtonEnabled(True)
        field.setFixedWidth(260)
        self.search_field = field
        self._search_results: list = []
        self._search_model = QStandardItemModel(self)
        completer = QCompleter(self._search_model, self)
        completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setMaxVisibleItems(14)
        completer.setWidget(field)
        completer.activated[QModelIndex].connect(self._search_chosen)
        self._search_completer = completer
        field.textEdited.connect(self._search_typed)
        field.returnPressed.connect(self._search_enter)
        # Markup | Calc on the menu bar, after Help: always in sight, never in
        # a toolbar that can be dragged away or hidden — what typing on the
        # page does depends on it (the user, 2026-10-01)
        from .widgets import ModeSwitch
        self.mode_switch = ModeSwitch()
        self.mode_switch.toggled.connect(lambda on: self.toggle_calc_mode(on))
        holder = QWidget(self)
        holder.setObjectName("menuBarCorner")
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 1, 8, 1)
        row.setSpacing(10)
        row.addWidget(self.mode_switch)
        row.addWidget(field)
        self.menuBar().setCornerWidget(holder, Qt.TopRightCorner)
        self._menu_corner_fitter = _OnResize(self._fit_menu_corner, self)
        self.menuBar().installEventFilter(self._menu_corner_fitter)

    #: The search field's width when the menu row has room, and the least it
    #: is squeezed to when it has not.
    SEARCH_WIDTH = (150, 260)

    def _fit_menu_corner(self) -> None:
        """Narrow the search field before the menus have to go behind the
        menu bar's » — and never so far that the room kept for Windows'
        caption buttons is pushed off the row.

        The menu bar lays its right-hand corner out at the width it asks for,
        whatever room there is: with a 260 px search field the corner asked
        for 470 px and, in a window half a screen wide, sat over the menus
        and hid the » that leads to them (QA, 2026-10-15).
        """
        field = getattr(self, "search_field", None)
        bar = self.menuBar()
        if field is None or bar.isNativeMenuBar():
            return
        narrowest, widest = self.SEARCH_WIDTH
        # everything on the row but the field, at the width it asks for
        others = bar.sizeHint().width() - field.width()
        width = max(narrowest, min(widest, bar.width() - others))
        if width != field.width():
            field.setFixedWidth(width)

    def search_everything(self, wanted: str) -> list:
        """Everything that matches *wanted*: (label, kind, target), best first."""
        text = wanted.strip().lower()
        if not text:
            return []
        words = text.split()
        found: list = []
        for tool in self.tools_matching(wanted):
            label = tool.label + (f"  ({tool.shortcut})" if tool.shortcut else "")
            found.append((label, "Tool", tool.key))
        seen = {tool.label.lower() for tool in TOOLS}
        commands = []
        for action in self.findChildren(QAction):
            name = action.text().replace("&", "").rstrip("…").strip()
            if (not name or action.isSeparator() or action.menu() is not None
                    or name.lower() in seen):
                continue
            haystack = f"{name} {action.toolTip()}".lower()
            if all(word in haystack for word in words):
                seen.add(name.lower())
                first = name.lower().startswith(words[0])
                commands.append((0 if first else 1, name, action))
        commands.sort(key=lambda row: (row[0], row[1]))
        for _rank, name, action in commands:
            key = action.shortcut().toString()
            found.append((name + (f"  ({key})" if key else ""), "Command", action))
        for index, page in enumerate(self.document.pages):
            label = page.label.strip() or f"Page {index + 1}"
            if all(word in f"{label} page {index + 1}".lower() for word in words):
                found.append((label, "Page", index))
            if page.frame is None:
                continue
            for item in page.frame.markups():
                if getattr(item, "from_drawing", False):
                    continue
                words_on_it = " ".join(str(getattr(item, name, "") or "") for name in
                                       ("written", "value_text", "subject",
                                        "comment", "label", "text"))
                haystack = f"{item.display_name()} {words_on_it}".lower()
                if all(word in haystack for word in words):
                    shown = " ".join(words_on_it.split())[:48]
                    found.append((f"{item.display_name()}: {shown}" if shown
                                  else item.display_name(),
                                  f"Markup · page {index + 1}", (index, item.uid)))
        # Last, so Enter still picks the best tool or command: the same words
        # looked for in the drawing and the markups, in the Search panel.
        return found[:59] + [(f"Find “{wanted.strip()}” in the document", "Find",
                              wanted.strip())]

    def _search_typed(self, wanted: str) -> None:
        from PySide6.QtGui import QStandardItem

        self._search_results = self.search_everything(wanted)
        self._search_model.clear()
        for number, (label, kind, _target) in enumerate(self._search_results):
            row = QStandardItem(f"{label}    —  {kind}")
            row.setData(number, Qt.UserRole)
            row.setEditable(False)
            self._search_model.appendRow(row)
        if self._search_results:
            self._search_completer.complete()
        else:
            self._search_completer.popup().hide()

    def _search_enter(self) -> None:
        popup = self._search_completer.popup()
        current = popup.currentIndex() if popup.isVisible() else QModelIndex()
        number = current.data(Qt.UserRole) if current.isValid() else None
        self._run_search_result(int(number) if number is not None else 0)

    def _search_chosen(self, index) -> None:
        number = index.data(Qt.UserRole)
        if number is not None:
            self._run_search_result(int(number))

    def _run_search_result(self, number: int) -> None:
        if not 0 <= number < len(self._search_results):
            return
        label, kind, target = self._search_results[number]
        # Spent: a second signal for the same Enter finds nothing to run.
        self._search_results = []
        self.search_field.clear()
        self._search_completer.popup().hide()
        self.view.setFocus(Qt.OtherFocusReason)
        if kind == "Tool":
            self.select_tool(target)
            self.status_hint.setText(label)
        elif kind == "Command":
            target.trigger()
        elif kind == "Page":
            self.go_to_page(target)
        elif kind == "Find":
            self.find_in_document(target)
        else:
            page_index, uid = target
            self.reveal_markup(page_index, uid)

    # -- the ways of putting pages in: one family, one shape -------------------------
    def insert_family(self) -> list:
        """Every way of putting pages in, in the order every menu lists them
        (bug hunt E1–E4): (act key, its name on its own, whether it opens a
        dialog, what it does given (page, before), what it puts in)."""
        return [
            ("add_page", "Insert Blank Page", True,
             lambda i, b: self.add_page(i, before=b), "A blank page"),
            ("add_sheet_page", "Insert Spreadsheet Page", False,
             lambda i, b: self.insert_sheet_page(i, before=b), "A page of spreadsheet cells"),
            ("insert_pdf", "Insert Pages", True,
             lambda i, b: self.insert_pdf(i, before=b), "Pages from a PDF"),
            ("insert_image_page", "Insert Image Page", True,
             lambda i, b: self.insert_image_page(i, before=b), "An image as a page"),
            ("insert_workbook", "Insert Excel Workbook", True,
             lambda i, b: self.insert_workbook(None, i, before=b),
             "An Excel workbook's sheets as spreadsheet pages"),
        ]

    def fill_insert_choice(self, sub: QMenu, entry: tuple, index: Optional[int] = None) -> None:
        """Before / After for one member of the insert family: of page
        *index*, or of the page in view at the time when it is None."""
        key, _name, dialog, run, what = entry
        where = f"page {index + 1}" if index is not None else "the page in view"
        if key == "add_sheet_page":
            page = self.document.pages[self.page_index(index)] if index is not None else None
            if page is not None and page.sheet is not None:
                what = "Another page of this spreadsheet, at its end"
        dots = "…" if dialog else ""
        before = sub.addAction(f"Before{dots}", lambda _c=False: run(index, True))
        before.setToolTip(f"{what}, placed before {where}")
        after = sub.addAction(f"After{dots}", lambda _c=False: run(index, False))
        after.setToolTip(f"{what}, placed after {where}")
        before.setStatusTip(before.toolTip())
        after.setStatusTip(after.toolTip())

    def _build_insert_family(self) -> None:
        """Each insert command carries its own Before / After submenu, so
        wherever the command is put — Document ▸ Insert, File ▸ Import, the
        Main toolbar's button — it is offered the same way. Its key, or a
        click on the button itself, puts it after the page in view."""
        for entry in self.insert_family():
            action = getattr(self, f"act_{entry[0]}")
            sub = QMenu(action.text(), self)
            sub.setObjectName(f"menuInsert_{entry[0]}")
            bindable.set_context(sub, f"insert.{entry[0]}")
            self.fill_insert_choice(sub, entry)
            after = sub.actions()[-1]

            def show_key(after=after, action=action):
                # the key the command answers to, beside the choice it makes
                after.setShortcut(action.shortcut())
                after.setShortcutContext(Qt.WidgetShortcut)
            sub.aboutToShow.connect(show_key)
            action.setMenu(sub)

    def _tool_entry(self, key: str, under: str = "") -> QAction:
        """A menu entry that picks up tool *key*, under the tool's own name —
        less the submenu's name it sits *under* (Revu's Tools ▸ Sketch to
        Scale ▸ Rectangle)."""
        tool = TOOL_MAP[key]
        text = tool.label
        if under and text.startswith(under + " "):
            text = text[len(under) + 1:]
        entry = self.give_icon(QAction(text, self), tool.icon)
        # the tool's own binding: its key is shown here and works everywhere
        entry.setProperty(bindable.COMMAND, f"tool.{key}")
        entry.setProperty(bindable.SHOWN, True)
        entry.setToolTip(tool.hint)
        entry.setStatusTip(tool.hint)
        if key == "table":
            entry.triggered.connect(lambda _c=False: self.insert_table())
        else:
            entry.triggered.connect(lambda _c=False, k=key: self.select_tool(k))
        self.insert_tool_actions.setdefault(key, []).append(entry)
        return entry

    # Revu's Alt keys for its panels (audit L2/L3), and their names in
    # Window ▸ Panels, which Revu lists alphabetically
    PANEL_KEYS = {"dock_bookmarks": "Alt+B", "dock_page": "Alt+U", "dock_search": "Alt+1",
                  "dock_pages": "Alt+T", "dock_toolsets": "Alt+X"}

    def _build_panel_actions(self) -> list:
        """Window ▸ Panels: one checkable entry per panel, with Revu's key,
        kept in step with the rails (sync_rails)."""
        made = []
        for name, (label, _icon) in self.PANEL_ICONS.items():
            key = f"panel_{name[5:]}"
            action = self._act(key, label,
                               lambda on, n=name: self.show_panel(n, on),
                               self.PANEL_KEYS.get(name, ""), checkable=True,
                               name=f"{label} Panel",
                               tip=f"Open or close the {label} panel")
            action.setChecked(not self.docks_by_name[name].isHidden())
            made.append(action)
        made.append(self.act_markups_list)
        return sorted(made, key=lambda a: a.text().lower())

    def _build_menus(self) -> None:
        """Bluebeam Revu's menu bar — Revu, File, Edit, View, Document, Batch,
        Tools, Window, Help — with CalcForge's own Calculation menu between
        Tools and Window (the user's choice, 2026-10-14). Every command keeps
        its place in one of them; what Revu has, where Revu has it, in Revu's
        order (audit B1, L1–L6), each family together and named alike
        everywhere (bug hunt E1–E19)."""
        from . import menutidy
        bar = self.menuBar()
        self._build_search()
        self._build_insert_family()
        self.insert_tool_actions: dict[str, list[QAction]] = {}

        def fill(menu, actions):
            for action in actions:
                if action is None:
                    menu.addSeparator()
                elif isinstance(action, QMenu):
                    menu.addMenu(action)
                else:
                    menu.addAction(action)

        revu_menu = bar.addMenu("CalcFo&rge")
        revu_menu.setObjectName("menuApp")
        # Preferences and Keyboard Shortcuts are in Revu's own menu (decided
        # 2026-10-15; F1 stays on Keyboard Shortcuts, which is CalcForge's help
        # for its keys — audit L6 was unsure of Revu's key)
        fill(revu_menu, (self.act_about, None, self.act_preferences, self.act_shortcuts,
                         None, self.act_quit))

        # -- File ---------------------------------------------------------------
        file_menu = bar.addMenu("&File")
        fill(file_menu, (self.act_new, self.act_new_tab, self.act_new_window, self.act_open))
        self.recent_menu = file_menu.addMenu("Open Recent")
        self.recent_menu.setObjectName("menuOpenRecent")
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        fill(file_menu, (None, self.act_close_tab, self.act_close_all, None,
                         self.act_save, self.act_save_as, self.act_save_all, None))
        # what comes in from elsewhere, beside what goes out (the user,
        # 2026-10-15: "you somehow removed import excel"). The page inserts
        # here are the same commands as Document ▸ Insert, Before / After
        # alike; the words of the submenu are not repeated (E6).
        import_menu = file_menu.addMenu("Import")
        import_menu.setObjectName("menuImport")
        fill(import_menu, (self.act_insert_pdf, self.act_insert_image_page,
                           self.act_insert_workbook, None, self.act_import_toolset))
        export_menu = file_menu.addMenu("Export")
        export_menu.setObjectName("menuExport")
        fill(export_menu, (self.act_export_pdf, self.act_export_png, self.act_export_markups))
        fill(file_menu, (None, self.act_preview, self.act_print))

        # -- Edit (audit L1) ----------------------------------------------------
        edit_menu = bar.addMenu("&Edit")
        edit_menu.setObjectName("menuEdit")
        fill(edit_menu, (self.act_undo, self.act_redo))
        # Revu's Undo History: what has been done, newest first; choosing one
        # undoes back to before it
        self.undo_history_menu = edit_menu.addMenu("Undo History")
        self.undo_history_menu.setObjectName("menuUndoHistory")
        self.undo_history_menu.aboutToShow.connect(self._fill_undo_history)
        # the clipboard family, then what is done to a markup without
        # changing it — grouped as on a markup's right-click menu (E16, E17)
        fill(edit_menu, (None, self.act_cut, self.act_copy, self.act_paste,
                         self.act_paste_in_place, self.act_paste_here, self.act_duplicate,
                         self.act_offset, self.act_array, self.act_delete, None))
        order_menu = edit_menu.addMenu("Order")
        order_menu.setObjectName("menuOrder")
        fill(order_menu, (self.act_front, self.act_forward, self.act_backward, self.act_back))
        align_menu = edit_menu.addMenu("Alignment")
        align_menu.setObjectName("menuAlignment")
        for key in ("left", "hcenter", "right", "top", "vcenter", "bottom"):
            align_menu.addAction(getattr(self, f"act_align_{key}"))
        fill(edit_menu, (self.act_flatten, self.act_recover_flattened, self.act_lock,
                         self.act_hide, self.act_show_hidden, self.act_group,
                         self.act_ungroup))
        text_menu = edit_menu.addMenu("Text")
        text_menu.setObjectName("menuText")
        fill(text_menu, (self.act_bold, self.act_italic, self.act_underline,
                         self.act_strikethrough, self.act_superscript, self.act_subscript,
                         None,
                         self.act_text_left, self.act_text_center, self.act_text_right,
                         None, self.act_font_increase, self.act_font_decrease))
        # Revu's Pan, Select and Snapshot are on its Edit menu
        fill(edit_menu, (None, self._tool_entry("pan"), self._tool_entry("select"),
                         self.act_select_all, None, self._tool_entry("snapshot"),
                         self.act_format_painter, None))
        # Revu's PDF Content: the redaction box, Whiteout (its Cut and Erase
        # Content), and burning the redactions in
        content = edit_menu.addMenu("PDF Content")
        content.setObjectName("menuPdfContent")
        fill(content, (self._tool_entry("redact"), self._tool_entry("whiteout"), None,
                       self.act_apply_redactions))
        fill(edit_menu, (None, self.act_find_text, self.act_replace_text))
        spelling = edit_menu.addMenu("Check Spelling")
        spelling.addAction(self.act_check_spelling)

        # -- View (audit L5) ----------------------------------------------------
        view_menu = bar.addMenu("&View")
        view_menu.setObjectName("menuView")
        fill(view_menu, (self.act_fit_page, self.act_fit_width, self.act_actual_size,
                         self.act_zoom_in, self.act_zoom_out, self.act_zoom_sel, None,
                         self.act_layout_single, self.act_layout_continuous,
                         self.act_layout_side, self.act_layout_continuous_side,
                         self.act_cover_page, None))
        rotate_menu = view_menu.addMenu("Rotate View")
        rotate_menu.setObjectName("menuRotateView")
        fill(rotate_menu, (self.act_turn_view_cw, self.act_turn_view_acw,
                           self.act_turn_view_reset))
        fill(view_menu, (self.act_split_view, self.act_separate_views, None,
                         self.act_rulers, self.act_crosshair, None,
                         self.act_grid, self.act_snap, self.act_snap_content,
                         self.act_snap_items, self.act_snap_alignment,
                         self.act_snap_pdf_alignment, None, self.act_margins,
                         self.act_name_tags, self.act_dark))
        dimmer_menu = view_menu.addMenu("Dimmer")
        dimmer_menu.addAction(self.act_dim_content)
        dimmer_menu.addSeparator()
        for level in self.dimmer_levels.actions():
            dimmer_menu.addAction(level)
        fill(view_menu, (None, self.act_prev_page, self.act_next_page))

        # -- Document (audit B1): Revu's order, then CalcForge's own -----------
        # Mnemonic on the "D": Revu's Document menu (Alt+P draws freehand).
        page_menu = bar.addMenu("&Document")
        page_menu.setObjectName("menuDocument")
        fill(page_menu, (self.act_doc_props, self.act_page_setup))
        rotate_pages = page_menu.addMenu("Rotate Pages")
        rotate_pages.setObjectName("menuRotatePages")
        fill(rotate_pages, (self.act_rotate_pages_cw, self.act_rotate_pages_acw))
        insert_pages = page_menu.addMenu("Insert")
        insert_pages.setObjectName("menuInsert")
        for entry in self.insert_family():
            insert_pages.addAction(getattr(self, f"act_{entry[0]}"))
        fill(page_menu, (self.act_extract_pages, self.act_split_pages, self.act_delete_page,
                         self.act_crop_page, None, self.act_header_footer, None,
                         self.act_color_processing, None, self.act_flatten_document,
                         self.act_recover_flattened, None))
        # CalcForge's own, together at the end
        self.current_page_menu = page_menu.addMenu("Current Page")
        self.current_page_menu.setObjectName("menuCurrentPage")
        bindable.set_context(self.current_page_menu, "page")
        self.current_page_menu.aboutToShow.connect(self._rebuild_current_page_menu)
        fill(page_menu, (self.act_duplicate_page, self.act_bookmark, self.act_contents))

        batch_menu = bar.addMenu("B&atch")      # Alt+B is Revu's Bookmarks panel
        batch_menu.setObjectName("menuBatch")
        fill(batch_menu, (self.act_export_markups,       # Revu's Summary
                          self.act_flatten_document, self.act_recover_flattened))

        # -- Tools (audit L4) ---------------------------------------------------
        tools_menu = bar.addMenu("T&ools")      # Alt+T is Revu's Thumbnails panel
        tools_menu.setObjectName("menuTools")
        # Every drawing tool, by name: somebody who does not know which button
        # the polygon is under can find it by reading, as in Revu's Tools menu.
        # Pan, Select and Snapshot are on Edit, Redact and Whiteout under Edit
        # ▸ PDF Content, as in Revu.
        on_edit = {"pan", "select", "snapshot", "redact", "whiteout"}
        markup_sub = tools_menu.addMenu("Markup")
        markup_sub.setObjectName("menuMarkup")
        for tool in tools_in("Annotate"):
            markup_sub.addAction(self._tool_entry(tool.key))
        markup_sub.addSeparator()
        for tool in tools_in("Draw"):
            if tool.mode != NONE and tool.key not in on_edit:
                markup_sub.addAction(self._tool_entry(tool.key))
        measure_sub = tools_menu.addMenu("Measure")
        measure_sub.setObjectName("menuMeasure")
        for tool in tools_in("Measure"):
            if tool.mode != NONE:
                measure_sub.addAction(self._tool_entry(tool.key))
        # the page's scale and its viewports, with Calibrate (novice 13)
        fill(measure_sub, (None, self.act_scale, self.act_viewports))
        # Revu's Tools ▸ Sketch to Scale: shapes drawn to a real size
        sketch_sub = tools_menu.addMenu(SKETCH)
        sketch_sub.setObjectName("menuSketchToScale")
        for tool in tools_in(SKETCH):
            sketch_sub.addAction(self._tool_entry(tool.key, under=SKETCH))
        for tool in tools_in("Navigate"):
            if tool.key not in on_edit:
                tools_menu.addAction(self._tool_entry(tool.key))
        tools_menu.addSeparator()
        self.selection_menu = tools_menu.addMenu("Selected Markups")
        bindable.set_context(self.selection_menu, "canvas")
        self.selection_menu.aboutToShow.connect(self._rebuild_selection_menu)
        fill(tools_menu, (self.act_autosize, self.act_sticky, self.act_renumber_counts,
                          self.act_forget_defaults, None))
        chest_menu = tools_menu.addMenu("Tool Chest")      # Revu: Tools ▸ Tool Chest
        chest_menu.setObjectName("menuToolChest")
        chest_menu.addAction(self.act_manage_toolsets)
        # outside File ▸ Import its name is said in full, as on the Tool
        # Chest panel's own menu
        menutidy.proxy(chest_menu, self.act_import_toolset, "Import Tool Set…")
        toolbars_menu = tools_menu.addMenu("Toolbars")
        for toolbar in self.toolbars:
            toolbars_menu.addAction(toolbar.toggleViewAction())
        fill(toolbars_menu, (None, self.act_lock_toolbars, self.act_customise_toolbar))

        # -- Calculation (CalcForge's own) --------------------------------------
        calc_menu = bar.addMenu("&Calculation")
        calc_menu.setObjectName("menuCalculation")
        # Calc mode is the switch on the menu bar (and F12), not a menu entry
        self.addAction(self.act_calc_mode)
        fill(calc_menu, (self.act_calculate, self.act_auto_calc, None,
                         self.act_insert_plot, self.act_insert_matrix,
                         self.act_insert_calc_text, self.act_insert_block,
                         self.act_insert_table, self.act_insert_chart,
                         self.act_insert_function, self.act_insert_operator,
                         self.act_constants))
        on_selection = calc_menu.addMenu("Selection")
        for key in ("solve", "calculate_selection", "invert", "determinant"):
            on_selection.addAction(getattr(self, f"act_{key}"))
        program_menu = calc_menu.addMenu("Program")
        for name in ("if", "for", "while", "line"):
            program_menu.addAction(getattr(self, f"act_prog_{name}"))
        calc_menu.addSeparator()
        calc_menu.addAction(self.act_calc_rules)
        # A spreadsheet's Page Layout, shaped as on its cells' right-click
        # menu and Excel's ribbon: Breaks ▸, Print Area ▸, Sheet Layout…
        # (novice 11: there was no page-break command on the menu bar)
        layout_menu = calc_menu.addMenu("Page Layout")
        layout_menu.setObjectName("menuPageLayout")
        breaks = layout_menu.addMenu("Breaks")
        fill(breaks, (self.act_insert_page_break, self.act_remove_page_break,
                      self.act_reset_page_breaks))
        area = layout_menu.addMenu("Print Area")
        fill(area, (self.act_set_print_area, self.act_clear_print_area))
        fill(layout_menu, (None, self.act_sheet_page_setup))
        layout_menu.aboutToShow.connect(self._refresh_page_layout_menu)
        layout_menu.aboutToHide.connect(self._page_layout_menu_closed)
        fill(calc_menu, (None, self.act_double_check))

        # -- Window (audit L3) --------------------------------------------------
        window_menu = bar.addMenu("&Window")
        window_menu.setObjectName("menuWindow")
        panels_menu = window_menu.addMenu("Panels")
        panels_menu.setObjectName("menuPanels")
        fill(panels_menu, self._build_panel_actions())
        fill(window_menu, (self.act_show_panels, None, self.act_full_screen,
                           self.act_presentation, None, self.act_pin_panels,
                           self.act_reset_layout))

        help_menu = bar.addMenu("&Help")
        help_menu.setObjectName("menuHelp")
        fill(help_menu, (self.act_find_tool, None,
                         self.act_record_slowdowns, self.act_about))

    def _build_status(self) -> None:
        status = CenteredStatusBar()
        self.setStatusBar(status)
        # What is going on and where the pointer is are both things the footer
        # says rather than things it offers, so they sit together on the left.
        # The controls are permanent widgets and gather on the right, and the
        # page navigation goes in the middle of what is left between them.
        # Bluebeam's status bar starts with its toggles, as icons: Show Grid,
        # Snap to Grid, Snap to Content, Snap to Markup, Reuse Markup Tools
        self.status_toggles = QWidget()
        toggles = QHBoxLayout(self.status_toggles)
        toggles.setContentsMargins(2, 0, 6, 0)
        toggles.setSpacing(1)
        self.status_grid = QToolButton()
        self.status_grid.setObjectName("statusShowGrid")
        self.status_grid.setAutoRaise(True)
        self.status_grid.setCheckable(True)
        self.status_grid.setToolTip("Show Grid on this page")
        self.status_grid.toggled.connect(
            lambda on: self.set_page_grid(self.current_index, on))
        toggles.addWidget(self.status_grid)
        self._status_icon_buttons = {self.status_grid: "show_grid"}
        for action, name in ((self.act_snap, "snap_grid"), (self.act_snap_content, "snap_content"),
                             (self.act_snap_items, "snap_markup"), (self.act_sticky, "reuse")):
            button = QToolButton()
            button.setAutoRaise(True)
            button.setDefaultAction(action)
            button.setToolButtonStyle(Qt.ToolButtonIconOnly)
            toggles.addWidget(button)
            self._icon_names[action] = name       # re-tinted with the theme
            action.setIcon(icon(name))
        self._refresh_status_icons()
        status.addWidget(self.status_toggles)

        # what is going on, cut short with "…" when the bar has no room for
        # all of it (the tooltip has the rest)
        self.status_hint = ElidedLabel("Ready")
        self.status_hint.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.status_hint.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.status_hint.setMinimumWidth(0)
        status.addWidget(self.status_hint)
        # a hovered command's tip, over the free room of the bar's left half
        # (never over its buttons) while the pointer is on the command
        self.status_tip = ElidedLabel("", status)
        self.status_tip.setObjectName("statusTip")
        self.status_tip.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.status_tip.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.status_tip.setAutoFillBackground(True)
        self.status_tip.setBackgroundRole(status.backgroundRole())
        self.status_tip.hide()

        self.status_position = QLabel("")
        self.status_position.setMinimumWidth(150)
        status.addWidget(self.status_position)


        self.status_dimmer = QToolButton()
        self.status_dimmer.setObjectName("statusDimmer")
        self.status_dimmer.setAutoRaise(True)
        self.status_dimmer.setDefaultAction(self.act_dim_content)
        self.status_dimmer.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self._icon_names[self.act_dim_content] = "dimmer"
        self.act_dim_content.setIcon(icon("dimmer"))
        status.addPermanentWidget(self.status_dimmer)

        self.status_scale = QToolButton()
        self.status_scale.setText("Scale Not Set")
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

        # Bluebeam's: |◀ ◀ [ 2 of 3 ] ▶ ▶|
        self.page_first = QToolButton()
        self.page_first.setAutoRaise(True)
        self.page_first.setToolTip("First Page")
        self.page_first.clicked.connect(lambda: self.go_to_page(0))
        page_bar.addWidget(self.page_first)
        self.page_back = QToolButton()
        self.page_back.setAutoRaise(True)
        self.page_back.setToolTip("Previous Page")
        self.page_back.clicked.connect(lambda: self.go_to_page(self.current_index - 1))
        page_bar.addWidget(self.page_back)

        self.page_spin = QSpinBox()
        self.page_spin.setObjectName("pageNumber")
        self.page_spin.setRange(1, 1)
        self.page_spin.setSuffix(" of 1")
        self.page_spin.setButtonSymbols(QSpinBox.NoButtons)
        self.page_spin.setMinimumWidth(110)
        self.page_spin.lineEdit().setAlignment(Qt.AlignCenter)
        self.page_spin.valueChanged.connect(lambda value: self.go_to_page(value - 1))
        page_bar.addWidget(self.page_spin)

        self.page_total = QLabel("of 1")
        self.page_total.setVisible(False)        # said in the page box, as Bluebeam's
        page_bar.addWidget(self.page_total)

        self.page_label = QLabel("")
        self.page_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.page_label.setMaximumWidth(180)
        self.page_label.setAlignment(Qt.AlignCenter)
        self.page_label.setToolTip("Current page label")
        page_bar.addWidget(self.page_label)

        self.page_forward = QToolButton()
        self.page_forward.setAutoRaise(True)
        self.page_forward.setToolTip("Next Page")
        self.page_forward.clicked.connect(lambda: self.go_to_page(self.current_index + 1))
        page_bar.addWidget(self.page_forward)
        self.page_last = QToolButton()
        self.page_last.setAutoRaise(True)
        self.page_last.setToolTip("Last Page")
        self.page_last.clicked.connect(lambda: self.go_to_page(len(self.document.pages) - 1))
        page_bar.addWidget(self.page_last)
        for button, name in ((self.page_first, "nav_first"), (self.page_back, "nav_prev"),
                             (self.page_forward, "nav_next"), (self.page_last, "nav_last")):
            self._status_icon_buttons[button] = name
        self._refresh_status_icons()
        status.set_center_widget(self.page_navigation)
        # centred on the page view: follow it as panels open, close and resize
        self._page_bar_follower = _SizeFollower(self._center_page_bar, self)
        for watched in (self.view, self.view.viewport(), status, self.page_navigation):
            watched.installEventFilter(self._page_bar_follower)

        self.status_fit = QToolButton()
        self.status_fit.setAutoRaise(True)
        self.status_fit.setText("Fit Width")
        self.status_fit.setToolTip("Fit the page across the window")
        self.status_fit.clicked.connect(lambda: self.view.fit_width())
        status.addPermanentWidget(self.status_fit)

        self.status_scroll = QToolButton()
        self.status_scroll.setAutoRaise(True)
        self.status_scroll.setText("Continuous")
        self.status_scroll.setToolTip("Page layout: Single Page, Continuous, Side-by-Side "
                                      "or Continuous Side-by-Side")
        scroll_menu = QMenu(self.status_scroll)
        for action in (self.act_layout_single, self.act_layout_continuous, self.act_layout_side,
                       self.act_layout_continuous_side, None, self.act_cover_page):
            scroll_menu.addSeparator() if action is None else scroll_menu.addAction(action)
        self.status_scroll.setMenu(scroll_menu)
        self.status_scroll.setPopupMode(QToolButton.InstantPopup)
        status.addPermanentWidget(self.status_scroll)

        self.status_snap = QToolButton()
        self.status_snap.setAutoRaise(True)
        self.status_snap.setText("Snap")
        self.status_snap.setToolTip("Choose what drawing points snap to")
        snap_menu = QMenu(self.status_snap)
        for action in (self.act_snap, self.act_snap_items,
                       self.act_snap_content, self.act_snap_alignment,
                       self.act_snap_pdf_alignment):
            snap_menu.addAction(action)
        self.status_snap.setMenu(snap_menu)
        self.status_snap.setPopupMode(QToolButton.InstantPopup)
        status.addPermanentWidget(self.status_snap)

        self.window_sync = QComboBox()
        self.window_sync.setObjectName("windowSync")
        self.window_sync.addItems(["Sync off", "Page sync", "Document sync"])
        self.window_sync.currentIndexChanged.connect(self._set_window_sync)
        self.window_sync.setToolTip(
            "Link this view with other windows showing the same document")

        # as wide as what it says now, not as its longest choice: the status
        # bar's room is what lets the page number sit under the page's middle
        def fit_the_sync(_text="") -> None:
            box = self.window_sync
            box.setFixedWidth(box.fontMetrics().horizontalAdvance(box.currentText()) + 34)
        self.window_sync.currentTextChanged.connect(fit_the_sync)
        fit_the_sync()
        status.addPermanentWidget(self.window_sync)

        self.status_size = QToolButton()
        self.status_size.setAutoRaise(True)
        self.status_size.setToolTip("The paper and its margins — click to change them")
        self.status_size.clicked.connect(self.page_setup)
        status.addPermanentWidget(self.status_size)

        self.zoom_combo = QComboBox()
        self.zoom_combo.setEditable(True)
        self.zoom_combo.addItems(["25%", "50%", "75%", "100%", "125%", "150%", "200%",
                                  "400%", "Fit Page", "Fit Width"])
        self.zoom_combo.setCurrentText("100%")
        self.zoom_combo.activated.connect(self._zoom_chosen)
        status.addPermanentWidget(self.zoom_combo)

        # What the footer drops as the window narrows, the least missed first:
        # the pointer's coordinates, then the paper size, Sync, Snap and the
        # page layout, as Revu's own footer does (QA, 2026-10-15). The page
        # navigation and the zoom box always stay. Whatever is dropped is on
        # the » menu beside the zoom box until there is room for it again.
        self.status_more = QToolButton()
        self.status_more.setObjectName("statusMore")
        self.status_more.setAutoRaise(True)
        self.status_more.setText("»")
        self.status_more.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self._status_icon_buttons[self.status_more] = "overflow"
        self.status_more.setToolTip("The status bar controls there is no room for")
        self.status_more.setPopupMode(QToolButton.InstantPopup)
        more_menu = bindable.data_menu(QMenu(self.status_more))
        more_menu.aboutToShow.connect(lambda: self._fill_status_overflow(more_menu))
        self.status_more.setMenu(more_menu)
        status.addPermanentWidget(self.status_more)
        self._refresh_status_icons()
        # the status bar's buttons, each the command it is a shortcut to, or a
        # command of its own, in Keyboard Shortcuts (bindable.py)
        for button, command_id in (
                (self.status_grid, "page.page_grid"), (self.status_scale, "command.scale"),
                (self.status_fit, "command.fit_width"), (self.status_size, "command.page_setup"),
                (self.page_back, "command.prev_page"), (self.page_forward, "command.next_page"),
                (self.page_first, "status.first_page"), (self.page_last, "status.last_page")):
            self.commands.bind_button(button, command_id)
        status.set_droppable([self.status_position, self.status_size, self.window_sync,
                              self.status_snap, self.status_scroll, self.status_fit,
                              self.status_scale, self.status_dimmer, self.status_toggles],
                             self.status_more)

    def _fill_status_overflow(self, menu: QMenu) -> None:
        """The » menu: the status bar's dropped controls, each doing what it
        does on the bar."""
        menu.clear()
        status = self.statusBar()
        dropped = status.dropped() if isinstance(status, CenteredStatusBar) else []
        for widget in dropped:
            if widget is self.status_position:
                text = self.status_position.text() or "—"
                menu.addAction(f"Pointer: {text}").setEnabled(False)
            elif widget is self.status_size:
                menu.addAction(f"Page Setup ({self.status_size.text()})…", self.page_setup)
            elif widget is self.window_sync:
                sync = menu.addMenu("Window Sync")
                for index in range(self.window_sync.count()):
                    action = sync.addAction(self.window_sync.itemText(index))
                    action.setCheckable(True)
                    action.setChecked(index == self.window_sync.currentIndex())
                    action.triggered.connect(
                        lambda _on=False, i=index: self.window_sync.setCurrentIndex(i))
            elif widget in (self.status_snap, self.status_scroll):
                sub = menu.addMenu(widget.text())
                for action in widget.menu().actions():
                    sub.addAction(action)
            elif widget is self.status_fit:
                menu.addAction("Fit Width", self.view.fit_width)
            elif widget is self.status_scale:
                menu.addAction(f"{self.status_scale.text()}…", self.calibrate_dialog)
            elif widget is self.status_dimmer:
                menu.addAction(self.act_dim_content)
            elif widget is self.status_toggles:
                menu.addSeparator()
                grid = menu.addAction("Show Grid")
                grid.setCheckable(True)
                grid.setChecked(self.status_grid.isChecked())
                grid.triggered.connect(self.status_grid.setChecked)
                for action in (self.act_snap, self.act_snap_content, self.act_snap_items,
                               self.act_sticky):
                    menu.addAction(action)

    def _wire_view(self, view) -> None:
        """The window listens to a view of its own — only while it is the
        view being worked in, when the window is split in two."""
        def active(slot):
            return lambda *args: slot(*args) if self.view is view else None

        view.statusMessage.connect(active(self.status_hint.setText))
        view.cursorMoved.connect(active(self._show_position))
        view.zoomChanged.connect(active(self._show_zoom))
        view.zoomChanged.connect(active(lambda _zoom: self._sync_other_windows(True)))
        view.selectionChanged.connect(active(self._selection_changed_on_the_canvas))
        view.toolFinished.connect(active(self.select_tool))
        view.documentEdited.connect(active(self.mark_modified))
        view.pageChanged.connect(active(self.follow_scrolled_page))
        view.horizontalScrollBar().valueChanged.connect(
            active(lambda _value: self._sync_other_windows(False)))
        view.verticalScrollBar().valueChanged.connect(
            active(lambda _value: self._sync_other_windows(False)))

    def _connect(self) -> None:
        self._wire_view(self.view)
        # Tool keys have to fall silent while somebody is typing, and a
        # shortcut fires before the key ever reaches the editor — so they are
        # headed off at the one point that sees every keystroke.
        application = QApplication.instance()
        if application is not None:
            application.installEventFilter(self)
            self._filters_the_application = True     # (PropertiesPanel.show_items)
        self.pages_panel.pageSelected.connect(self.go_to_page)
        # (first page, how many, where the run now starts) — move_page takes
        # the last two the other way round
        self.pages_panel.pagesReordered.connect(
            lambda first, count, target: self.move_page(first, target, count))
        self.markups_panel.markupActivated.connect(self.reveal_markup)
        self.markups_panel.markupPicked.connect(self.pick_markup)
        self.markups_panel.markupsPicked.connect(self.pick_markups)
        self._connect_undo_stack(self.undo_stack)

    def shown_states(self):
        """(document, scene, undo stack) of every tab and view this window
        shows, or nothing once it is closed for good."""
        if getattr(self, "_closed_for_good", True):
            return
        yield self.document, self.scene, self.undo_stack
        active = getattr(self, "_active_pane", None)
        for pane in getattr(self, "_panes", ()):
            if pane is active:
                for index, state in enumerate(self._open_documents):
                    if index != self._active_tab:      # (its live state is above)
                        yield state["document"], state["scene"], state["undo_stack"]
            else:
                for state in pane.documents:
                    yield state["document"], state["scene"], state["undo_stack"]
                yield None, pane.view.scene(), None

    def _let_go(self) -> None:
        """Release every canvas, history and document no window shows now
        (ui/release.py): a closed tab, a replaced document, a split turned
        off."""
        import shiboken6
        from . import release
        windows = [w for w in type(self)._windows if shiboken6.isValid(w)]
        if self not in windows and shiboken6.isValid(self):
            windows.append(self)
        showing = [w for w in windows if not getattr(w, "_closed_for_good", True)]
        for window in showing:
            # the tab in view is kept as what it shows now, not as what it
            # showed when it was last left: a document New or Open replaced
            # there is not still held by its tab
            here = window._active_tab
            if 0 <= here < len(window._open_documents):
                window._open_documents[here] = window._current_document_state()
        release.let_go(showing, windows)
        # a gesture's "before" taken on a page that has now gone
        for window in showing:
            for pane in window._panes:
                view = pane.view
                if not shiboken6.isValid(view) or not view._snapshot:
                    continue
                view._snapshot = [(frame, items) for frame, items in view._snapshot
                                  if shiboken6.isValid(frame) and frame.scene() is not None]

    def _connect_undo_stack(self, stack) -> None:
        """Connect this window once, without disturbing another shared view."""
        if any(stack is seen for seen in self._connected_undo_stacks):
            return
        stack.cleanChanged.connect(self._undo_clean_slot)
        # Undo and Redo are greyed and lit by whichever history is in hand;
        # only the window's first one used to tell them (QA F-02)
        stack.canUndoChanged.connect(self._refresh_undo_actions)
        stack.canRedoChanged.connect(self._refresh_undo_actions)
        self._connected_undo_stacks.append(stack)

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
                "tool": tool or self.view.tool_key,
                "zoom": self.view.zoom(),
                "hscroll": self.view.horizontalScrollBar().value(),
                "vscroll": self.view.verticalScrollBar().value()}

    def _adopt_document_state(self, state: dict) -> None:
        initial_fit = getattr(self, "_initial_fit", None)
        if initial_fit is not None:
            initial_fit.stop()
        self.document = state["document"]
        self.scene = state["scene"]
        self.undo_stack = state["undo_stack"]
        # Shared views may outlive the window that first created this stack.
        self.undo_stack.setParent(None)
        self._connect_undo_stack(self.undo_stack)
        self.current_index = state["index"]
        if self.scene is not None:
            self.view.setScene(self.scene)
        self.rebuild_scenes()
        self.view.set_zoom(float(state.get("zoom", self.view.zoom())))
        self.view.horizontalScrollBar().setValue(int(state.get("hscroll", 0)))
        self.view.verticalScrollBar().setValue(int(state.get("vscroll", 0)))
        self.select_tool(state.get("tool") or "select")
        self.refresh_lists()
        self.update_title()
        self._refresh_undo_actions()
        self._show_page_layout()

        mode = next((other.window_sync.currentIndex() for other in type(self)._windows
                     if other is not self and other.document is self.document), 0)
        self.window_sync.blockSignals(True)
        self.window_sync.setCurrentIndex(mode)
        self.window_sync.blockSignals(False)

    def _tab_title(self, document) -> str:
        return os.path.basename(document.path) if document.path else "Untitled"

    def open_in_new_tab(self, document=None) -> int:
        """Put another document beside this one, with a tab of its own —
        or, from the empty workspace, in place of the blank one behind it."""
        if self._workspace_empty:
            if document is None:
                self.new_document(confirm=False)
                self._open_documents[self._active_tab] = self._current_document_state()
                return self._active_tab
            self.show_empty_workspace(False)
            where = self.open_in_new_tab(document)
            placeholder = 0 if where > 0 else 1
            self._open_documents.pop(placeholder)
            self.document_tabs.blockSignals(True)
            self.document_tabs.removeTab(placeholder)
            self._active_tab = self.document_tabs.currentIndex()
            self.document_tabs.blockSignals(False)
            return self._active_tab
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
        same_document = document is self.document
        stack = self.undo_stack if same_document else QUndoStack(self)
        if not same_document:
            from . import release
            release.STACKS.add(stack)
            self._connect_undo_stack(stack)
        fresh = {"document": document if document is not None else Document(),
                 "scene": self.scene if same_document else None,
                 "undo_stack": stack,
                 "index": self.current_index if same_document else 0,
                 "tool": held if same_document else "select",
                 "zoom": self.view.zoom(),
                 "hscroll": self.view.horizontalScrollBar().value(),
                 "vscroll": self.view.verticalScrollBar().value()}
        self._open_documents.append(fresh)
        self.document_tabs.blockSignals(True)
        where = self.document_tabs.addTab(self._tab_title(fresh["document"]))
        self.document_tabs.setCurrentIndex(where)
        self.document_tabs.blockSignals(False)
        self.document_tabs.setVisible(True)
        self._active_tab = where
        self._adopt_document_state(fresh)
        return where

    def open_same_document_tab(self, index: Optional[int] = None) -> int:
        """Open another independently positioned view of a document."""
        if index is not None and 0 <= index < len(self._open_documents):
            self.switch_to_document(index)
        return self.open_in_new_tab(self.document)

    def _tab_context_menu(self, point: QPoint, menu=None):
        """Commands belonging to the document under the pointer."""
        index = self.document_tabs.tabAt(point)
        if index < 0:
            return None
        from . import menutidy
        supplied = menu is not None
        menu = bindable.set_context(menu or QMenu(self.document_tabs), "doctab")
        # Revu's tab menu (QA round 4): Close, Close All, Close Others | Save,
        # Save As… | New Window, Split | and CalcForge's Duplicate Tab. Each
        # acts on the tab clicked, which is brought forward first where the
        # command works on the document in view.
        active = index == self._active_tab

        def on_tab(action):
            def run(_checked=False):
                self.switch_to_document(index)
                action.trigger()
            return run
        close = menu.addAction("Close", lambda: self.close_document_tab(index))
        if active:
            close.setShortcut(self.act_close_tab.shortcut())
            close.setShortcutContext(Qt.WidgetShortcut)
        menu.addAction(self.act_close_all)
        others = menu.addAction("Close Others", lambda: self.close_other_documents(index))
        others.setEnabled(len(self._open_documents) > 1)
        menu.addSeparator()
        for action in (self.act_save, self.act_save_as):
            entry = menu.addAction(action.text(), on_tab(action))
            entry.setShortcut(action.shortcut())
            entry.setShortcutContext(Qt.WidgetShortcut)
        menu.addSeparator()
        window = menu.addAction("New Window", lambda: self.open_same_document_window(index))
        window.setToolTip("Show this document in a window of its own as well")
        split = menu.addAction("Open in Split View", lambda: self.split_document(index))
        split.setToolTip("Show this document beside the one in view, in a split window")
        duplicate = menu.addAction("Duplicate Tab", lambda: self.open_same_document_tab(index))
        duplicate.setToolTip("Another tab on the same document, with a view of its own")
        menutidy.tidy(menu)
        if not supplied:
            menu.exec(self.document_tabs.mapToGlobal(point))
        return menu

    def close_other_documents(self, keep: int) -> None:
        """Close every tab but *keep*, each asking about unsaved changes; a
        Cancel stops there."""
        for index in range(len(self._open_documents) - 1, -1, -1):
            if index == keep:
                continue
            count = len(self._open_documents)
            self.close_document_tab(index)
            if len(self._open_documents) == count:
                return                                 # Cancel kept it
            if index < keep:
                keep -= 1

    def open_same_document_window(self, index: Optional[int] = None) -> "MainWindow":
        """Show this document in another window without copying its contents."""
        state = self._state_for_tab(index)
        window = self.open_new_window()
        window._adopt_document_state(dict(state))
        return window

    @_moves_documents
    def tear_off_document(self, index: int, global_point: QPoint = QPoint()) -> None:
        """Move a tab into a new independent application window."""
        if not (0 <= index < len(self._open_documents)):
            return
        pane = self.other_pane()
        if pane is not None and not global_point.isNull():
            # onto the other pane of the split: its tab bar or its canvas
            bar = pane.tabs
            if bar.rect().contains(bar.mapFromGlobal(global_point)):
                self.move_document_to_pane(index, pane,
                                           bar.tabAt(bar.mapFromGlobal(global_point)))
                return
            if pane.widget.rect().contains(pane.widget.mapFromGlobal(global_point)):
                self.move_document_to_pane(index, pane)
                return
        for other in type(self)._windows:
            if other is self or not other.isVisible():
                continue
            bar = other.document_tabs
            if bar.isVisible() and bar.rect().contains(bar.mapFromGlobal(global_point)):
                self.move_document_to(index, other, bar.tabAt(bar.mapFromGlobal(global_point)))
                return
        state = self._state_for_tab(index)
        window = self.open_new_window()
        window._adopt_document_state(dict(state))
        if not global_point.isNull():
            window.move(global_point)
        self.close_document_tab(index, moving=True)
        if all(state["undo_stack"] is not held["undo_stack"]
               for held in self._open_documents):
            state["undo_stack"].setParent(window)

    @_moves_documents
    def move_document_to(self, index, target, before=-1):
        """Move the live document, viewport and undo history between windows."""
        if target is self or not 0 <= index < len(self._open_documents):
            return
        state = dict(self._state_for_tab(index))
        # A document the target already shows is not opened a second time:
        # its tab comes forward (as when Revu's split panes swap a file).
        showing = next((i for i, held in enumerate(target._open_documents)
                        if held["document"] is state["document"]), -1)
        if showing < 0 and not target._open_documents and target.document is state["document"]:
            showing = 0
        if showing >= 0:
            if target._open_documents:
                target.switch_to_document(showing)
        else:
            destination = target.open_in_new_tab()
            target._open_documents[destination] = state
            target._adopt_document_state(state)
            target.document_tabs.setTabText(destination, target._tab_title(state["document"]))
            if before >= 0:
                target.document_tabs.moveTab(destination, before)
        self.close_document_tab(index, moving=True)
        if all(held["undo_stack"] is not state["undo_stack"] for held in self._open_documents):
            state["undo_stack"].setParent(target)

    def _state_for_tab(self, index=None):
        if index is None or index == self._active_tab:
            return self._current_document_state()
        return self._open_documents[index]

    def _tab_moved(self, before: int, after: int) -> None:
        if 0 <= before < len(self._open_documents):
            self._open_documents.insert(after, self._open_documents.pop(before))
            if self._active_tab == before:
                self._active_tab = after
            elif before < self._active_tab <= after:
                self._active_tab -= 1
            elif after <= self._active_tab < before:
                self._active_tab += 1

    # -- Split View: two panes in one window (ViewPane) ----------------------
    @property
    def is_split(self) -> bool:
        return len(self._panes) > 1

    def other_pane(self) -> Optional[ViewPane]:
        return next((pane for pane in self._panes if pane is not self._active_pane), None)

    def pane_of(self, widget) -> Optional[ViewPane]:
        """The pane *widget* is in, if it is in one."""
        for pane in self._panes:
            if widget is pane.widget or pane.widget.isAncestorOf(widget):
                return pane
        return None

    def split_document(self, index=None) -> ViewPane:
        """View ▸ Split View: a second pane beside this one, in this window.

        Splitting an inactive tab puts that document beside the current one;
        splitting the current document opens another view of the same pages.
        Only a view and a tab bar are made, so it is immediate (a whole second
        window took 3.8 s, QA 2026-10-16).
        """
        if self.is_split:
            return self.other_pane()
        state = dict(self._state_for_tab(index))
        state["tool"] = "select"
        view = PageView(self)
        view.use_the_graphics_card(self.view.gpu)
        from .sheettabs import SheetTabs
        sheet_tabs = SheetTabs(self)
        view.addScrollBarWidget(sheet_tabs, Qt.AlignLeft)
        tabs = self._make_document_tabs()
        tabs.addTab(self._tab_title(state["document"]))
        pane = self._make_pane(view, tabs, sheet_tabs)
        pane.documents = [state]
        pane.active = 0
        view.tables.bar = self.formula_bar
        self._wire_view(view)
        styles = getattr(self, "markup_styles", None)
        if styles is not None:
            view.toolChanged.connect(
                lambda key, v=view: styles._tool_changed(key) if self.view is v else None)
            view.markupStyleChanged.connect(
                lambda n, v=view: styles._style_changed(n) if self.view is v else None)
            view.selectionChanged.connect(
                lambda v=view: styles._selection_changed() if self.view is v else None)
        self._panes.append(pane)
        view.rulers.show(self.act_rulers.isChecked())
        view.crosshair.show(self.act_crosshair.isChecked())
        half = max(1, self.view_split.width() // 2)
        self.view_split.setSizes([half, half])
        self._check_split_action(True)
        self.activate_pane(pane)
        view.setFocus(Qt.OtherFocusReason)
        return pane

    def _check_split_action(self, on: bool) -> None:
        self.act_split_view.blockSignals(True)
        self.act_split_view.setChecked(on)
        self.act_split_view.blockSignals(False)

    def activate_pane(self, pane: ViewPane) -> None:
        """Make *pane* the one the menus, toolbars and panels act on."""
        if pane is self._active_pane or pane not in self._panes \
                or getattr(self, "_activating", False):
            return
        self._activating = True
        try:
            self._activate_pane(pane)
        finally:
            self._activating = False

    def _activate_pane(self, pane: ViewPane) -> None:
        leaving = self._active_pane
        held = self.view.tool_key
        self.view.escape_everything()
        if 0 <= self._active_tab < len(self._open_documents):
            self._open_documents[self._active_tab] = self._current_document_state(held)
        leaving.documents = self._open_documents
        leaving.active = self._active_tab
        self._active_pane = pane
        self.view = pane.view
        self.document_tabs = pane.tabs
        self.sheet_tabs = pane.sheet_tabs
        self._open_documents = pane.documents
        self._active_tab = pane.active
        shown = not self.formula_bar.isHidden()
        pane.layout.insertWidget(pane.layout.indexOf(pane.tabs) + 1, self.formula_bar)
        self.formula_bar.setVisible(shown)
        self.formula_bar.tables = pane.view.tables
        if 0 <= self._active_tab < len(self._open_documents):
            state = self._open_documents[self._active_tab]
            # the view may have been scrolled or zoomed (the wheel, Window
            # Sync) while it was not the one in hand: it is where it is
            view = pane.view
            if view.scene() is state["scene"] and state["scene"] is not None:
                state["zoom"] = view.zoom()
                state["hscroll"] = view.horizontalScrollBar().value()
                state["vscroll"] = view.verticalScrollBar().value()
                state["index"] = view.visible_page_index()
            self._adopt_document_state(state)
        self._show_zoom(self.view.zoom())
        self.sheet_tabs.refresh()
        self._mark_active_pane()

    def unsplit(self, keep: Optional[ViewPane] = None, carry_over: bool = True) -> None:
        """Turn the split off: *keep* (the pane being worked in) stays.

        With *carry_over*, any document the other pane held that *keep* has
        not got moves across as a tab, so turning the split off never closes
        somebody's work.
        """
        if not self.is_split:
            return
        keep = keep if keep in self._panes else self._active_pane
        self.activate_pane(keep)
        leaving = self.other_pane()
        if carry_over:
            here = self._active_tab
            if 0 <= here < len(self._open_documents):
                # what the tab shows now (New or Open may have replaced it)
                self._open_documents[here] = self._current_document_state()
            held = {id(state["document"]) for state in self._open_documents}
            for state in leaving.documents:
                if id(state["document"]) in held:
                    continue
                held.add(id(state["document"]))
                self.add_tab_for_state(state)
            self.switch_to_document(here)
        self._panes.remove(leaving)
        leaving.view.escape_everything()
        leaving.view.setScene(None)
        leaving.widget.setParent(None)
        leaving.widget.deleteLater()
        leaving.documents = []
        self._mark_active_pane()
        self._check_split_action(False)
        self.view.setFocus(Qt.OtherFocusReason)

    def toggle_split_view(self, on: bool = True):
        """Split this window in two, or turn an existing split off."""
        if self.is_split:
            self.unsplit()
            self._let_go()
            return None
        return self.split_document()

    @_moves_documents
    def separate_views(self) -> Optional["MainWindow"]:
        """Window ▸ Separate Views: the other pane becomes a window of its
        own, with its own menus."""
        if not self.is_split:
            return None
        states = list(self.other_pane().documents)
        self.unsplit(carry_over=False)
        window = self.open_new_window()
        window.interactive_prompts = self.interactive_prompts
        for number, state in enumerate(states):
            if number == 0:
                window._open_documents[0] = dict(state)
                window._adopt_document_state(dict(state))
                window.document_tabs.setTabText(0, window._tab_title(state["document"]))
            else:
                window.add_tab_for_state(state)
            if all(state["undo_stack"] is not held["undo_stack"]
                   for held in self._open_documents):
                state["undo_stack"].setParent(window)
        return window

    def add_tab_for_state(self, state: dict, before: int = -1) -> int:
        """Show a document already open somewhere (its canvas, history and
        place) in a new tab of this pane."""
        held = self.view.tool_key
        self.view.escape_everything()
        if 0 <= self._active_tab < len(self._open_documents):
            self._open_documents[self._active_tab] = self._current_document_state(held)
        state = dict(state)
        self._connect_undo_stack(state["undo_stack"])
        self._open_documents.append(state)
        self.document_tabs.blockSignals(True)
        where = self.document_tabs.addTab(self._tab_title(state["document"]))
        if 0 <= before < where:
            self.document_tabs.moveTab(where, before)
            self._open_documents.insert(before, self._open_documents.pop(where))
            where = before
        self.document_tabs.setCurrentIndex(where)
        self.document_tabs.blockSignals(False)
        self._active_tab = where
        self._adopt_document_state(state)
        return where

    @_moves_documents
    def move_document_to_pane(self, index: int, pane: ViewPane, before: int = -1) -> None:
        """A tab dragged onto the other pane: its document goes there."""
        if pane is self._active_pane or pane not in self._panes \
                or not 0 <= index < len(self._open_documents):
            return
        state = dict(self._state_for_tab(index))
        showing = next((i for i, held in enumerate(pane.documents)
                        if held["document"] is state["document"]), -1)
        if len(self._open_documents) == 1:
            # the pane's last tab going is the split going
            self.unsplit(keep=pane, carry_over=False)
        else:
            self.close_document_tab(index, moving=True)
            self.activate_pane(pane)
        if showing >= 0:
            self.switch_to_document(showing)
        else:
            self.add_tab_for_state(state, before)
        self.view.setFocus(Qt.OtherFocusReason)

    def switch_to_document(self, index: int) -> None:
        """Store the view by tab identity, even when two tabs share a PDF."""
        if not (0 <= index < len(self._open_documents)) or index == self._active_tab:
            return
        held = self.view.tool_key
        self.view.escape_everything()
        if 0 <= self._active_tab < len(self._open_documents):
            self._open_documents[self._active_tab] = self._current_document_state(held)
        self._active_tab = index
        self.document_tabs.blockSignals(True)
        self.document_tabs.setCurrentIndex(index)
        self.document_tabs.blockSignals(False)
        self._adopt_document_state(self._open_documents[index])

    # -- the empty workspace (novice 24) ---------------------------------------------
    #: What still works with no document open, as in Revu: making or opening
    #: one, the window and its panels, the application's own settings.
    WORKSPACE_COMMANDS = {
        "new", "new_tab", "new_window", "open", "quit", "preferences", "shortcuts",
        "about", "find_tool", "record_slowdowns", "full_screen", "dark", "show_panels",
        "pin_panels", "reset_layout", "lock_toolbars", "customise_toolbar",
        "import_toolset", "manage_toolsets", "close_all", "markups_list",
    }

    def _build_empty_workspace(self) -> QWidget:
        from PySide6.QtWidgets import QPushButton
        space = QWidget()
        space.setObjectName("emptyWorkspace")
        outer = QVBoxLayout(space)
        outer.addStretch(1)
        said = QLabel("No document is open")
        said.setObjectName("emptyWorkspaceTitle")
        said.setAlignment(Qt.AlignCenter)
        font = said.font()
        font.setPointSizeF(font.pointSizeF() * 1.4)
        said.setFont(font)
        outer.addWidget(said)
        hint = QLabel("File ▸ New PDF (Ctrl+N) or File ▸ Open… (Ctrl+O)")
        hint.setAlignment(Qt.AlignCenter)
        outer.addWidget(hint)
        row = QHBoxLayout()
        row.addStretch(1)
        for text, key in (("New PDF", "new"), ("Open…", "open")):
            button = QPushButton(text)
            button.setObjectName(f"emptyWorkspace_{key}")
            button.clicked.connect(lambda _c=False, k=key: getattr(self, f"act_{k}").trigger())
            row.addWidget(button)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(2)
        return space

    @property
    def workspace_empty(self) -> bool:
        return self._workspace_empty

    def show_empty_workspace(self, empty: bool) -> None:
        """No document in view: the canvas, its tab and the commands that need
        a document go, and the window says how to get one (Revu). A document
        made or opened brings everything back."""
        if empty == self._workspace_empty:
            return
        self._workspace_empty = empty
        self.view.escape_everything()
        for widget in (self.bottom_split, self.document_tabs):
            widget.setVisible(not empty)
        if empty:
            self.formula_bar.hide()
        self.empty_workspace.setVisible(empty)
        # the panels and the footer say nothing about a document that is not
        # there: the blank one behind the workspace is not shown in them
        # (the Tool Chest is the application's, not the document's)
        for dock in self.panels:
            if dock is not self.dock_toolsets and dock.widget() is not None:
                dock.widget().setEnabled(not empty)
        # the blank page's thumbnail is not shown (the list keeps its place)
        self.pages_panel.list.viewport().setVisible(not empty)
        self.statusBar().setEnabled(not empty)
        actions = [(name[4:], getattr(self, name)) for name in dir(self)
                   if name.startswith("act_") and isinstance(getattr(self, name), QAction)]
        actions += [(f"tool.{key}", action) for key, action in self.tool_actions.items()]
        actions += [(f"menu.{key}.{i}", action)
                    for key, entries in self.insert_tool_actions.items()
                    for i, action in enumerate(entries)]
        if empty:
            self._enabled_before_empty = {}
            for key, action in actions:
                if key in self.WORKSPACE_COMMANDS or key.startswith("panel_"):
                    continue
                self._enabled_before_empty[key] = action.isEnabled()
                action.setEnabled(False)
        else:
            for key, action in actions:
                if key in self._enabled_before_empty:
                    action.setEnabled(self._enabled_before_empty[key])
            self._enabled_before_empty = {}
            self._refresh_undo_actions()
        self.update_title()

    def close_document_tab(self, index: int, moving: bool = False) -> None:
        """Closing a view must not silently discard its document's edits."""
        if not (0 <= index < len(self._open_documents)):
            return
        target = self._state_for_tab(index)
        shared = any(state["document"] is target["document"]
                     for i, state in enumerate(self._open_documents) if i != index)
        other = self.other_pane()
        if other is not None and target["document"] in other.documents_held():
            shared = True
        if not moving and not shared:
            previous = self._active_tab
            self.switch_to_document(index)
            if not self.confirm_discard():
                self.switch_to_document(previous)
                return
            self.switch_to_document(previous)
        if len(self._open_documents) == 1 and other is not None:
            # The pane's last tab going (closed, or dragged away) is the split
            # going: the other pane carries on as the window's one view.
            self.unsplit(keep=other, carry_over=False)
            if not moving:
                self._let_go()
            return
        if len(self._open_documents) == 1:
            # Revu leaves an empty workspace, not an "Untitled" document
            # (novice 24): a blank document stands behind it, out of sight,
            # until one is made or opened
            self.new_document(confirm=False)
            self._open_documents[0] = self._current_document_state()
            self.show_empty_workspace(True)
            return
        if 0 <= self._active_tab < len(self._open_documents):
            self._open_documents[self._active_tab] = self._current_document_state()
        was_active = index == self._active_tab
        self._open_documents.pop(index)
        self.document_tabs.blockSignals(True)
        self.document_tabs.removeTab(index)
        if was_active:
            self._active_tab = min(index, len(self._open_documents) - 1)
        elif index < self._active_tab:
            self._active_tab -= 1
        self.document_tabs.setCurrentIndex(self._active_tab)
        self.document_tabs.blockSignals(False)
        self.document_tabs.setVisible(True)
        if was_active:
            self._adopt_document_state(self._open_documents[self._active_tab])
        if not moving:
            # a tab being moved is shown somewhere else next; one closed is
            # gone, and what it held goes with it
            self._let_go()

    def confirm_all_documents(self) -> bool:
        """Include inactive tabs — and the other view's, in Split View — in
        the close/save decision, once per PDF."""
        seen = set()
        if not self.is_split:
            return self._confirm_pane_documents(seen)
        here = self._active_pane
        for pane in [p for p in self._panes if p is not here] + [here]:
            self.activate_pane(pane)
            if not self._confirm_pane_documents(seen):
                self.activate_pane(here)
                return False
        return True

    def _confirm_pane_documents(self, seen: set) -> bool:
        if not self._open_documents:
            return self.confirm_discard()
        previous = self._active_tab
        for index in range(len(self._open_documents)):
            document = self._state_for_tab(index)["document"]
            if id(document) in seen:
                continue
            seen.add(id(document))
            self.switch_to_document(index)
            if not self.confirm_discard():
                self.switch_to_document(previous)
                return False
        self.switch_to_document(previous)
        return True

    def open_new_window(self) -> "MainWindow":
        """A second window, with a document, pages and tool of its own.

        Nothing is shared but the application: the two windows do not reach
        into each other's document, and the arrangement each of them saves is
        stamped so a late write from one cannot land on the other's.
        """
        window = type(self)()
        # Offset from this one, so the new window is not exactly on top of the
        # old one and apparently missing.
        here = self.geometry()
        window.setGeometry(here.adjusted(36, 36, 36, 36))
        window.show()
        window.raise_()
        window.activateWindow()
        self.status_hint.setText("Opened a second window")
        return window

    def _new_undo_stack(self):
        # Replacing one view's document must not clear another view's history.
        # What was under way on the canvas going out is finished first, on
        # the history it belongs to (not the one about to replace it).
        self.view.leave_the_canvas()
        self.undo_stack = QUndoStack(self)
        self.undo_stack.setUndoLimit(200)
        from . import release
        release.STACKS.add(self.undo_stack)
        self._connect_undo_stack(self.undo_stack)
        # the menu's Undo and Redo follow the new history (QA F-02: after an
        # Undo and File ▸ New they stayed greyed for good)
        self._refresh_undo_actions()

    def new_document(self, confirm: bool = True) -> None:
        if confirm and not self.confirm_discard():
            return
        self.document = Document()
        self._new_undo_stack()
        self.current_index = 0
        self.rebuild_scenes()
        self.select_tool("select")
        self.toggle_calc_mode(False)          # decision 7: File > New is in Markup mode
        self.show_empty_workspace(False)
        self.view.fit_page()
        self.update_title()
        self._let_go()

    def rebuild_scenes(self) -> None:
        """Give every page a frame on the canvas, and show the current one.

        A page that already has a live frame keeps it. Building a fresh one
        would load the page's *pending* items, and those were emptied into the
        frame the first time it was built — so rebuilding after inserting a
        page would have quietly emptied every page in the document.
        """
        self._adopt_calc_defaults(self.document)
        from . import release
        release.DOCUMENTS.add(self.document)
        if self.scene is None or self.scene.document is not self.document:
            self.scene = DocumentScene(self.document)
            release.SCENES.add(self.scene)
            self.scene.itemsChanged.connect(self._refresh_lists_soon)
            self.scene.selectionChanged.connect(self._scene_selection_changed)
            self.view.setScene(self.scene)
        # Frames whose page has gone leave the canvas with it.
        live = {id(page) for page in self.document.pages}
        for frame in list(self.scene.frames):
            if id(frame.page) not in live:
                self.scene.frames.remove(frame)
                self.scene.removeItem(frame)
        ordered = []
        # tables and sheets coming in are calculated once, all together, at
        # the end — not each again as the next sheet it reads arrives (a
        # workbook of three sheets was calculated over four times, 2026-10-10)
        from contextlib import nullcontext
        cells = any(r.get("type") in ("table", "sheet_run") for page in self.document.pages
                    for r in (page._pending_items or ()) if isinstance(r, dict))
        if cells:
            from ..sheet.docbook import book_for
            batch = book_for(self.document).workbook.transaction("Load")
        else:
            batch = nullcontext()
        with batch:
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
        # spreadsheet pages: each run's cells on its first page, each page
        # its slice of the grid (ui/sheetpages.py)
        from . import sheetpages
        sheetpages.settle(self)
        # Pages moved, added or deleted: equations are evaluated in page
        # order, so the document's worksheet re-keys them (decision 9).
        from .view import rescue_stranded
        rescue_stranded(self.scene)
        from ..calc.docsheet import sheet_for
        sheet_for(self.document).pages_changed()
        self.current_index = max(0, min(self.current_index, len(self.document.pages) - 1))
        self.page_spin.blockSignals(True)
        self.page_spin.setRange(1, len(self.document.pages))
        self.page_spin.setValue(self.current_index + 1)
        self.page_spin.blockSignals(False)
        self.pages_panel.rebuild(self.document, self.current_index)
        self.refresh_lists()
        self.refresh_scale_label()

    def open_document(self) -> None:
        """File ▸ Open: the file in a tab of its own, as Revu opens it."""
        from .xlsximport import OPEN_FILTER
        path, _ = QFileDialog.getOpenFileName(self, "Open document",
                                              start_folder(self.document), OPEN_FILTER)
        if not path:
            return
        self._open_chosen(path)

    def _tab_showing(self, path: str):
        """(pane, tab) of this window showing the file at *path*, or None."""
        wanted = os.path.normcase(os.path.abspath(path))
        for pane in self._panes:
            states = self._open_documents if pane is self._active_pane else pane.documents
            for index, state in enumerate(states):
                if pane is self._active_pane and index == self._active_tab:
                    document = self.document
                else:
                    document = state["document"]
                if document.path and os.path.normcase(os.path.abspath(document.path)) == wanted:
                    return pane, index
        return None

    def _untouched(self) -> bool:
        """The document in view is a blank Untitled nobody has worked on."""
        return (not self.document.path and not self.document.modified
                and self.undo_stack.count() == 0)

    def _open_chosen(self, path: str) -> None:
        """Open *path* in a new tab — or bring forward the tab that already
        shows it. A blank, untouched Untitled is replaced rather than kept."""
        showing = self._tab_showing(path)
        if showing is not None:
            pane, index = showing
            self.activate_pane(pane)
            self.switch_to_document(index)
            self.status_hint.setText(f"{os.path.basename(path)} is already open")
            return
        new_tab = not self._untouched()
        if new_tab:
            previous = self._active_tab
            self.open_in_new_tab()
        try:
            opened = self.open_path(path) is not False
        except Exception as exc:  # noqa: BLE001
            opened = False
            QMessageBox.critical(self, "Open document", f"Could not open the file:\n{exc}")
        if not opened:
            if new_tab:
                self.close_document_tab(self._active_tab, moving=True)
                self.switch_to_document(previous)
            self._let_go()
            return
        self.undo_stack.clear()
        self.current_index = 0
        self.show_empty_workspace(False)
        self.rebuild_scenes()
        self.view.fit_page()
        self.update_title()
        self._let_go()
        remember_recent_file(path)
        self._say_what_the_workbook_left_out()

    # -- Open Recent, Close All, Save All (Revu's File menu) -----------------------------------
    def _fill_recent(self) -> None:
        menu = self.recent_menu
        menu.clear()
        files = recent_files()
        if not files:
            nothing = menu.addAction("No recent files")
            nothing.setEnabled(False)
            return
        for number, path in enumerate(files, 1):
            name = os.path.basename(path)
            action = bindable.data_entry(
                menu.addAction(f"&{number % 10}  {name}", lambda p=path: self.open_recent(p)))
            action.setToolTip(path)
            action.setStatusTip(path)
        menu.addSeparator()
        menu.addAction("Clear Recent Files", lambda: forget_recent_files())

    def open_recent(self, path: str) -> None:
        if not os.path.exists(path):
            forget_recent_files(path)
            QMessageBox.information(self, "Open Recent",
                                    f"“{os.path.basename(path)}” is no longer there:\n{path}")
            return
        self._open_chosen(path)

    def close_all_documents(self) -> bool:
        """Close every tab, each asking about unsaved changes; False if one
        was kept open."""
        for index in range(len(self._open_documents) - 1, -1, -1):
            count = len(self._open_documents)
            state = self._state_for_tab(index)
            last_and_empty = count == 1 and not state["document"].path \
                and state["undo_stack"].isClean() and not state["document"].modified
            if last_and_empty:
                break
            self.close_document_tab(index)
            if len(self._open_documents) == count and count > 1:
                return False                         # Cancel kept it
            if count == 1 and self.document is state["document"]:
                return False
        return True

    def save_all_documents(self) -> None:
        """Save every open document with unsaved changes, then come back."""
        here = self._active_tab
        saved = 0
        for index in range(len(self._open_documents)):
            state = self._state_for_tab(index)
            if state["undo_stack"].isClean() and not state["document"].modified:
                continue
            self.switch_to_document(index)
            if not self.save_document():
                break
            saved += 1
        self.switch_to_document(here)
        # said, rather than nothing at all (exercise round 1, F-35)
        self.status_hint.setText(
            f"Saved {saved} document{'s' * (saved != 1)}" if saved
            else "Save All: nothing to save — every open document is saved")

    def open_from_command_line(self, path: str) -> None:
        """`calcforge drawing.pdf`: open it as File > Open would."""
        if self.open_path(path) is False:
            return
        remember_recent_file(path)
        self.current_index = 0
        self.show_empty_workspace(False)
        self.rebuild_scenes()
        self.view.fit_page()
        self.update_title()
        self._let_go()
        self._say_what_the_workbook_left_out()

    def _say_what_the_workbook_left_out(self) -> None:
        """After opening an .xlsx: what came in, what was left out, and any
        formula that gives another answer here than in Excel."""
        imported = self.__dict__.pop("_opened_workbook", None)
        if imported is not None:
            from .xlsximport import _say
            _say(self, imported)

    def open_path(self, path: str) -> Optional[bool]:
        """Open a document, or bring in a PDF that is not one yet.

        A saved document is itself a PDF, so what decides between the two is
        what the file holds and not what it is called: a PDF carrying a
        MarkForge record is a document and opens as one, whatever its name.
        """
        from .xlsximport import is_workbook
        if is_workbook(path):
            # an Excel workbook: its worksheets as spreadsheet pages (cells only)
            from .xlsximport import open_workbook
            document, imported = open_workbook(self, path)
            if document is None:
                return False              # the reader cancelled the choice of worksheets
            self.document = document
            self._new_undo_stack()
            self._opened_workbook = imported
            return
        if project_io.carries_a_document(path):
            document = Document()
            project_io.load_document(document, path)
            self.document = document
            self._new_undo_stack()
            self._say_what_opening_found(document.open_warnings)
            return
        document = Document()
        document.mode = "pdf"
        document.title = os.path.splitext(os.path.basename(path))[0]
        document.pages = []
        count = pdfio.page_count(path)
        if count < 1:
            raise OSError("The PDF contains no pages")
        # Somebody else's markups come in as markups. A drawing that has been
        # through Bluebeam carries its clouds, call-outs, text boxes and
        # rectangles as PDF annotations, and the point of opening it here is to
        # work on them — to move a call-out, retype a text box, recolour a
        # cloud. Left in the file they are a picture of somebody's redlines.
        # The page's own line work is a different matter and stays off: that is
        # the drawing, not a markup, and there can be tens of thousands of it.
        pdfio.import_pages(document, path, list(range(count)), pdfio.FIT_ORIGINAL,
                           pdfio.BEST_DPI, at=0, annotations=True)
        # Opening a PDF is opening a document, not converting one. The page is
        # the PDF's own page, drawn by the PDF renderer; nothing on it is
        # turned into a markup of ours, so what is on screen is what any
        # reader shows and it opens as fast as one. Save writes this file back
        # — the source page comes through untouched and the markups go on top
        # of it, the way Bluebeam saves a marked-up drawing.
        document.path = path
        # Opened, not changed: nothing to save until something is (the user,
        # 2026-10-01: a PDF opens exactly as it was written).
        document.modified = False
        self.document = document
        self._new_undo_stack()
        # A file that had to be repaired to be read still opens, and is still
        # worth a word: what comes out of a save is a whole new file rather
        # than the original with the markups added to it.
        note = pdfio.trouble_with(path)
        if note:
            self.status_hint.setText(note)
        from ..io import calclayer
        from ..pdf import engine as pdf_engine
        found = []
        try:
            source = pdf_engine.open_bytes(document.asset(document.pages[0].pdf_key))
            try:
                if calclayer.is_signed(source):
                    document.signed_source = (document.pages[0].pdf_key,
                                              document.asset(document.pages[0].pdf_key))
                if calclayer.has_layers(source):
                    found.append("This PDF has CalcForge calculations, but the record "
                                 "they are edited from is missing. It has opened as a "
                                 "plain PDF: the calculations show, but can't be edited.")
            finally:
                pdf_engine.close(source)
        except Exception:                            # noqa: BLE001
            pass
        self._say_what_opening_found(found)

    def _say_what_opening_found(self, warnings: list) -> None:
        """Warnings from opening a file (decision 3): in the status bar, and
        in a message box when the window may ask things."""
        if not warnings:
            return
        text = "\n\n".join(warnings)
        self.status_hint.setText(" ".join(warnings))
        if self.interactive_prompts:
            QMessageBox.warning(self, "Open document", text)

    def save_document(self) -> bool:
        # A line still being typed is part of the document being saved, so it
        # is settled first — its answers worked out, its region kept or turned
        # into the note it turned out to be.
        self.view.end_item_edit()
        if not self.document.path:
            return self.save_document_as()
        self._recalculate_for_saving()
        # As SMath: a document gets an id once, and each save is a revision
        # (decision 28; the {revision} and {id} header/footer fields).
        import uuid
        if not self.document.doc_id:
            self.document.doc_id = str(uuid.uuid4())
        self.document.revision += 1
        try:
            note = project_io.save_document(self.document, self.document.path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Save", f"Could not save:\n{exc}")
            return False
        self.undo_stack.setClean()
        self.clear_autosave()
        self.update_title()
        said = f"Saved {self.document.path}"
        self.status_hint.setText(f"{said} — {note}" if note else said)
        return True

    def _recalculate_for_saving(self) -> None:
        """Every save recalculates first (decision 3): what goes into the file
        is the answer to what is on the page now."""
        from ..calc.docsheet import sheet_for
        if self.view.calc.editing():
            self.view.calc.leave()
        sheet = sheet_for(self.document)
        sheet.settle()
        sheet.recalculate(force=True)

    def save_document_as(self) -> bool:
        suggested = project_io.suggested_name(self.document)
        path, _ = QFileDialog.getSaveFileName(self, "Save document as",
                                              in_start_folder(suggested, self.document),
                                              project_io.FILTER)
        if not path:
            return False
        old_path, old_title = self.document.path, self.document.title
        old_recovery = self.autosave_path()
        self.document.path = path
        if self.document.title in ("", "Untitled"):
            self.document.title = project_io.describe(path)
        if not self.save_document():
            self.document.path, self.document.title = old_path, old_title
            return False
        remember_recent_file(path)
        if os.path.exists(old_recovery):
            try:
                os.remove(old_recovery)
            except OSError:
                pass
        return True

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

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._wrap_toolbar_rows()
        self._share_width_with_panels()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # the first size is given before the window counts as shown
        QTimer.singleShot(0, self, self._wrap_toolbar_rows)
        QTimer.singleShot(0, self, self._share_width_with_panels)

    # -- side panels in a narrow window ----------------------------------
    # The side panels kept their full width as the window narrowed and the
    # page took all of the loss: at 800 px the page was 183 px wide between
    # a 200 px Thumbnails panel and a 300 px Properties panel (QA,
    # 2026-10-15). The panels now give up a share once the page is down to
    # CANVAS_SHARE of the window, and are given back the width they had when
    # the window widens again.
    CANVAS_SHARE = 0.4
    #: The narrowest a side panel is squeezed to by this; it can still be
    #: dragged narrower, or closed.
    PANEL_LEAST = 140

    def _side_panels(self) -> list:
        return [dock for dock in getattr(self, "panels", [])
                if not dock.isHidden() and not dock.isFloating()
                and self.dockWidgetArea(dock) in (Qt.LeftDockWidgetArea,
                                                  Qt.RightDockWidgetArea)]

    def _share_width_with_panels(self) -> None:
        if not self.isVisible() or self.isFullScreen():
            return
        docks = self._side_panels()
        remembered = self.__dict__.setdefault("_panel_widths", {})
        # the widths the panels had at the last size that did not squeeze
        # them: Qt itself takes a little off them before this sees the resize
        natural = self.__dict__.setdefault("_panel_natural", {})
        for dock in list(remembered):
            if dock not in docks:
                del remembered[dock]
        if not docks:
            return
        # a panel's width as the layout has it now (activate: the docks may
        # not have been laid out at the new window size yet)
        self.layout().activate()
        widths = {dock: dock.width() for dock in docks}
        canvas = self.centralWidget().width()
        wanted = int(self.width() * self.CANVAS_SHARE)
        new = dict(widths)
        if canvas < wanted:
            short = wanted - canvas
            spare = {dock: max(0, width - self.PANEL_LEAST) for dock, width in widths.items()}
            total = sum(spare.values())
            if not total:
                return
            for dock in docks:
                remembered.setdefault(dock, max(widths[dock], natural.get(dock, 0)))
                new[dock] = widths[dock] - min(spare[dock], short * spare[dock] // total)
        elif remembered and canvas > wanted:
            room = canvas - wanted
            owed = {dock: max(0, remembered[dock] - widths[dock])
                    for dock in docks if dock in remembered}
            total = sum(owed.values())
            if not total:
                remembered.clear()
                natural.clear()
                natural.update(widths)
                return
            for dock, debt in owed.items():
                new[dock] = widths[dock] + min(debt, room * debt // total)
                if new[dock] >= remembered[dock]:
                    del remembered[dock]
        if not remembered:
            natural.clear()
            natural.update(new)
        changed = [dock for dock in docks if new[dock] != widths[dock]]
        if changed:
            self.resizeDocks(changed, [new[dock] for dock in changed], Qt.Horizontal)

    # -- toolbar rows that wrap ------------------------------------------
    # Revu's toolbars sit in rows, and a row that is too narrow for its bars
    # wraps: the bars that do not fit go down to a row of their own, and come
    # back when the window is wide again. Qt's own answer is to squash the
    # last bar on a row into its » chevron, which left the Calculation bar
    # showing one button of twelve (QA, 2026-10-15). The breaks put in here
    # are remembered apart from the ones the user made by dragging, and are
    # left out of the saved arrangement, so a narrow window today does not
    # become tomorrow's layout.
    def _toolbar_lines(self, area) -> list:
        """The shown toolbars in *area*, row by row as the user arranged
        them: a break the wrapping put in does not start a row here."""
        bars = [bar for bar in self.toolbars
                if self.toolBarArea(bar) == area and not bar.isHidden()]
        bars.sort(key=lambda bar: (bar.y(), bar.x()))
        lines: list = []
        for bar in bars:
            if not lines or (self.toolBarBreak(bar) and bar not in self._auto_breaks):
                lines.append([])
            lines[-1].append(bar)
        return lines

    def _wrap_toolbar_rows(self) -> None:
        """Break each toolbar row where its bars stop fitting, and take back
        the breaks there is room to do without."""
        if not self.isVisible() or not self.toolbars:
            return
        room = self.contentsRect().width()
        wanted: set = set()
        for area in (Qt.TopToolBarArea, Qt.BottomToolBarArea):
            for line in self._toolbar_lines(area):
                used = 0
                for bar in line:
                    width = bar.sizeHint().width()
                    if used and used + width > room:
                        wanted.add(bar)
                        used = 0
                    used += width
        if wanted == self._auto_breaks:
            return
        for bar in self._auto_breaks - wanted:
            if self.toolBarBreak(bar):
                self.removeToolBarBreak(bar)
        for bar in wanted - self._auto_breaks:
            if not self.toolBarBreak(bar):
                self.insertToolBarBreak(bar)
        self._auto_breaks = wanted

    def _wrap_toolbar_rows_soon(self) -> None:
        timer = getattr(self, "_wrap_timer", None)
        if timer is None:
            timer = self._wrap_timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._wrap_toolbar_rows)
        timer.start(0)

    def saveState(self, version: int = 0) -> QByteArray:
        """The arrangement as the user made it: without the row breaks put
        in only because the window is narrow just now."""
        made = [bar for bar in getattr(self, "_auto_breaks", ()) if self.toolBarBreak(bar)]
        for bar in made:
            self.removeToolBarBreak(bar)
        try:
            return super().saveState(version)
        finally:
            for bar in made:
                self.insertToolBarBreak(bar)

    def restoreState(self, state, version: int = 0) -> bool:
        done = super().restoreState(state, version)
        # the restored rows are all the user's; wrap them afresh
        self._auto_breaks = set()
        self._wrap_toolbar_rows_soon()
        if getattr(self, "left_rail_bar", None) is not None:
            self.arrange_side_toolbars()
        if getattr(self, "docks_by_name", None):
            for dock in self.panels:
                if dock.isFloating():
                    dock.floated_on_purpose = True     # left floating: kept so
                else:
                    self.put_panel_back(dock)          # saved along the top: to its side
            self.tabify_panels()          # panels saved stacked are tabbed, once
        return done

    #: The toolbars' rows out of the box, top to bottom.
    TOOLBAR_ROWS = (("toolbar_main", "toolbar_calculation", "toolbar_measure"),
                    ("toolbar_tools",), ("toolbar_style",))
    #: Bumped when TOOLBAR_ROWS changes in a way a saved arrangement from
    #: before should not keep: 2 split the measuring tools off the markup
    #: tools and moved the Calculation bar up a row (QA, 2026-10-15).
    TOOLBAR_ROWS_VERSION = 2

    def _default_toolbar_rows(self) -> None:
        """Put the toolbars back in their rows out of the box, keeping which
        are shown."""
        bars = {bar.objectName(): bar for bar in self.toolbars}
        shown = {bar: not bar.isHidden() for bar in self.toolbars}
        for number, row in enumerate(self.TOOLBAR_ROWS):
            if number:
                self.addToolBarBreak(Qt.TopToolBarArea)
            for name in row:
                if name in bars:
                    self.addToolBar(Qt.TopToolBarArea, bars[name])
        for bar, visible in shown.items():
            bar.setVisible(visible)
        self._auto_breaks = set()
        self._wrap_toolbar_rows_soon()

    if sys.platform == "win32":
        def nativeEvent(self, event_type, message):
            """Windows' messages for the frame: the menus sit in its title
            bar (nativeframe). Only defined on Windows, where it is needed."""
            frame = getattr(self, "_native_frame", None)
            if frame is not None:
                answer = frame.native_event(message)
                if answer is not None:
                    return answer
            return super().nativeEvent(event_type, message)

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

    def event(self, event) -> bool:
        if event.type() == QEvent.StatusTip:
            self._show_status_tip(event.tip())
            return True
        return super().event(event)

    def _show_status_tip(self, tip: str) -> None:
        """A hovered command's tip, in the footer's left half: from after
        the Show Grid and snap buttons to the end of the page navigation
        (which it stands in for while the pointer is in a menu, as Qt's own
        message does), ended with "…" where it runs out (QA F-23). Qt's
        message was painted from the bar's left edge across those buttons,
        its words over their icons. All is as it was when the pointer
        leaves."""
        bar = self.statusBar()
        label = getattr(self, "status_tip", None)
        if label is None or bar is None:
            return
        if not tip:
            label.hide()
            bar.after_layout = None
            return
        label.setText(tip)
        bar.after_layout = self._place_status_tip
        self._place_status_tip()
        label.show()
        label.raise_()

    def _place_status_tip(self) -> None:
        bar = self.statusBar()
        label = self.status_tip
        start = self.status_toggles.geometry().right() + 6 \
            if self.status_toggles.isVisible() else 4
        # up to the controls kept on the right (Scale, Fit Width, zoom …),
        # wherever the page navigation has been centred to
        left_half = {self.status_toggles, self.status_hint, self.status_position,
                     label, getattr(bar, "center_widget", None), *bar._spacers}
        rights = [child.geometry().left() for child in bar.children()
                  if isinstance(child, QWidget) and not child.isWindow()
                  and child.isVisible() and child not in left_half
                  and type(child).__name__ != "QSizeGrip" and child.geometry().left() > start]
        end = (min(rights) - 6) if rights else bar.width() // 2
        label.setGeometry(start, 0, max(0, end - start), bar.height())

    def closeEvent(self, event) -> None:
        # Nothing is settled here on purpose. Finishing an open markup touches
        # the panels, and the arrangement written a few lines further down
        # would then be the arrangement that left behind, not the one that was
        # on screen. There is nothing to lose by leaving it: a markup's text is
        # kept level with the typing as it goes, so what is in the document is
        # what was typed either way.
        if not getattr(self, "_closing_confirmed", False) and not self.confirm_all_documents():
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
        from . import release
        for stack in self._connected_undo_stacks:
            release.disconnect_stack(stack, self)
        event.accept()
        # Closed for good: whatever only this window showed — its canvases,
        # their markups, tables and equations, its undo histories and the
        # caches kept for them — goes now, not with the application.
        self._closed_for_good = True
        try:
            self.view.escape_everything()
        except RuntimeError:
            pass
        self._let_go()
        self._go_for_good()

    def _go_for_good(self) -> None:
        """A window closed for good is taken down, not just hidden (QA F-14).

        Kept, every window ever closed went on being restyled with the
        application (New Window took 2 s, then 3.6, then 5.3 … 35 s by the
        twelfth), went on filtering every event of the application, and its
        timers went on firing into it. The other windows stop counting it
        now, and Qt deletes it once the events in hand are through."""
        windows = type(self)._windows
        while self in windows:
            windows.remove(self)
        application = QApplication.instance()
        if application is not None and getattr(self, "_filters_the_application", False):
            application.removeEventFilter(self)
            self._filters_the_application = False
        for timer in self.findChildren(QTimer):
            timer.stop()
        # nor is anything drawn for it while Qt has yet to delete it (a
        # harness without an event loop never does): the Thumbnails went on
        # drawing the pages of a closed window's document as the page cache
        # finished them
        panel = getattr(self, "pages_panel", None)
        if panel is not None and hasattr(panel, "let_go"):
            panel.let_go()
        self.hide()
        self.deleteLater()

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
        if getattr(self, "_workspace_empty", False):
            self.setWindowTitle(APP_NAME)
            return
        name = os.path.basename(self.document.path) if self.document.path else "Untitled"
        try:
            dirty = "" if self.undo_stack.isClean() else " •"
        except RuntimeError:            # the window is being torn down
            return
        self.setWindowTitle(f"{name}{dirty} — {APP_NAME}")
        if 0 <= self._active_tab < self.document_tabs.count():
            self.document_tabs.setTabText(self._active_tab, name + dirty)

    def mark_modified(self) -> None:
        self.document.modified = True
        self.refresh_lists()
        # The page's thumbnail is drawn again once the edits stop: drawn on
        # every one, a page of a thousand markups cost a sixth of a second
        # each time one was let go of (2026-10-05).
        self.pages_panel.refresh_soon()

    # ==================================================================
    # pages
    # ==================================================================
    def current_page(self) -> Page:
        return self.document.pages[self.current_index]

    def _go_to_page_asked(self, index: int) -> None:
        """Go to Page from a page's menu: the current one too — its top, and
        a word to say so, rather than nothing (exercise round 1, F-35)."""
        if index == self.current_index and 0 <= index < len(self.document.pages):
            self.view.go_to_page_top(index)
            self.status_hint.setText(f"Page {index + 1} is the page in view")
            return
        self.go_to_page(index)

    def go_to_page(self, index: int) -> None:
        if not 0 <= index < len(self.document.pages):
            return
        if index == self.current_index:
            # already in view (a zoom brought it there, leaving a run picked
            # in Thumbnails): asked for, it is the page picked
            self.pages_panel.show_current(index)
            return
        # Anything half-finished belongs to the page being left, so it is
        # settled here rather than being carried onto the next one.
        self.view.end_item_edit()
        self.view.cancel_draft()
        self.current_index = index
        self.view._shown_page = index
        self.scene.show_page(index)           # Single Page / Side-by-Side: its spread
        self.view.go_to_page_top(index)
        # Zoomed out, that scroll can leave a later page in the middle of the
        # window, which its scroll reports as the page in view: the page
        # asked for is the one gone to, in the page box and Thumbnails alike.
        self.current_index = index
        self.view._shown_page = index
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(index + 1)
        self.page_spin.blockSignals(False)
        self.pages_panel.show_current(index)
        self.refresh_scale_label()
        self.refresh_selection()
        self._sync_other_windows(True)

    def _set_window_sync(self, mode: int) -> None:
        """One synchronization choice applies to every view of this document."""
        for other in list(type(self)._windows):
            if other is self or other.document is not self.document:
                continue
            other.window_sync.blockSignals(True)
            other.window_sync.setCurrentIndex(mode)
            other.window_sync.blockSignals(False)
        self._sync_other_windows(True)

    def _sync_other_windows(self, document_change: bool) -> None:
        """Copy this viewport to opted-in windows showing the same document."""
        if (self._syncing_view or getattr(self.view, "_zooming", False)
                or not hasattr(self, "window_sync")):
            return
        # Views share a scene. Resizing its pan margin changes *every*
        # scrollbar; a peer must not echo its old zoom back during that step.
        if any(other is not self and other.document is self.document
               and (other._syncing_view or getattr(other.view, "_zooming", False))
               for other in list(type(self)._windows)):
            return
        mode = self.window_sync.currentIndex()
        if mode == 0:
            return
        source_top = self.view._page_top_value(self.current_index)
        page_offset = self.view.verticalScrollBar().value() - source_top
        for other in list(type(self)._windows):
            if other is self:
                continue
            try:
                if other.document is not self.document or other.window_sync.currentIndex() == 0:
                    continue
                other._syncing_view = True
                if document_change and mode == 2 and other.current_index != self.current_index:
                    other.go_to_page(self.current_index)
                other.view.set_zoom(self.view.zoom())
                other.view.horizontalScrollBar().setValue(
                    self.view.horizontalScrollBar().value())
                other.view.verticalScrollBar().setValue(
                    round(other.view._page_top_value(other.current_index)
                          + page_offset))
            except RuntimeError:
                continue
            finally:
                try:
                    other._syncing_view = False
                except RuntimeError:
                    pass
        # the other view of a split window, when it shows the same document
        pane = self.other_pane()
        if pane is not None and pane.documents:
            state = pane.documents[pane.active]
            if state["document"] is self.document and pane.view.scene() is self.scene:
                index = self.current_index if mode == 2 else state["index"]
                self._syncing_view = True
                try:
                    pane.view.set_zoom(self.view.zoom())
                    pane.view.horizontalScrollBar().setValue(
                        self.view.horizontalScrollBar().value())
                    pane.view.verticalScrollBar().setValue(
                        round(pane.view._page_top_value(index) + page_offset))
                finally:
                    self._syncing_view = False

    def eventFilter(self, watched, event) -> bool:
        """Let the editor keep keys that would otherwise run global commands.

        Qt asks with a ShortcutOverride before it fires a shortcut. Accepting
        it means the key goes to whatever has focus instead — so while words
        are being typed, no document command fires at all. Two things are let
        through: a symbol binding, which is editor input rather than a
        command, and the handful of editor commands that are about the words
        themselves.
        """
        # This application-wide filter also sees every paint/layout/timer
        # event — thousands for one rebuild of the Properties panel — so the
        # test for the ones it handles is kept as cheap as Python allows
        # (novice finding 25). Only input handled below needs a walk up the
        # widget tree.
        kind = event.type()
        if kind not in _FILTERED_INPUT and kind != QEvent.FocusIn:
            if kind == QEvent.Show:
                # every menu as it opens, every button as it is shown: each
                # entry's command id, and the key bound to it shown beside it
                # (bindable.py)
                if isinstance(watched, QMenu):
                    if bindable.owning_window(watched) is self:
                        self.commands.decorate(watched)
                elif isinstance(watched, QAbstractButton) and not watched.property(
                        bindable.BUTTON) and bindable.owning_window(watched) is self:
                    self.commands.tag_one(watched)
            return False
        if (kind in (QEvent.MouseButtonPress, QEvent.FocusIn) and len(self._panes) > 1
                and isinstance(watched, QWidget)):
            # Split View: a click (or the keyboard) in a pane makes it the
            # one the menus, toolbars and panels act on
            pane = self.pane_of(watched)
            if pane is not None and pane is not self._active_pane:
                self.activate_pane(pane)
        if kind not in _FILTERED_INPUT:
            return False
        owner = watched if isinstance(watched, QWidget) else None
        on_canvas = False
        while owner is not None and not isinstance(owner, MainWindow):
            proxy = owner.graphicsProxyWidget() if owner.parentWidget() is None else None
            if proxy is not None and proxy.scene() is not None and proxy.scene().views():
                # a box on the canvas (a dimension's words, a typed size):
                # the window of the view it is shown in
                owner = proxy.scene().views()[0]
                on_canvas = True
                continue
            owner = owner.parentWidget()
        if owner is not self:
            return super().eventFilter(watched, event)
        if (event.type() == QEvent.ShortcutOverride and _a_field_being_typed_in(watched)
                and Qt.Key_F2 <= event.key() <= Qt.Key_F35
                and not event.modifiers() & (Qt.ControlModifier | Qt.AltModifier
                                             | Qt.MetaModifier)):
            # A function key while typing in a box — the formula bar, the Name
            # Box, Search, a typed size, a dimension's words, a panel's field —
            # belongs to the box, as it already did in a cell, an equation and
            # a text box: F12 switched modes and F11 went full screen in the
            # middle of a word (bug hunt, 2026-10-16). F1 (Help) still works.
            event.accept()
            return True
        if on_canvas:
            return super().eventFilter(watched, event)    # the view handles the rest
        # Inline panel editors can consume Escape before it bubbles up to
        # this window. Cancel the canvas first, while leaving dialogs/popups
        # to their own normal Escape behaviour.
        if (event.type() in (QEvent.ShortcutOverride, QEvent.KeyPress)
                and event.key() == Qt.Key_Escape and not event.modifiers()
                and not isinstance(QWidget.window(watched), dialogs.QDialog)
                and QApplication.activePopupWidget() is None
                and watched is not self.view and not self.view.isAncestorOf(watched)
                and watched is not self.document_tabs
                # Rename Page Label's in-place box: Escape leaves the label
                and not (isinstance(watched, QLineEdit)
                         and watched.objectName() == "pageLabelEditor")):
            if event.type() == QEvent.KeyPress:
                self.view.escape_everything()
            event.accept()
            return True
        if (event.type() == QEvent.MouseButtonPress and self.holding_a_format()
                and isinstance(watched, QWidget)
                and watched is not self.view and not self.view.isAncestorOf(watched)
                and not (isinstance(watched, QToolButton)
                         and watched.defaultAction() is self.act_format_painter)):
            self.put_the_format_painter_down()
        if (event.type() == QEvent.ShortcutOverride and self.view.calc.calc_mode()
                and not self.view.is_editing()):
            # Calc mode: no tool key fires, with or without Shift or Alt
            # (decision 5). The key goes to the canvas, where a letter —
            # Shift+E included — starts an equation.
            binding = self.shortcuts.binding_for(QKeySequence(event.keyCombination()),
                                                 scopes=(MARKUP,))
            # a Markup-mode *command* (Multiply's Ctrl+M) has handed its key
            # to the Calc-mode one (_apply_mode_keys); only tool keys stop here
            if binding is not None and binding.kind != COMMAND:
                event.accept()
                return True
            # and a bare character starts an equation, whatever it has been
            # bound to elsewhere (Keyboard Shortcuts takes any key, 2026-10-16)
            text = event.text()
            if (text and text.isprintable() and not text.isspace()
                    and not event.modifiers() & (Qt.ControlModifier | Qt.AltModifier
                                                 | Qt.MetaModifier)
                    and (watched is self.view or self.view.isAncestorOf(watched))):
                event.accept()
                return True
        if event.type() == QEvent.ShortcutOverride and self.view.is_editing():
            sequence = QKeySequence(event.keyCombination())
            binding = self.shortcuts.binding_for(sequence)
            if binding is None and self._menu_mnemonic(event):
                # Alt and a menu's letter opens that menu while an equation
                # or a text box is being typed in, as it does in Revu and on
                # any Windows program (exercise round 1, F-07): a mnemonic is
                # not a command, and nothing else is bound to it.
                return super().eventFilter(watched, event)
            if not (binding is not None and (binding.kind == TYPED_SYMBOL
                                             or binding.action_id in self.EDITOR_COMMANDS)):
                # Including Ctrl+B, Ctrl+I and Ctrl+U. Whatever is bound to
                # them, it does not fire in the middle of a sentence; the view
                # takes them and formats the words instead.
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def _menu_mnemonic(self, event) -> bool:
        """Is this key Alt and the underlined letter of a menu on the bar?"""
        if event.modifiers() & ~(Qt.AltModifier | Qt.KeypadModifier) or \
                not event.modifiers() & Qt.AltModifier:
            return False
        key = event.key()
        if not Qt.Key_A <= key <= Qt.Key_Z:
            return False
        sequence = QKeySequence(Qt.AltModifier | Qt.Key(key))
        return any(action.isVisible() and action.isEnabled()
                   and QKeySequence.mnemonic(action.text()) == sequence
                   for action in self.menuBar().actions())

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

    def hide_or_show_panels(self, _checked: bool = False) -> None:
        """Revu's Hide Panels (Shift+F4): with any panel open, every one goes
        and is remembered; pressed again, they come back — the default one
        on each side when none had been open."""
        open_now = [name for name, dock in self.docks_by_name.items()
                    if name in self.PANEL_ICONS and not dock.isHidden()]
        if open_now:
            self._panels_hidden = open_now
            for name in open_now:
                dock = self.docks_by_name[name]
                if not dock.isFloating():
                    # the width it had, for when it comes back
                    side = self.panel_sides.get(name, LEFT)
                    self._edge_hidden = getattr(self, "_edge_hidden", {})
                    self._edge_hidden.setdefault(side, (name, dock.width()))
                self.show_panel(name, False)
            self.status_hint.setText("Panels hidden — Shift+F4 brings them back")
            return
        wanted = getattr(self, "_panels_hidden", None) or []
        self._panels_hidden = []
        # and a column hidden by double-clicking its edge comes back with them
        edged = getattr(self, "_edge_hidden", {})
        if not wanted and not edged:
            self.show_all_panels()
            return
        for name in wanted:
            self.show_panel(name, True)
        for side in list(edged):
            if self.open_panel_on(side) is None:
                self.open_panel_column(side)
        self._edge_hidden = {}

    def _apply_mode_keys(self) -> None:
        """A key shared by a Markup-mode and a Calc-mode command (Ctrl+M:
        Multiply, or SMath's Matrix) is carried only by the command of the
        mode in force, so the two never fight over it."""
        calc_on = self.view.calc.calc_mode()
        for key, scope in _SHORTCUT_SCOPES.items():
            action = getattr(self, f"act_{key}", None)
            action_id = self.action_ids.get(key)
            if action is None or action_id is None:
                continue
            live = (scope == "calc") == calc_on
            action.setShortcuts(self._keys_for(key, self.shortcuts.sequence(action_id))
                                if live else [])
        commands = getattr(self, "commands", None)
        if commands is not None:
            commands.apply()

    def lock_toolbars(self, locked: bool) -> None:
        for bar in self.toolbars:
            bar.setMovable(not locked)
        self.status_hint.setText("Toolbars locked" if locked else "Toolbars unlocked")

    # -- toolbars on the side edges ----------------------------------------
    # A toolbar can go to the left or right edge (the user, 2026-10-15:
    # "allow toolbars to be dragged to the side on their own column (can't
    # join the panel column)"). There it is a column of its own between the
    # window's edge and the panel rail: never in the rail's column, never
    # between the rail and its panels, never sharing a column with another
    # toolbar. Qt's toolbar areas are outside the dock areas already, so a
    # side toolbar is always outside the panels; what is kept in order here
    # is the rail, which is a toolbar too and has to stay next to the panels.
    #: The toolbars that only go top or bottom: the Properties toolbar's boxes
    #: and lists, and the Markup Styles bar's words, do not work stood on end.
    TOP_AND_BOTTOM_ONLY = ("toolbar_style", "toolbar_markup_styles")

    def _side_rails(self) -> dict:
        return {Qt.LeftToolBarArea: self.left_rail_bar,
                Qt.RightToolBarArea: self.right_rail_bar}

    def _side_columns_in_order(self, area) -> bool:
        """Whether every toolbar in the side *area* is in a column of its own,
        all of them outside the rail."""
        rail = self._side_rails()[area]
        bars = [bar for bar in self.toolbars if self.toolBarArea(bar) == area
                and not bar.isHidden()]
        if not bars:
            return True
        if not self.isVisible():
            return False
        self.layout().activate()
        left = area == Qt.LeftToolBarArea
        columns = set()
        for bar in bars:
            x = bar.geometry().x()
            if x in columns or abs(x - rail.geometry().x()) < 2:
                return False
            if (x > rail.geometry().x()) if left else (x < rail.geometry().x()):
                return False
            columns.add(x)
        return True

    def arrange_side_toolbars(self) -> None:
        """Give each toolbar on a side edge a column of its own, outside the
        rail; put one that cannot stand on end back at the top."""
        for bar in self.toolbars:
            if (bar.objectName() in self.TOP_AND_BOTTOM_ONLY
                    and self.toolBarArea(bar) in self._side_rails()):
                self.addToolBar(Qt.TopToolBarArea, bar)
        for area, rail in self._side_rails().items():
            if self._side_columns_in_order(area):
                continue
            bars = [bar for bar in self.toolbars if self.toolBarArea(bar) == area]
            # the order they are in now, from the edge inwards
            bars.sort(key=lambda bar: bar.geometry().x(),
                      reverse=area == Qt.RightToolBarArea)
            for bar in bars:
                self.insertToolBar(rail, bar)
                self.insertToolBarBreak(rail)
        self._auto_breaks = {bar for bar in self._auto_breaks
                             if self.toolBarArea(bar) in (Qt.TopToolBarArea,
                                                          Qt.BottomToolBarArea)}

    def _arrange_side_toolbars_soon(self) -> None:
        timer = getattr(self, "_side_timer", None)
        if timer is None:
            timer = self._side_timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self.arrange_side_toolbars)
        timer.start(0)

    def _toolbar_stood_on_end(self, bar, orientation) -> None:
        """A toolbar moved to a side edge shows its buttons' icons only, and
        is given its column; back at the top it is as it was."""
        vertical = orientation == Qt.Vertical
        hook = getattr(bar, "set_vertical", None)
        if hook is not None:
            hook(vertical)
        elif vertical:
            bar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self._arrange_side_toolbars_soon()

    def _toolbars_off_the_rails(self) -> None:
        """A layout saved with toolbars on the side edges: each one in its
        own column outside the rail (and the Properties toolbar, which only
        goes top or bottom, back at the top)."""
        self.arrange_side_toolbars()

    def reset_layout(self) -> None:
        """Put every panel and toolbar back where it started."""
        settings = app_settings()
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
        self._wrap_toolbar_rows_soon()          # the bars changed width

    # -- remembering it ------------------------------------------------
    def note_layout_change(self) -> None:
        """Something moved; write the arrangement out in a moment."""
        if getattr(self, "_closed_for_good", False):
            return                  # its panels going with it are not a change
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
        settings = app_settings()
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
        settings = app_settings()
        try:
            stamp = int(settings.value("window/stamp", 0)) + 1
        except (TypeError, ValueError):
            stamp = 1
        settings.setValue("window/stamp", stamp)
        self._layout_stamp = stamp
        settings.setValue("window/geometry", self.saveGeometry())
        settings.setValue("window/frame", "native")
        settings.setValue("window/maximised", self.isMaximized())
        settings.setValue("window/state", self.saveState())
        settings.setValue("toolbars/rows", self.TOOLBAR_ROWS_VERSION)
        settings.setValue("window/markups_list",
                          [self.bottom_split.sizes()[1] if self.markups_list_open() else 0,
                           self._markups_height])
        settings.setValue("toolbars/locked", not self.toolbars[0].isMovable())
        if self.visible_tools is None:
            settings.remove("toolbars/tools")
        else:
            settings.setValue("toolbars/tools", sorted(self.visible_tools))
        save_panel_state(self.panels)
        settings.sync()

    def restore_layout(self) -> None:
        settings = app_settings()
        # What this window has caught up with. A delayed save from a window
        # still holding an older arrangement checks this before writing.
        try:
            self._layout_stamp = int(settings.value("window/stamp", 0))
        except (TypeError, ValueError):
            self._layout_stamp = 0
        geometry = settings.value("window/geometry")
        if sys.platform != "darwin" and settings.value("window/frame") != "native":
            # saved by a window that drew its own frame (before 2026-10-16):
            # its size and place would land the native frame askew
            geometry = None
        state = settings.value("window/state")
        if geometry is not None:
            self.restoreGeometry(geometry)
        if state is not None:
            self.restoreState(state)
            self._toolbars_off_the_rails()
            try:
                rows = int(settings.value("toolbars/rows", 1))
            except (TypeError, ValueError):
                rows = 1
            if rows < self.TOOLBAR_ROWS_VERSION:
                self._default_toolbar_rows()
        stored = settings.value("window/markups_list")
        try:
            shown, height = (int(v) for v in stored) if stored else (0, 220)
        except (TypeError, ValueError):
            shown, height = 0, 220
        self._markups_height = max(height, 120)
        if shown > 0:
            self.show_markups_list(True)
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
        from shiboken6 import isValid
        if not isValid(self.page_spin) or not isValid(self.page_panel.width_mm):
            return                     # a last scroll while the window is being taken down
        self.current_index = index
        self.scene.show_page(index)
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(index + 1)
        self.page_spin.blockSignals(False)
        # Scrolled to, zoomed or fitted onto: a run picked out in Thumbnails
        # stays picked and only the page in view moves; Page Setup, Delete
        # and the rest still act on the run until another thumbnail is
        # clicked (the user, 2026-10-17). One page picked follows the view.
        self.pages_panel.show_current(index, keep_run=True)
        self.refresh_scale_label()
        self._sync_other_windows(True)

    def _structure_snapshot(self, reuse: Optional[dict] = None) -> dict:
        """Every page written out. With *reuse* (from the snapshot before a
        change), a page whose markups have not changed since keeps the
        markups written then: adding a page to a sheet of a thousand markups
        wrote all thousand out twice (2026-10-05)."""
        pages, written = [], {}
        for page in self.document.pages:
            frame = page.frame
            generation = frame.layer.generation if frame is not None else None
            kept = (reuse or {}).get(id(page))
            if kept is not None and generation is not None and kept[0] == generation:
                entry = page.to_dict(items=kept[1])
            else:
                entry = page.to_dict()
            if generation is not None:
                written[id(page)] = (generation, entry["items"])
            pages.append(entry)
        self._written_pages = written
        # and how the view was, so an undo or redo of the change shows the
        # pages as they were seen then (QA F-21: after undoing A0 the view
        # stayed at 17 %, or on page 2, or on the empty desk)
        view = {"zoom": self.view.zoom(),
                "h": self.view.horizontalScrollBar().value(),
                "v": self.view.verticalScrollBar().value()}
        return {"pages": pages, "current": self.current_index, "view": view}

    def _restore_structure(self, snapshot: dict, preserve_view: bool = False) -> None:
        scroll = (self.view.horizontalScrollBar().value(),
                  self.view.verticalScrollBar().value())
        self.document.pages = [Page.from_dict(entry) for entry in snapshot["pages"]]
        self.current_index = max(0, min(snapshot.get("current", 0),
                                        len(self.document.pages) - 1))
        self.rebuild_scenes()
        seen = snapshot.get("view")
        if seen:
            self.view.set_zoom(float(seen["zoom"]))
            self.view.horizontalScrollBar().setValue(int(seen["h"]))
            self.view.verticalScrollBar().setValue(int(seen["v"]))
        elif preserve_view:
            self.view.horizontalScrollBar().setValue(scroll[0])
            self.view.verticalScrollBar().setValue(scroll[1])
        index = self.current_index
        self.view._shown_page = index
        self.current_index = -1          # so the chrome is told, even unmoved
        self.follow_scrolled_page(index)
        self.current_index = index
        self.update_title()

    def warn_undefined(self, names: list, why: str) -> None:
        """Say which variables have just become undefined, and why."""
        if not names:
            return
        text = f"{why}: {', '.join(names)} " + ("is" if len(names) == 1 else "are") + \
            " no longer defined."
        self.status_hint.setText(text)
        if self.interactive_prompts:
            QMessageBox.warning(self, "Variables undefined", text)

    def record_structure_change(self, before: dict, description: str) -> None:
        """One undo step from *before* to how the document is now, for a
        change already made (equations moved on to new pages, say)."""
        after = self._structure_snapshot()
        self.undo_stack.push(DocumentStructureCommand(
            before, after, description,
            lambda snapshot: self._restore_structure(snapshot, True)))
        self.mark_modified()

    def _structural_change(self, description: str, mutate,
                           preserve_view: bool = False, bookmarks: bool = False) -> bool:
        """Change the pages as one undo step; False if nothing changed (and
        nothing was recorded). With *bookmarks*, where the bookmarks point is
        part of the step too (Page Setup moves it)."""
        before = self._structure_snapshot()
        marks_before = [mark.to_dict() for mark in self.document.bookmarks]
        # the run picked out in Thumbnails, which a change to those pages that
        # leaves them where they are keeps picked (Page Setup, Crop Pages, as
        # Set Scale and Flatten already did)
        picked = self.selected_pages()
        order = [page.uid for page in self.document.pages]
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
        if len(picked) > 1 and [page.uid for page in self.document.pages] == order:
            self.pages_panel.pick(picked)
        after = self._structure_snapshot(reuse=getattr(self, "_written_pages", None))
        if after["pages"] == before["pages"]:
            # nothing about the pages changed (Page Setup OK'd as it was, say):
            # nothing to undo either (QA F-28)
            return False
        restore = (lambda snapshot: self._restore_structure(snapshot, True)) \
            if preserve_view else self._restore_structure
        if bookmarks:
            before["bookmarks"] = marks_before
            after["bookmarks"] = [mark.to_dict() for mark in self.document.bookmarks]
            pages_back = restore

            def restore(snapshot, pages_back=pages_back):
                from ..core.document import Bookmark
                self.document.bookmarks = [Bookmark.from_dict(mark)
                                           for mark in snapshot.get("bookmarks", [])]
                pages_back(snapshot)
        self.undo_stack.push(DocumentStructureCommand(before, after, description,
                                                      restore))
        self.mark_modified()
        return True

    def page_index(self, index: Optional[int] = None) -> int:
        """The page a command applies to: the one named, else the current one."""
        if index is None:
            return self.current_index
        return max(0, min(int(index), len(self.document.pages) - 1))

    def thumbnail_selection(self) -> list[int]:
        """The pages picked out in Thumbnails, for a Pages control's
        Selected — which only appears when something besides the page in
        view is picked (Revu: "only appears if pages were selected")."""
        picked = self.selected_pages()
        return picked if picked and picked != [self.current_index] else []

    def blank_page_dialog(self, index: Optional[int] = None,
                          before: bool = False) -> "dialogs.InsertBlankPageDialog":
        """Revu's Insert Blank Page, placed Before or After page *index* (the
        page in view when none is named); not yet shown."""
        which = self.page_index(index)
        return dialogs.InsertBlankPageDialog(
            self.document.pages[which].setup, self, count=len(self.document.pages),
            page=which, after=not before)

    def add_page(self, index: Optional[int] = None, before: bool = False) -> None:
        """Document ▸ Insert ▸ Blank Page…, and the Thumbnails menu's Insert
        Blank Page ▸ Before / After, which open the dialog placed there."""
        if not self.interactive_prompts:
            # one page of the same paper, where asked: what the suite and
            # scripted callers build documents with
            from .sheetpages import safe_target
            which = self.page_index(index)
            target = safe_target(self.document, which + (0 if before else 1))
            setup = PageSetup.from_dict(self.document.pages[which].setup.to_dict())
            self._insert_blank_pages(target, 1, setup)
            return
        dialog = self.blank_page_dialog(index, before)
        if dialog.exec() != dialogs.QDialog.Accepted:
            return
        self.finish_blank_page(dialog)

    def finish_blank_page(self, dialog) -> int:
        """Insert the pages *dialog* asked for, where it said; one undo step.
        Says where the first of them is."""
        from .sheetpages import safe_target
        target = safe_target(self.document, dialog.target())
        count = dialog.page_count.value()
        self._insert_blank_pages(target, count, dialog.chosen_setup())
        return target

    def _insert_blank_pages(self, target: int, count: int, setup: PageSetup) -> None:
        def mutate():
            for offset in range(count):
                page = self.document.add_page(target + offset)
                page.setup = PageSetup.from_dict(setup.to_dict())
            self.current_index = target
        self._structural_change("Add page" if count == 1 else f"Add {count} pages", mutate)

    def _edit_chart(self, chart) -> None:
        from .chartdialog import edit_chart
        edit_chart(self, chart)

    def insert_chart(self, kind: str = "scatter", lines: bool = False, markers: bool = True):
        """Insert ▸ Chart: a chart of the cells picked out in the open table."""
        from .chartdialog import insert_chart
        return insert_chart(self.view.tables, kind, lines, markers)

    def insert_workbook(self, path: Optional[str] = None, index: Optional[int] = None,
                        before: bool = False) -> bool:
        """Insert ▸ Excel workbook: its worksheets as spreadsheet pages."""
        from .xlsximport import insert_workbook
        return insert_workbook(self, path, index, before)

    def insert_sheet_page(self, index: Optional[int] = None, before: bool = False) -> None:
        """A page of spreadsheet cells (ui/sheetpages.py)."""
        from .sheetpages import insert_sheet_page
        insert_sheet_page(self, index, before)

    def sheet_page_setup(self, index: Optional[int] = None) -> None:
        """The spreadsheet's own page layout (ui/sheetlayout.py)."""
        from .sheetlayout import sheet_page_setup
        sheet_page_setup(self, self.page_index(index))

    def add_page_before(self, index: Optional[int] = None) -> None:
        self.add_page(index, before=True)

    def duplicate_page(self, index: Optional[int] = None) -> None:
        """Copy the page — or the whole picked run — in after the last of it."""
        from .sheetpages import fresh_item_ids, plain_copy, safe_target
        wanted = self.pages_acted_on(index)
        sources = [self.document.pages[which].to_dict() for which in wanted]
        if any(self.document.pages[which].sheet for which in wanted):
            sources = [plain_copy(source) for source in sources]
        sources = fresh_item_ids(sources)
        target = safe_target(self.document, wanted[-1] + 1)

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
        payload = {"calcforge_page": pages[0], "calcforge_pages": pages,
                   "assets": assets}
        QApplication.clipboard().setText(json.dumps(payload))
        self.status_hint.setText(
            (f"Copied page {wanted[0] + 1}" if len(wanted) == 1
             else f"Copied {len(wanted)} pages") + " — Paste Pages puts a copy in")

    def page_on_the_clipboard(self) -> Optional[dict]:
        """The page waiting on the clipboard, if there is one."""
        try:
            payload = json.loads(QApplication.clipboard().text() or "")
        except (ValueError, TypeError):
            return None
        if not isinstance(payload, dict) or "calcforge_page" not in payload:
            return None
        return payload

    def paste_page(self, index: Optional[int] = None,
                   before: bool = False) -> None:
        """Put the copied page in beside this one, and go to where it landed."""
        payload = self.page_on_the_clipboard()
        if payload is None:
            self.status_hint.setText("There is no page on the clipboard")
            return
        from .sheetpages import fresh_item_ids, plain_copy, safe_target
        which = self.page_index(index)
        target = safe_target(self.document, which if before else which + 1)
        for key, encoded in (payload.get("assets") or {}).items():
            if not self.document.asset(key):
                try:
                    self.document.put_asset(key, base64.b64decode(encoded))
                except (ValueError, TypeError):
                    pass

        waiting = payload.get("calcforge_pages") or [payload["calcforge_page"]]
        waiting = [plain_copy(source) if source.get("sheet") else source for source in waiting]
        waiting = fresh_item_ids(waiting)

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
        self.pages_panel.show_current(target)
        self.status_hint.setText(f"Page pasted in as page {target + 1}")

    def _pages_for(self, index: Optional[int] = None) -> list[int]:
        """The pages a page dialog starts on: from the menu bar, what
        Thumbnails has picked out (else the page in view); from a page's own
        menu, that page or the run it is in."""
        picked = self.thumbnail_selection()
        return picked if index is None and picked else self.pages_acted_on(index)

    def _pages_preset(self, pages_range, going: list, which: int) -> None:
        """Set a Pages control to *going*: Selected when that is what
        Thumbnails has picked, Current when it is the one page, else Custom."""
        if going and going == pages_range.selected:
            pages_range.choose(pages_range.SELECTED)
        elif going == [pages_range.current]:
            pages_range.choose(pages_range.CURRENT)
        elif going:
            pages_range.set_custom(dialogs.page_ranges(going))

    def delete_pages_dialog(self, index: Optional[int] = None,
                            pages: Optional[list] = None) -> "dialogs.DeletePagesDialog":
        """Revu's Delete Pages, set to the page (or the run picked out, or the
        *pages* given); not yet shown."""
        which = self.page_index(index)
        going = sorted(pages) if pages is not None else self._pages_for(index)
        dialog = dialogs.DeletePagesDialog(len(self.document.pages), which,
                                           self.thumbnail_selection(), self)
        self._pages_preset(dialog.pages, going, which)
        return dialog

    def delete_page(self, index: Optional[int] = None, pages: Optional[list] = None,
                    ask: bool = True) -> None:
        """Take out the page — or the whole run picked out in the panel, or
        the *pages* given (a sheet's, from its tab) — after Revu's Delete
        Pages dialog, which can change which."""
        if len(self.document.pages) <= 1:
            QMessageBox.information(self, "Delete Pages", "A document needs at least one page.")
            return
        if ask and self.interactive_prompts and pages is not None:
            # a sheet's pages, from its tab: Excel's question, not Revu's dialog
            asked = (f"Delete page {pages[0] + 1}?" if len(pages) == 1
                     else f"Delete these {len(pages)} pages?")
            if QMessageBox.question(self, "Delete Pages", asked) != QMessageBox.Yes:
                return
        elif ask and self.interactive_prompts:
            dialog = self.delete_pages_dialog(index, pages)
            if dialog.exec() != dialogs.QDialog.Accepted:
                return
            self.finish_delete_pages(dialog)
            return
        going = sorted(pages) if pages is not None else self.pages_acted_on(index)
        # Never all of them: a document has to keep a page. The last one in
        # the run stays behind rather than the first, so what is left is the
        # end of what was there rather than the start of it.
        if len(going) >= len(self.document.pages):
            going = going[:len(self.document.pages) - 1]
        self._delete_pages(going)

    def finish_delete_pages(self, dialog) -> int:
        """Delete the pages *dialog* chose; how many went. Every page cannot."""
        problem = dialog.problem()
        if problem:
            self.status_hint.setText(problem)
            return 0
        going = sorted(dialog.page_indexes())
        self._delete_pages(going)
        return len(going)

    def _delete_pages(self, going: list) -> None:
        if not going:
            return
        from .calcedit import undefined_without
        going_equations = [item for which in going
                           for item in (self.document.pages[which].frame.markups()
                                        if self.document.pages[which].frame else [])
                           if getattr(item, "IS_CALC", False)]
        lost = undefined_without(self.document, going_equations)

        def mutate():
            # a spreadsheet page takes its rows with it (ui/sheetpages.py)
            from .sheetpages import before_delete
            before_delete(self, going)
            # Backwards, so each removal leaves the ones still to go where
            # they were.
            for which in reversed(going):
                self.document.remove_page(which)
            self.current_index = max(0, going[0] - 1)
        self._structural_change("Delete page" if len(going) == 1
                                else f"Delete {len(going)} pages", mutate)
        self.warn_undefined(lost, "Page deleted")

    def move_page(self, source: int, target: int, count: int = 1) -> None:
        """Move a page, or a run of them, to start at *target*."""
        count = max(int(count), 1)
        from .sheetpages import move_allowed
        if not move_allowed(self.document, source, count, target):
            # a run of spreadsheet pages is one sheet: it moves whole, and
            # nothing goes in between its pages
            self.status_hint.setText("A spreadsheet's pages move together, and nothing goes "
                                     "between them")
            self.pages_panel.rebuild(self.document, self.current_index)
            return

        def mutate():
            self.current_index = self.document.move_pages(source, count, target)
        self._structural_change("Reorder pages", mutate)

    # -- Page Setup (Revu's: the paper, and the content resized onto it) ------
    def page_setup_dialog(self, state: Optional[dict] = None) -> "dialogs.PageSetupDialog":
        """Revu's Page Setup for the page in view (or the pages picked out in
        Thumbnails); not yet shown. After Get Line it comes back as it was
        left, with the Rotation the line asked for."""
        which = self.current_index
        dialog = dialogs.PageSetupDialog(
            self.current_page().setup, self, len(self.document.pages) > 1,
            document=self.document, current=which,
            selected=self.thumbnail_selection(), state=state)
        if state is None:
            self._pages_preset(dialog.pages, self._pages_for(), which)
        return dialog

    def page_setup(self, state: Optional[dict] = None) -> None:
        """Document ▸ Page Setup…: new paper for the chosen pages, their
        drawing, markups, equations and tables scaled, moved and turned onto
        it (Auto Scale, Scale, Offset, Rotation, Centre, Fit to Media)."""
        if not isinstance(state, dict):
            state = None          # a button's or an action's "checked", not a state
        dialog = self.page_setup_dialog(state)
        answer = dialog.exec()
        if answer == dialog.PICK:
            # Get Line: a line dragged on the drawing, then this again
            self._scale_dialog_state = None
            self.select_tool("calibrate")
            self._page_setup_state = dialog.state()
            self.status_hint.setText("Page Setup: drag along a line on the drawing that "
                                     "should be level — Esc goes back to Page Setup")
            return
        if answer != dialogs.QDialog.Accepted:
            return
        self.finish_page_setup(dialog)

    def page_setup_line(self, start: QPointF, end: QPointF) -> None:
        """Get Line's line, dragged on the page: Page Setup comes back with
        the Rotation that makes it level."""
        state = getattr(self, "_page_setup_state", None)
        self._page_setup_state = None
        if state is None:
            return
        from .pagesetup import level_rotation
        state["rotation"] = level_rotation(start, end)
        self.select_tool("select")
        QTimer.singleShot(0, lambda: self.page_setup(state=state))

    def finish_page_setup(self, dialog) -> bool:
        """Apply *dialog*'s Page Setup to the pages it chose; one undo step."""
        pages = dialog.page_indexes()
        if not pages:
            self.status_hint.setText("Page Setup: those pages are not in this document")
            return False
        return self.apply_page_setup(dialog.plan(), pages)

    def apply_page_setup(self, plan, pages: list, preserve_view: bool = False,
                         description: str = "Page Setup") -> bool:
        """Give *pages* (indexes) the paper and placement *plan* says (a
        pagesetup.Plan). False, and nothing recorded, if it changes nothing."""
        from . import pagesetup
        changes = pagesetup.changes_for(self.document, plan, pages)
        picked = self.selected_pages()
        if not changes:
            # OK with nothing changed changes nothing: not the view, not the
            # history (QA F-28)
            self.status_hint.setText("Page Setup: nothing changed")
            return False

        def mutate():
            pagesetup.carry_out(self, changes)
        try:
            done = self._structural_change(description, mutate, preserve_view=preserve_view,
                                           bookmarks=True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Page Setup", str(exc))
            return False
        if not done:
            return False
        if not preserve_view:
            self.view.fit_page()
            self._note_view_after_change()
            if len(picked) > 1:
                self.pages_panel.pick(picked)   # the fit scrolled past other pages
        # the scale label, the lists and the Page panel came up to date with
        # the pages; the Properties of what is picked out follow
        self.refresh_selection()
        count = len({id(change.page) for change in changes})
        size = changes[0].setup
        self.status_hint.setText(
            f"Page Setup: {count} page{'s' if count != 1 else ''} now "
            f"{size.width_pt * 25.4 / 72:.0f} × {size.height_pt * 25.4 / 72:.0f} mm")
        return True

    def _note_view_after_change(self) -> None:
        """The view settled after the last page change was recorded (a fit,
        say): a redo of it comes back to this view, not the one before."""
        index = self.undo_stack.index() - 1
        command = self.undo_stack.command(index) if index >= 0 else None
        after = getattr(command, "after", None)
        if isinstance(after, dict) and "view" in after:
            after["view"] = {"zoom": self.view.zoom(),
                             "h": self.view.horizontalScrollBar().value(),
                             "v": self.view.verticalScrollBar().value()}

    def set_page_setup(self, setup: PageSetup, all_pages: bool = False) -> None:
        """Give the current page (or every page) this paper; one undo step.

        The Page panel's paper and margin boxes and the Paper Size menu: the
        paper changes and what is on it stays where it is on the page (as
        Page Setup with its Clear), the file's page given the same paper so
        the saved PDF shows it."""
        from .pagesetup import MARGIN_KEYS, Plan
        indexes = list(range(len(self.document.pages))) if all_pages \
            else [self.current_index]
        plan = Plan(media=(setup.size_name, setup.width_mm, setup.height_mm,
                           setup.orientation),
                    margins={key: getattr(setup, key) for key in MARGIN_KEYS},
                    keep_content=True)
        self.apply_page_setup(plan, indexes, preserve_view=True)

    def set_page_scale(self, scale: PageScale, pages: Optional[list] = None) -> None:
        """Give the current page — or each of *pages*, by index — this scale,
        units and precision (Set Scale's Pages; the user, 2026-10-15)."""
        if pages is None:
            self.current_page().scale = scale
        else:
            here = self.current_page()
            for index in pages:
                if not 0 <= index < len(self.document.pages):
                    continue
                page = self.document.pages[index]
                page.scale = PageScale.from_dict(scale.to_dict())
                if page is not here:
                    self.refresh_page_measurements(page)
            # each page's caption carries its scale; the pages picked in
            # Thumbnails stay picked
            picked = self.selected_pages()
            self.pages_panel.rebuild(self.document, self.current_index)
            self.pages_panel.pick(picked)
        self.apply_scale_change()

    def insert_pages_dialog(self, index: Optional[int] = None,
                            before: bool = False) -> "dialogs.InsertPagesDialog":
        """Revu's Insert Pages, placed Before or After page *index* (the page
        in view when none is named); not yet shown."""
        which = self.page_index(index)
        return dialogs.PdfImportDialog(self, self.current_page().setup,
                                       count=len(self.document.pages), page=which,
                                       after=not before)

    def insert_pdf(self, index: Optional[int] = None, before: bool = False) -> None:
        """Document ▸ Insert ▸ Pages…, and the Thumbnails menu's Insert Pages
        ▸ Before… / After…, which open the dialog placed there."""
        dialog = self.insert_pages_dialog(index, before)
        if dialog.exec() != dialogs.QDialog.Accepted:
            return
        self.finish_insert_pages(dialog, index, before)

    def finish_insert_pages(self, dialog, index: Optional[int] = None,
                            before: bool = False) -> None:
        """Bring in the pages *dialog* chose, where it placed them."""
        chosen = dialog.selection()
        # A dialog written before any of this says nothing about the last two,
        # and the answer to both is now fixed anyway: everything the file holds
        # comes across, at the best the sheet allows.
        path, indices, fit = chosen[:3]
        dpi = chosen[3] if len(chosen) > 3 else pdfio.BEST_DPI
        vectors = bool(chosen[4]) if len(chosen) > 4 else False
        if not path or not indices:
            QMessageBox.information(self, "Insert Pages", "No pages were selected.")
            return
        target = dialog.target() if hasattr(dialog, "target") \
            else self.page_index(index) + (0 if before else 1)
        target = max(0, min(target, len(self.document.pages)))
        if project_io.carries_a_document(path):
            self.insert_calcforge_pages(path, at=target, indices=indices)
            return
        brought: list = []

        def mutate():
            brought.extend(pdfio.import_pages(self.document, path, indices, fit,
                                              dpi, at=target, vectors=vectors,
                                              annotations=True))
            self.current_index = target
        try:
            self._structural_change(f"Insert {len(indices)} PDF page(s)", mutate)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Insert Pages", str(exc))
            return
        self.view.fit_page()
        lines = sum(len(page.frame.markups()) if page.frame is not None else 0
                    for page in brought)
        said = f"Inserted {len(indices)} page(s) from {os.path.basename(path)}"
        if vectors:
            said += (f" — {lines} pieces of line work came with them"
                     if lines else " — no line work could be read out of this one")
        self.status_hint.setText(said)

    def _calcforge_pages(self, path: str, indices=None) -> list:
        """The pages of a CalcForge file, as they are in it: its equations
        live, its markups markups, its drawings drawn from the file itself.
        Their assets come into this document with them."""
        import uuid
        other = Document()
        project_io.load_document(other, path)
        numbers = range(len(other.pages)) if indices is None else indices
        pages = [other.pages[i] for i in numbers if 0 <= i < len(other.pages)]
        taken = {page.uid for page in self.document.pages}
        for page in pages:
            if page.uid in taken:
                page.uid = uuid.uuid4().hex
            taken.add(page.uid)
        # its tables, equations and blocks are new ones here, even when the
        # same file comes in twice (each is known by its uid)
        from .sheetpages import fresh_item_ids
        entries = [{"items": page._pending_items, "sheet": page.sheet} for page in pages]
        fresh_item_ids(entries)
        for page, entry in zip(pages, entries):
            page._pending_items, page.sheet = entry["items"], entry["sheet"]
        for key, data in other.assets.items():
            self.document.assets.setdefault(key, data)
        self._say_what_opening_found(other.open_warnings)
        return pages

    def insert_calcforge_pages(self, path: str, at: Optional[int] = None,
                               indices=None) -> list:
        """Insert PDF, for a file written here: its equations come in live
        and join this document's reading order (decision 9)."""
        at = len(self.document.pages) if at is None else max(0, min(at, len(self.document.pages)))
        brought: list = []

        def mutate():
            brought.extend(self._calcforge_pages(path, indices))
            self.document.pages[at:at] = brought
            self.current_index = at
        self._structural_change(f"Insert {os.path.basename(path)}", mutate)
        self.status_hint.setText(
            f"Inserted {len(brought)} page(s) from {os.path.basename(path)}, equations and all")
        return brought

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
                    if path.lower().endswith(".pdf") and project_io.carries_a_document(path):
                        pages = self._calcforge_pages(path)
                        self.document.pages[at:at] = pages
                        added += len(pages)
                        at += len(pages)
                    elif path.lower().endswith(".pdf"):
                        pages = pdfio.import_pages(
                            self.document, path,
                            list(range(pdfio.page_count(path))),
                            pdfio.FIT_ORIGINAL, at=at, annotations=True)
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
        if page.sheet is not None:
            # a spreadsheet turns as a whole: portrait ⇄ landscape, and its
            # page breaks flow again; its markups stay on their cells
            from .sheetpages import turn_run
            turn_run(self, which)
            return
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
            page.turn = (page.turn + (90 if clockwise else -90)) % 360
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
                    if hasattr(item, "show_upright"):
                        # an equation or a table: turned about its corner,
                        # WebSMath's way, which its own layout reads back
                        position = item.pos()
                        if clockwise:
                            item.setPos(height - position.y(), position.x())
                            item.setRotation(item.rotation() + 90)
                        else:
                            item.setPos(position.y(), width - position.x())
                            item.setRotation(item.rotation() - 90)
                        continue
                    # Turned about its own centre, as every markup is (and
                    # as a reopened one is), and its centre carried to where
                    # the page's turn takes it: turned about its corner it
                    # came back from a save off to one side (2026-10-14).
                    centre = item.local_rect().center()
                    where = item.mapToParent(centre)
                    if clockwise:
                        landing = QPointF(height - where.y(), where.x())
                        turn = 90
                    else:
                        landing = QPointF(where.y(), width - where.x())
                        turn = -90
                    item.setTransformOriginPoint(centre)
                    item.setRotation(item.rotation() + turn)
                    item.setPos(item.pos() + landing - item.mapToParent(centre))
            self.current_index = which
        if self._structural_change("Rotate page", mutate):
            self.view.fit_page()
            self._note_view_after_change()

    def _rotate_background(self, page, clockwise: bool) -> str:
        """A quarter-turned copy of the page's sheet, if it has one.

        A page opened from a PDF keeps no picture of itself, so one is
        rendered here — turning it is what makes the turn permanent, and from
        that point the page is a raster rather than the source file.
        """
        image = pdfio.page_raster(self.document, page)
        if image is None or image.isNull():
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
        from .pagesetup import Plan
        which = self.page_index(index)
        page = self.document.pages[which]
        width, height = PAGE_SIZES.get(name, PAGE_SIZES["A4"])
        # the paper changes and what is on it stays where it is, as the Page
        # panel's paper boxes do; the file's page gets the same paper
        plan = Plan(media=(name, width, height, page.setup.orientation), keep_content=True)
        self.current_index = which
        self.apply_page_setup(plan, [which], description=f"Page size {name}")

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

        Revu's Thumbnails menu, in its order and with its names (QA round 4,
        audit A1): Page Setup…, Set Scale… | Cut, Copy and Paste Pages, and
        Move Up / Down beside them | every insert, Before or After, then
        Duplicate, Extract, Split, Delete, Crop and Rotate Pages, and the page
        labels | Print Pages… and whether the page prints | Flatten…,
        Unflatten, Colour Processing… — then CalcForge's own, in a group of
        their own at the end. Each family is together and named as on the
        Document menu (bug hunt E1–E14).

        The tooltips say which pages: with six sheets picked out, "Delete
        these 6 pages" is what Delete Pages does, so nothing is taken away by
        a command that read as being about one page.
        """
        from . import menutidy
        index = self.page_index(index)
        acting = self.pages_acted_on(index)
        several = len(acting) > 1
        these = f"these {len(acting)} pages" if several else "page"
        page = self.document.pages[index]
        menu = bindable.set_context(menu or QMenu(self), "page")

        def here(run):
            """*run* on this page: the page goes in view first, as the
            Document menu's commands act on the page in view."""
            return lambda _checked=False: (self.go_to_page(index), run())

        # -- page setup and scale ----------------------------------------------------
        menu.addAction("Page Setup…", here(self.page_setup))
        menu.addAction(self.act_scale.text(), here(self.calibrate_dialog)).setToolTip(
            self.act_scale.toolTip())
        menu.addSeparator()
        # -- the clipboard, and moving the pages along (E9) ----------------------------
        many = len(self.document.pages) > 1
        cut = menu.addAction("Cut Pages", lambda: self.cut_pages(index))
        cut.setToolTip(f"Copy {these}, then delete them")
        cut.setEnabled(many and len(acting) < len(self.document.pages))
        copy = menu.addAction("Copy Pages", lambda: self.copy_page(index))
        copy.setToolTip(f"Copy {these}")
        waiting = self.page_on_the_clipboard()
        paste = menu.addMenu("Paste Pages")
        paste.setToolTip("Paste the copied pages before or after this page"
                         if waiting is not None else "There is no page on the clipboard")
        before = paste.addAction("Before", lambda: self.paste_page(index, before=True))
        before.setToolTip(f"Paste the copied pages before page {index + 1}")
        after = paste.addAction("After", lambda: self.paste_page(index))
        after.setToolTip(f"Paste the copied pages after page {index + 1}")
        paste.setEnabled(waiting is not None)
        first, last = acting[0], acting[-1]
        up = menu.addAction("Move Up", lambda: self.move_page(first, first - 1, len(acting)))
        up.setToolTip(f"Move {these} one place towards the start")
        up.setEnabled(first > 0)
        down = menu.addAction("Move Down", lambda: self.move_page(first, first + 1, len(acting)))
        down.setToolTip(f"Move {these} one place towards the end")
        down.setEnabled(last < len(self.document.pages) - 1)
        menu.addSeparator()
        # -- insert, and the rest of what is done to pages ---------------------------
        # Every way of putting pages in, together and the same shape: each
        # one Before or After this page (the user, 2026-10-16), the same
        # family the Document menu's Insert ▸ offers (insert_family). On a
        # spreadsheet page Insert Spreadsheet Page is one more page of it.
        for entry in self.insert_family():
            self.fill_insert_choice(menu.addMenu(entry[1]), entry, index)
        duplicate = menu.addAction("Duplicate Pages" if several else "Duplicate Page",
                                   lambda: self.duplicate_page(index))
        duplicate.setToolTip(f"Duplicate {these}")
        extract = menu.addAction(self.act_extract_pages.text(),
                                 lambda: self._extract_from_menu(index))
        extract.setToolTip(f"Save {these} as a new PDF")
        split = menu.addAction(self.act_split_pages.text(), here(self.split_into_files))
        split.setToolTip(self.act_split_pages.toolTip())
        delete = menu.addAction(self.act_delete_page.text(), lambda: self.delete_page(index))
        delete.setToolTip(f"Delete {these}")
        delete.setEnabled(many)
        crop = menu.addAction(self.act_crop_page.text(), here(self.crop_pages))
        crop.setToolTip(self.act_crop_page.toolTip())
        turn = menu.addMenu("Rotate Pages")
        turn_cw = turn.addAction(self.act_rotate_pages_cw.text(),
                                 lambda: self.rotate_page(index, True))
        turn_cw.setToolTip("Turn the paper and everything drawn on it. To turn "
                           "only the way it is shown, use View ▸ Rotate View.")
        turn_acw = turn.addAction(self.act_rotate_pages_acw.text(),
                                  lambda: self.rotate_page(index, False))
        turn_acw.setToolTip("Turn the paper and everything drawn on it anticlockwise")
        if not several:
            rename = menu.addAction("Rename Page Label", lambda: self.rename_page(index))
            rename.setToolTip("Edit this page's label on its thumbnail (F2)")
            reset = menu.addAction("Reset Page Label", lambda: self.reset_page_label(index))
            reset.setToolTip("Restore the imported label, or the normal page number")
            reset.setEnabled(page.label != page.source_note.strip())
        every = menu.addAction("Reset All Page Labels", self.reset_all_page_labels)
        every.setToolTip("Every page back to its imported label, or the normal page number")
        every.setEnabled(any(p.label != p.source_note.strip() for p in self.document.pages))
        menu.addSeparator()
        # -- printing: the command and whether the page prints, together (E10) -----
        printing = menu.addAction("Print Pages…", lambda: self.print_pages(index))
        printing.setToolTip(f"Print {these}")
        include = menu.addAction("Include in Print && Export")
        include.setToolTip("Whether the page, or the pages picked out, are printed and "
                           "exported with the rest")
        include.setCheckable(True)
        include.setChecked(all(self.document.pages[i].printable for i in acting))
        include.toggled.connect(
            lambda on, chosen=tuple(acting): self.set_pages_printable(chosen, on))
        menu.addSeparator()
        # -- flatten and colour: the Document menu's group (E14, E15) ---------------
        menu.addAction(self.act_flatten_document)
        menu.addAction(self.act_recover_flattened)
        processing = menu.addAction(self.act_color_processing.text(),
                                    lambda: self.color_processing(index))
        processing.setEnabled(bool(page.background_key or page.pdf_key))
        menu.addSeparator()
        # -- CalcForge's own ------------------------------------------------------------
        go = menu.addAction("Go to Page", lambda: self._go_to_page_asked(index))
        go.setToolTip("Go to this page")
        bookmark = menu.addAction(self.act_bookmark.text(), lambda: self.bookmark_page(index))
        bookmark.setToolTip("Add this page to the document bookmarks")
        if page.sheet is not None:
            layout = menu.addAction(self.act_sheet_page_setup.text(),
                                    lambda: self.sheet_page_setup(index))
            layout.setToolTip("Print area, titles, fit to page width, centring, gridlines")
        from . import calcsections
        calcsections.add_menu(self, menu, index)
        grid = menu.addAction("Page Grid")
        grid.setCheckable(True)
        grid.setChecked(page.shows_a_grid(self.document.settings))
        grid.setToolTip("A grid belongs to the page it is on, and prints with "
                        "it.\nPages that came in from a PDF start without one.")
        grid.toggled.connect(lambda on, i=index: self.set_page_grid(i, on))
        running = menu.addMenu("Header/Footer")
        for which, label in (("header", "Show Header"), ("footer", "Show Footer")):
            entry = running.addAction(label)
            entry.setCheckable(True)
            entry.setChecked(getattr(page, f"shows_a_{which}")(self.document.settings))
            entry.toggled.connect(
                lambda on, i=index, w=which: self.set_page_running_text(i, w, on))
        running.addSeparator()
        wording = running.addAction(self.act_header_footer.text(), self.edit_header_footer)
        wording.setToolTip("Edit the document's header and footer wording")
        paper = menu.addMenu("Paper Size")
        for name in PAGE_SIZES:
            entry = paper.addAction(name, lambda n=name: self.set_page_size(index, n))
            entry.setCheckable(True)
            entry.setChecked(page.setup.size_name == name)
        editable = menu.addAction("Make This Page's Markups Editable",
                                  lambda: self.make_markups_editable(index))
        editable.setToolTip(
            "Read the clouds, call-outs and dimensions already on this page "
            "out of the PDF\nand turn them into markups you can move and "
            "change. What is read out is\nCalcForge's drawing of them, so it "
            "will not match the file exactly.")
        editable.setEnabled(bool(page.pdf_key) and page.pdf_annotations)
        return menutidy.tidy(menu)

    def cut_pages(self, index: Optional[int] = None) -> None:
        """Revu's Cut Pages: the pages copied, then deleted (one undo step)."""
        going = self.pages_acted_on(index)
        if len(going) >= len(self.document.pages):
            self.status_hint.setText("A document needs at least one page")
            return
        self.copy_page(index)
        self.delete_page(index, ask=False)
        numbers = ", ".join(str(i + 1) for i in going)
        self.status_hint.setText(f"Cut page{'s' * (len(going) > 1)} {numbers} — "
                                 "Paste Pages puts " + ("them" if len(going) > 1 else "it") + " in again")

    def reset_all_page_labels(self) -> None:
        """Revu's Reset All Page Labels: every page back to its imported
        label, or to its plain number; one undo step."""
        changed = [(page, page.source_note.strip()) for page in self.document.pages
                   if page.label != page.source_note.strip()]
        if not changed:
            return

        def mutate():
            for page, restored in changed:
                page.label = restored

        self._structural_change("Reset all page labels", mutate, preserve_view=True)

    def print_pages(self, index: Optional[int] = None) -> "PrintDialog":
        """Revu's Print Pages…: the Print dialog with these pages chosen —
        Selected, the run picked out in Thumbnails or the page right-clicked."""
        chosen = self.pages_acted_on(index)
        return self.open_print_dialog(chosen, "selected")

    def rename_page(self, index: int) -> None:
        """Revu's Rename Page Label: the label is edited in place on the page's
        thumbnail (F2 there does the same). Should the Thumbnails panel not be
        showable, a small Rename Page Label box asks instead."""
        index = self.page_index(index)
        if index != self.current_index:
            self.go_to_page(index)             # Revu re-labels the current page
        self.show_panel("dock_pages", True)
        if self.pages_panel.isVisible() and self.pages_panel.edit_label(index) is not None:
            return
        page = self.document.pages[index]
        label, accepted = QInputDialog.getText(
            self, "Rename Page Label", "Label:", text=page.label)
        if accepted:
            self.set_page_label(index, label)

    def set_page_label(self, index: int, label: str) -> None:
        """Give one page the label shown in Thumbnails; one undo step."""
        if not 0 <= index < len(self.document.pages):
            return
        page = self.document.pages[index]
        label = (label or "").strip()
        if label == page.label or (label == str(index + 1) and not page.label):
            return

        def mutate():
            page.label = label

        self._structural_change("Rename page label", mutate, preserve_view=True)

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
    def scale_dialog(self, measured_pt: Optional[float] = None) -> "dialogs.ScaleDialog":
        """Revu's Set Scale for the page in view; not yet shown.

        After Calibrate's two points (*measured_pt*), it comes back as it was
        left, with the measured length on the left of the scale.
        """
        state = getattr(self, "_scale_dialog_state", None) if measured_pt else None
        self._scale_dialog_state = None
        picked = self.selected_pages()
        return dialogs.ScaleDialog(
            self.current_page().scale, measured_pt, self,
            count=len(self.document.pages), current=self.current_index,
            selected=picked if len(picked) > 1 else [], state=state)

    def calibrate_scale(self, measured_pt: Optional[float] = None) -> None:
        """Set Scale (the user, 2026-10-15): a preset, a custom scale, or —
        after Calibrate's two points — the length they measure."""
        dialog = self.scale_dialog(measured_pt)
        answer = dialog.exec()
        if answer == dialogs.ScaleDialog.PICK:
            # Calibrate: two clicks, then this dialog again as it was left
            self._scale_dialog_state = dialog.state()
            self.start_calibrating()
            return
        if answer != dialogs.QDialog.Accepted:
            return
        self.finish_scale(dialog)

    def finish_scale(self, dialog) -> bool:
        """Apply Scale: *dialog*'s scale on the pages it chose."""
        scale = dialog.result_scale()
        if scale is None:
            return False
        pages = dialog.page_indexes() if hasattr(dialog, "page_indexes") else None
        if not pages:
            return False
        self.set_page_scale(scale, pages)
        return True

    def calibrate_dialog(self) -> None:
        self.calibrate_scale(None)

    # -- viewports ---------------------------------------------------------
    def add_viewport(self, frame, region: QRectF, scale: Optional[PageScale] = None,
                     name: str = "") -> bool:
        """Make *region* of the page a viewport with a scale of its own."""
        from ..core.document import Viewport
        if frame is None:
            return False
        page = frame.page
        region = QRectF(region).normalized().intersected(frame.page_rect())
        if region.width() < 4 or region.height() < 4:
            self.status_hint.setText("Viewport: drag the region drawn at its own scale")
            return False
        name = name or f"Viewport {len(page.viewports) + 1}"
        if scale is None and not self.interactive_prompts:
            scale = PageScale.from_dict(page.scale.to_dict())
        if scale is None:
            dialog = dialogs.ScaleDialog(page.scale, None, self, name=name)
            if dialog.exec() != dialogs.QDialog.Accepted:
                return False
            scale = dialog.result_scale()
            if scale is None:
                return False
            name = dialog.name.text().strip() or name
        viewport = Viewport(name, region.x(), region.y(), region.width(),
                            region.height(), scale)
        self._change_viewports(page, page.viewports + [viewport], "Add viewport")
        if page.frame is not None:
            page.frame.set_active_viewport(page.viewports[-1])
        self.status_hint.setText(
            f"{name} at {scale.label} — measurements inside it use that scale")
        return True

    def edit_viewport(self, page, viewport) -> bool:
        """Rename a viewport or change its scale."""
        dialog = dialogs.ScaleDialog(viewport.scale, None, self, name=viewport.name)
        if dialog.exec() != dialogs.QDialog.Accepted:
            return False
        scale = dialog.result_scale()
        if scale is None:
            return False
        from ..core.document import Viewport
        changed = [Viewport(dialog.name.text().strip() or v.name, v.x, v.y, v.width,
                            v.height, scale) if v is viewport else v
                   for v in page.viewports]
        self._change_viewports(page, changed, "Change viewport")
        return True

    def delete_viewport(self, page, viewport) -> None:
        self._change_viewports(page, [v for v in page.viewports if v is not viewport],
                               "Delete viewport")

    def _change_viewports(self, page, viewports: list, text: str) -> None:
        from .commands import ViewportsCommand
        before = [v.to_dict() for v in page.viewports]
        after = [v.to_dict() for v in viewports]
        self.undo_stack.push(ViewportsCommand(
            page, before, after, text, self._viewports_changed,
            find_page=lambda uid: next((p for p in self.document.pages if p.uid == uid), None)))

    def _viewports_changed(self, page) -> None:
        """Measurements re-read against the new regions, and the page redrawn."""
        self.refresh_page_measurements(page)
        if page.frame is not None:
            page.frame.update()
        self.page_panel.refresh()
        self.refresh_lists()
        self.refresh_selection()
        self.mark_modified()

    def viewports_dialog(self) -> None:
        """Every viewport on this page: change one's scale, or delete it."""
        page = self.current_page()
        if not page.viewports:
            # not a dead end (F-35): the way to make one is offered
            words = ("This page has no viewports yet. A viewport is a region of "
                     "the sheet drawn at its own scale: drag one out with the "
                     "Viewport tool.")
            if not self.interactive_prompts:
                self.status_hint.setText(words)
                return
            box = QMessageBox(QMessageBox.Information, "Viewports", words,
                              QMessageBox.Cancel, self)
            draw = box.addButton("Draw a Viewport", QMessageBox.AcceptRole)
            box.setDefaultButton(draw)
            box.exec()
            if box.clickedButton() is draw:
                self.select_tool("viewport")
            return
        dialog = dialogs.ViewportsDialog(self, page)
        dialog.exec()

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
        # Every value already on the page is re-read in the new scale and
        # unit, so changing the unit changes the dimensions drawn with it.
        self.refresh_page_measurements(self.current_page())
        # Measurements and rectangle sizes are in the takeoff list too, so it
        # goes stale unless it is rebuilt with them.
        self.refresh_lists()
        self.refresh_selection()
        self.mark_modified()

    def spelling_mistakes(self) -> list:
        """Every misspelt word in the document's text markups, in page order.

        Each is (item, start, length, word); positions are in the item's
        plain text.
        """
        from ..core.spelling import shared

        checker = shared()
        found = []
        for page in self.document.pages:
            frame = page.frame
            if frame is None:
                continue
            for item in frame.markups():
                if not isinstance(item, _TextBase) or item.locked:
                    continue
                text = item.doc.toPlainText()
                for start, length, word in checker.mistakes(text):
                    found.append((item, start, length, word))
        return found

    def check_spelling(self) -> int:
        """Walk every misspelt word in the document, as Bluebeam's F7 does.

        Returns how many words were changed.
        """
        from PySide6.QtGui import QTextCursor
        from ..core.spelling import remember, shared

        self.view.end_item_edit()
        mistakes = self.spelling_mistakes()
        if not mistakes:
            self.status_hint.setText("Spelling: no mistakes found")
            if self.interactive_prompts:
                QMessageBox.information(self, "Check Spelling",
                                        "No spelling mistakes were found.")
            return 0
        checker = shared()
        ignored: set = set()
        # Change All: the word, lower-cased, to what every later one becomes
        always: dict = {}
        changed = 0
        shift: dict = {}
        # each word's box is picked out while it is asked about; afterwards
        # the selection is what it was (F-29: the last box was left picked,
        # its frame round the words)
        was_selected = [item for item in self.scene.selectedItems()]
        self.view.begin_snapshot(self.view.all_frames())
        for item, start, length, word in mistakes:
            key = word.lower()
            if key in ignored or (key not in always and checker.knows(word)):
                continue
            at = start + shift.get(id(item), 0)
            if key in always:
                replacement = always[key]
            else:
                self.scene.clearSelection()
                item.setSelected(True)
                self.view.ensureVisible(item)
                dialog = dialogs.SpellingDialog(word, item.doc.toPlainText(), at,
                                                checker.suggestions(word), self)
                answer = dialog.exec() if self.interactive_prompts else 0
                action = dialog.choice if answer else "stop"
                if action == "stop":
                    break
                if action == "ignore_once":
                    continue
                if action in ("ignore", "ignore_all"):
                    ignored.add(key)
                    continue
                if action == "add":
                    remember(word)
                    continue
                replacement = dialog.replacement()
                if action == "change_all" and replacement:
                    always[key] = replacement
            if not replacement or replacement == word:
                continue
            cursor = QTextCursor(item.doc)
            cursor.setPosition(at)
            cursor.setPosition(at + length, QTextCursor.KeepAnchor)
            cursor.insertText(replacement)
            item.written = item.doc.toPlainText()
            if hasattr(item, "refresh_layout"):
                item.refresh_layout()
            item.update()
            shift[id(item)] = shift.get(id(item), 0) + len(replacement) - length
            changed += 1
        if changed:
            self.view.commit_snapshot("Check spelling")
        else:
            self.view.forget_snapshot()
        import shiboken6
        self.scene.clearSelection()
        for item in was_selected:
            if shiboken6.isValid(item) and item.scene() is self.scene:
                item.setSelected(True)
        self.view.selectionChanged.emit()
        self.status_hint.setText(f"Spelling: {changed} word(s) changed")
        return changed

    def refresh_page_measurements(self, page) -> None:
        """Re-read every measured value on *page* from its current scale."""
        for frame in (self.scene.frames if self.scene is not None else []):
            if getattr(frame, "page", None) is not page:
                continue
            for item in frame.markups():
                if isinstance(item, MeasureItem) or (
                        isinstance(item, RectItem) and item.kind in SIZED_SHAPES):
                    item.refresh(page=page)

    def set_area_unit(self, unit: str) -> None:
        if unit:
            self.current_page().scale.area_unit = unit
            self.refresh_page_measurements(self.current_page())
            self.refresh_lists()
            self.mark_modified()

    def refresh_scale_label(self) -> None:
        from shiboken6 import isValid
        if not isValid(self.status_scale):
            return                      # a last scroll as the window closes
        panel = getattr(self, "page_panel", None)
        if panel is not None and isValid(panel):
            try:
                panel.refresh()
            except RuntimeError:        # its fields already gone with the window
                pass
        self.view.tables.refresh_bar()      # a spreadsheet page in view keeps the formula bar
        tabs = getattr(self, "sheet_tabs", None)
        if tabs is not None:
            tabs.refresh()                  # and its tab is the current one
        scale = self.current_page().scale
        # Revu's "Scale Not Set" (novice 12): a page nobody has scaled must
        # not look as if it measured 1:1
        if scale.is_calibrated():
            self.status_scale.setText(f"Scale {scale.label}")
            self.status_scale.setToolTip(
                f"1 page point = {format_quantity(scale.length_per_pt, 5)}\n"
                "Click to change (Set Scale…)")
        else:
            self.status_scale.setText("Scale Not Set")
            self.status_scale.setToolTip("This page has no scale: measurements are paper "
                                         "distances.\nClick to set one (Set Scale…)")
        self.refresh_page_bar()

    def refresh_page_bar(self) -> None:
        """The bar along the bottom, saying what this page is."""
        total = len(self.document.pages)
        self.page_total.setText(f"of {total}")
        self.page_spin.setSuffix(f" of {total}")
        self.page_back.setEnabled(self.current_index > 0)
        self.page_forward.setEnabled(self.current_index < total - 1)
        self.page_first.setEnabled(self.current_index > 0)
        self.page_last.setEnabled(self.current_index < total - 1)
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
            # Select answers to Escape and to Revu's V; the tooltip says both.
            spoken = [sequence] + [
                self.shortcuts.sequence(b.action_id) for b in self.shortcuts.bindings()
                if b.kind == TOOL and b.payload == tool_key
                and b.action_id != f"tool.{tool_key}"]
            spoken = ", ".join(text for text in spoken if text)
            hint = f"  ({spoken})" if spoken else ""
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
            action.setShortcuts(self._keys_for(key, sequence))
        for action_id, action in getattr(self, "symbol_actions", {}).items():
            action.setShortcut(QKeySequence(self.shortcuts.sequence(action_id)))
        self._apply_mode_keys()
        self.commands.refresh_buttons()

    #: Where a command with no group of its own is filed in Keyboard
    #: Shortcuts: under the menu it is on.
    MENU_CATEGORIES = {"CalcForge": "File", "File": "File", "Edit": "Edit", "View": "View",
                       "Document": "Document", "Batch": "Document", "Tools": "Markup",
                       "Calculation": "Calculation", "Window": "Window", "Help": "Help"}
    SUBMENU_CATEGORIES = {("Tools", "Measure"): "Measure", ("Tools", "Toolbars"): "Window",
                          ("Tools", "Tool Chest"): "Panels", ("Window", "Panels"): "Panels",
                          ("Document", "Insert"): "Pages", ("Document", "Rotate Pages"): "Pages",
                          ("Edit", "Order"): "Order", ("Edit", "Alignment"): "Order",
                          ("Edit", "Text"): "Text", ("Calculation", "Page Layout"): "Spreadsheet"}

    def _file_commands_by_menu(self) -> None:
        """Give each command registered without a group the group of the
        menu it is on, so the shortcut list reads like the menu bar."""
        from .shortcuts import BY_ID
        for key, action_id in self.action_ids.items():
            binding = BY_ID.get(action_id)
            if binding is None or binding.category:
                continue
            action = getattr(self, f"act_{key}", None)
            category = ""
            for owner in (action.associatedObjects() if action is not None else []):
                if isinstance(owner, QMenu):
                    path = self.commands.menu_path(owner)
                    if path:
                        category = (self.SUBMENU_CATEGORIES.get(tuple(path[:2]))
                                    or self.MENU_CATEGORIES.get(path[0], ""))
                        if category:
                            break
                elif isinstance(owner, QToolBar) and not category:
                    category = {"Calculation": "Calculation", "Measure": "Measure",
                                "Properties": "Markup"}.get(owner.windowTitle(), "")
            self.shortcuts.recategorise(action_id, category or "Other")

    def insert_symbol(self, text: str) -> None:
        """Put a symbol in at the cursor, wherever the cursor is."""
        if self.view.insert_symbol(text):
            return
        self.status_hint.setText(
            f"{text} has nowhere to go — start typing a markup first")

    def run_typed_binding(self, text: str, modifiers, position: QPointF) -> bool:
        """Act on a bare keystroke over the canvas; False if nothing is bound."""
        binding = self.shortcuts.match_typed(text, modifiers, self.view.calc.mode)
        if binding is None:
            return False
        if binding.kind == INSERT and binding.payload in ("equation", "calc_text", "plot"):
            frame = self.view.frame_at(position) or self.view.frame()
            if frame is not None:
                self.view.calc.insert(binding.payload, frame, frame.mapFromScene(position))
            return True
        if binding.kind == INSERT:
            self._insert_at(binding.payload, position)
            return True
        if binding.kind == TOOL:
            self.select_tool(binding.payload)
            return True
        if binding.kind == COMMAND:
            method = getattr(self, binding.payload, None) if binding.payload else None
            if callable(method):
                method()
                return True
            # a window command given a single character as its key
            for key, action_id in self.action_ids.items():
                action = getattr(self, f"act_{key}", None)
                if action_id == binding.action_id and action is not None:
                    if action.isEnabled():
                        action.trigger()
                    return True
        if binding.kind == "menu":
            # a menu entry's or a button's (bindable.py)
            self.commands.run(binding.action_id)
            return True
        if binding.kind == TYPED_SYMBOL:
            self.insert_symbol(binding.payload)
            return True
        return False

    def edit_shortcuts(self) -> None:
        """Keyboard Shortcuts: every command, each key working as it is set."""
        dialog = dialogs.ShortcutManagerDialog(self.shortcuts, self)
        dialog.exec()
        dialog.apply()
        self.shortcuts.save()
        self.apply_shortcuts()
        self.status_hint.setText("Shortcuts updated")
        dialog.deleteLater()

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
        if key != self.view.tool_key:
            self.view.clear_pending_tool()
        if key != "crop":
            # Crop Pages' Get Window was given up: the Crop tool crops again
            self._crop_dialog_state = None
        pending = getattr(self, "_page_setup_state", None)
        if pending is not None and key != "calibrate":
            # Page Setup's Get Line given up (Esc, another tool): the dialog
            # comes back as it was left, as Revu's does
            self._page_setup_state = None
            QTimer.singleShot(0, lambda: self.page_setup(state=pending))
        self.put_the_format_painter_down()
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

    def record_slowdowns(self, on: bool) -> None:
        """Help ▸ Record slow-downs (ui/stallwatch.py)."""
        from . import stallwatch
        stallwatch.toggle(self, on)

    PAGE_LAYOUTS = {"single": "Single Page", "continuous": "Continuous",
                    "side": "Side-by-Side", "continuous_side": "Continuous Side-by-Side"}

    def set_scroll_mode(self, mode: str) -> None:
        """One page at a time ("page") or every page ("continuous"), keeping
        whether pages lie side by side."""
        paired = self.scene.page_mode in ("side", "continuous_side")
        if mode == "page":
            self.set_page_layout("side" if paired else "single")
        else:
            self.set_page_layout("continuous_side" if paired else "continuous")

    def set_page_layout(self, mode: str) -> None:
        """Revu's page layouts (View menu). Only how the pages lie on the
        screen changes; the document does not."""
        if mode not in self.PAGE_LAYOUTS:
            mode = "continuous"
        index = self.current_index
        self.scene.set_page_mode(mode, index)
        label = self.PAGE_LAYOUTS[mode]
        self.status_scroll.setText(label)
        getattr(self, f"act_layout_{mode}").setChecked(True)
        if mode == "single":
            self.view.fit_page()              # Revu fits a single page to the window
        self.view.go_to_page_top(index)
        self.status_hint.setText(label)

    def _show_page_layout(self) -> None:
        """The layout controls showing the layout of the document in view."""
        if self.scene is None or not hasattr(self, "status_scroll"):
            return
        mode = getattr(self.scene, "page_mode", "continuous")
        self.status_scroll.setText(self.PAGE_LAYOUTS.get(mode, "Continuous"))
        getattr(self, f"act_layout_{mode}").setChecked(True)
        self.act_cover_page.blockSignals(True)
        self.act_cover_page.setChecked(bool(getattr(self.scene, "cover_page", False)))
        self.act_cover_page.blockSignals(False)

    def show_rulers(self, on: bool) -> None:
        from ..settings import app_settings
        self.view.rulers.show(on)
        app_settings().setValue("view/rulers", bool(on))

    def show_crosshair(self, on: bool) -> None:
        from ..settings import app_settings
        self.view.crosshair.show(on)
        app_settings().setValue("view/crosshair", bool(on))

    def set_dimmer(self, on: bool) -> None:
        """View ▸ Dimmer ▸ Dim Content (Revu's Ctrl+F5): every open drawing."""
        from .scene import DIMMER
        DIMMER["on"] = bool(on)
        self._repaint_all_pages()
        for other in list(type(self)._windows):
            if other is not self and other.act_dim_content.isChecked() != bool(on):
                other.act_dim_content.blockSignals(True)
                other.act_dim_content.setChecked(bool(on))
                other.act_dim_content.blockSignals(False)

    def set_dimmer_level(self, percent: int) -> None:
        """How strongly the content still shows while dimmed: Revu's 0–100 %."""
        from .scene import DIMMER
        DIMMER["level"] = max(0, min(100, int(percent))) / 100.0
        if not self.act_dim_content.isChecked():
            self.act_dim_content.setChecked(True)          # choosing a level dims
        else:
            self._repaint_all_pages()

    def _repaint_all_pages(self) -> None:
        for other in list(type(self)._windows):
            for state in getattr(other, "_open_documents", []) or []:
                scene = state.get("scene") if isinstance(state, dict) else None
                for frame in getattr(scene, "frames", []) or []:
                    frame.update()
            for frame in getattr(other.scene, "frames", []) or []:
                frame.update()

    def offset_toolbar(self):
        bar = getattr(self, "_offset_bar", None)
        if bar is None:
            from .offset import build_toolbar
            bar = self._offset_bar = build_toolbar(self)
            self.addToolBarBreak()
            self.addToolBar(Qt.TopToolBarArea, bar)
        return bar

    def end_canvas_sessions(self, view) -> None:
        """*view*'s canvas is going (another document in its place, or the
        canvas taken apart): nothing begun on it may outlive it.

        An Offset session went on watching the view's mouse and drew its
        preview into the canvas that had been taken apart — the next drag
        crashed the application (QA F-01). The Search panel's hits pointed
        at the old pages and its marks stayed drawn on every later document
        (QA F-04)."""
        offset = getattr(self, "_offset", None)
        if offset is not None and getattr(offset, "view", None) is view:
            offset.finish()
        panel = getattr(self, "search_panel", None)
        if panel is not None and view is getattr(self, "view", None):
            panel.forget()

    def start_offset(self):
        """Edit ▸ Offset (O)."""
        from .offset import OffsetSession, can_offset
        if getattr(self, "_offset", None) is not None:
            self._offset.finish()
        chosen = [i for i in self.scene.selectedItems() if isinstance(i, MarkupItem)]
        if len(chosen) != 1 or not can_offset(chosen[0]):
            self.status_hint.setText("Offset: select one line, polyline, polygon, shape "
                                     "or length/area measurement first")
            return None
        self._offset = OffsetSession(self, chosen[0])
        return self._offset

    def crop_image_region(self, frame, region) -> bool:
        """Revu's Crop Image: the selected image markup (or the one under the
        dragged rectangle) keeps what the rectangle covers. One undo step."""
        if frame is None:
            return False
        from ..items.media import ImageItem
        area = frame.mapRectToScene(region.normalized())
        images = [i for i in self.scene.selectedItems() if isinstance(i, ImageItem)]
        if not images:
            images = [i for i in frame.markups() if isinstance(i, ImageItem)
                      and i.sceneBoundingRect().intersects(area)]
        images = [i for i in images if i.sceneBoundingRect().intersects(area)][:1]
        if not images:
            self.status_hint.setText("Crop Image: drag over an image markup — select it first")
            return False
        image = images[0]
        keep = image.mapFromScene(area).boundingRect()
        self.view.begin_snapshot(self.view.involved_frames(image))
        done = image.crop_to(keep)
        image.touch()
        self.view.commit_snapshot("Crop Image")
        if done:
            self.scene.clearSelection()
            image.setSelected(True)
            self.status_hint.setText("Image cropped — Undo brings the rest back")
        return done

    def colour_changeable(self, item=None) -> list:
        """The markups Change Colors works on: those picked out together, and
        the whole group of a grouped one however it was picked (the user,
        2026-10-15: a group — or several — is the one time markups change
        colour together; a page's colour change never touches them)."""
        found = [m for m in self.scene.selectedItems()
                 if isinstance(m, MarkupItem) and getattr(m, "style", None) is not None]
        for one in list(found) + ([item] if item is not None else []):
            if isinstance(one, MarkupItem) and getattr(one, "group", ""):
                for member in self.view.group_of(one):
                    if member not in found and getattr(member, "style", None) is not None:
                        found.append(member)
        return found

    def change_multiple_colors(self, items=None) -> int:
        from .changecolors import change_multiple_colors
        items = items if items is not None else self.colour_changeable()
        return change_multiple_colors(self, items) if items else 0

    def _fill_undo_history(self) -> None:
        menu = self.undo_history_menu
        menu.clear()
        stack = self.undo_stack
        done = stack.index()
        if done == 0:
            nothing = menu.addAction("Nothing to undo")
            nothing.setEnabled(False)
            return
        for index in range(done - 1, max(-1, done - 41), -1):
            text = stack.text(index) or "Change"
            bindable.data_entry(menu.addAction(text, lambda i=index: self.undo_to(i)))

    def undo_to(self, index: int) -> None:
        """Undo the change at *index* in the history and every one after it."""
        self.view.end_item_edit()
        self.view.cancel_draft()
        if 0 <= index < self.undo_stack.index():
            self.undo_stack.setIndex(index)

    def set_full_screen(self, on: bool) -> None:
        """Window ▸ Full Screen (F11)."""
        if on:
            self._before_full_screen = self.isMaximized()
            self.showFullScreen()
        elif self.isFullScreen():
            self.showMaximized() if getattr(self, "_before_full_screen", False) else self.showNormal()

    def set_presentation(self, on: bool) -> None:
        """Window ▸ Presentation (Ctrl+Enter): the page alone, a page at a
        time, over the whole screen; Esc puts everything back."""
        if on and getattr(self, "_presenting", None) is None:
            self._presenting = {
                "state": self.saveState(),
                "menu": self.menuBar().isVisible(),
                "status": self.statusBar().isVisible(),
                "tabs": self.document_tabs.isVisible(),
                "layout": self.scene.page_mode,
                "zoom": self.view.zoom(),
                "full": self.isFullScreen(),
                "maximized": self.isMaximized(),
                "rulers": self.view.rulers.on,
                "bars": [(bar, bar.isVisible()) for bar in self.toolbars],
                # Split View: only the view in hand is presented
                "panes": [pane.widget for pane in self._panes
                          if pane is not self._active_pane],
            }
            for widget in self._presenting["panes"]:
                widget.hide()
            for toolbar in self.toolbars:
                toolbar.hide()
            for dock in self.panels:
                dock.hide()
            from PySide6.QtWidgets import QDockWidget
            for child in self.findChildren(QDockWidget):
                child.hide()
            self.menuBar().hide()
            self.statusBar().hide()
            self.document_tabs.hide()
            self.view.rulers.show(False)
            self.set_page_layout("single")
            self.showFullScreen()
            self.view.setFocus(Qt.OtherFocusReason)
            QApplication.instance().installEventFilter(self._presentation_keys())
            QTimer.singleShot(0, self.view, self.view.fit_page)
        elif not on and getattr(self, "_presenting", None) is not None:
            was, self._presenting = self._presenting, None
            QApplication.instance().removeEventFilter(self._presentation_keys())
            self.menuBar().setVisible(was["menu"])
            self.statusBar().setVisible(was["status"])
            self.document_tabs.setVisible(was["tabs"])
            from shiboken6 import isValid
            for widget in was.get("panes", []):
                if isValid(widget):
                    widget.show()
            self.restoreState(was["state"])
            for toolbar, shown in was["bars"]:
                toolbar.setVisible(shown)
            self.set_page_layout(was["layout"])
            self.view.rulers.show(was["rulers"])
            if not was["full"]:
                self.showMaximized() if was["maximized"] else self.showNormal()
            self.view.set_zoom(was["zoom"])
            self.view.go_to_page_top(self.current_index)
            self.act_presentation.blockSignals(True)
            self.act_presentation.setChecked(False)
            self.act_presentation.blockSignals(False)

    def _presentation_keys(self):
        keys = getattr(self, "_presentation_filter", None)
        if keys is None:
            window = self

            class _Keys(QObject):
                def eventFilter(self, _watched, event):
                    if window._presenting is None or event.type() != QEvent.KeyPress:
                        return False
                    key = event.key()
                    if key == Qt.Key_Escape:
                        window.set_presentation(False)
                        return True
                    step = {Qt.Key_Right: 1, Qt.Key_Down: 1, Qt.Key_PageDown: 1, Qt.Key_Space: 1,
                            Qt.Key_Left: -1, Qt.Key_Up: -1, Qt.Key_PageUp: -1,
                            Qt.Key_Backspace: -1}.get(key)
                    if step:
                        window.go_to_page(window.current_index + step)
                        window.view.fit_page()
                        return True
                    return False
            keys = self._presentation_filter = _Keys(self)
        return keys

    def set_cover_page(self, on: bool) -> None:
        self.scene.cover_page = bool(on)
        self.scene.layout_pages()
        self.view.go_to_page_top(self.current_index)


    def _refresh_style_controls(self) -> None:
        """Show only style controls meaningful for the selection or tool."""
        if not hasattr(self, "_style_widgets"):
            return
        tables = self.view.tables
        if tables.is_open():
            # a table open for its cells: its own controls, in the same bar
            for actions in self._style_widgets.values():
                for action in actions:
                    action.setVisible(False)
            item = tables.item
            self.style_kind_label.setText(item.name)
            self.style_kind_menu.setToolTip(item.name)
            self.style_kind_menu.set_face(picture=icon("table", 20))
            self.table_controls.show(True)
            self.table_controls.sync()
            self.style_bar.layout().invalidate()
            self.style_bar.layout().activate()
            self._style_bar_tables = True   # the bar's own controls come back next time
            return
        if hasattr(self, "table_controls"):
            self.table_controls.show(False)
        items = self.selected_items()
        active = items[0] if items else None
        self._style_own_look = False
        if items:
            supported = common_capabilities(items)
        else:
            active = self._style_default_item()
            if active is not None and getattr(self, "markup_styles", None) is not None:
                self.markup_styles.dress(active)     # a markup style being edited
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
        # The bar never comes and goes (the page would jump under it): with
        # nothing that takes a style, the everyday controls stay, greyed out.
        idle = not supported
        shown = set(supported or {STROKE, FILL, FILL_OPACITY, WIDTH, DASH, OPACITY})
        from . import propbar
        shown |= propbar.extras_shown(items, active, supported)
        if isinstance(active, MeasureItem) and active.kind in ("area", "volume"):
            # Revu's area bar has no Font (its caption's font is in the
            # Properties panel): Line, Fill, Hatch, Units, Caption, Totals
            shown.discard(FONT)
        if items:
            names = {self._type_name(i) for i in items}
            kind = names.pop() if len(names) == 1 else f"{len(items)} markups"
        else:
            kind = (f"New {self._type_name(active).lower()}" if active is not None
                    else "Nothing selected")
            styles = getattr(self, "markup_styles", None)
            if active is not None and styles is not None and styles.editing():
                kind = f"{self._type_name(active)} style {styles.editing()}"
        self.style_kind_label.setText(kind)
        self.style_kind_menu.setToolTip(f"{kind} — Subject, and more")
        tool_key = "" if items else self.view.tool_key
        self.style_kind_menu.set_face(picture=propbar.kind_icon(
            self, active if items else None, tool_key if active is not None else ""))
        # what the field groups say, less the parts a markup does not have:
        # a contents list's font is its own, a callout has no start
        hidden = set()
        if isinstance(active, ContentsItem):
            hidden.add(self.font_family_combo)
        if isinstance(active, CalloutItem):
            hidden |= {self.arrow_start_combo, self.arrow_start_label_action,
                       self.arrow_start_size_spin}
        # Revu shows an end's size only once the end has something drawn on it
        if active is not None and active.style.arrow_start == "none":
            hidden.add(self.arrow_start_size_spin)
        if active is not None and active.style.arrow_end == "none":
            hidden.add(self.arrow_size_spin)
        # a cloud's line styles are drawn as its scallops, as Revu's are
        cloud = CLOUD in supported
        if bool(self.dash_combo.property("cloudStyles")) != cloud:
            fill_line_style_combo(self.dash_combo, _bar_ink(), 1,
                                  active.style.line_style if active is not None else "",
                                  cloud)
        changed = False
        for field, actions in self._style_widgets.items():
            for action in actions:
                wanted = (field in shown and action not in hidden
                          and action.defaultWidget() not in hidden)
                if action.isVisible() != wanted:
                    action.setVisible(wanted)
                    changed = True
                action.setEnabled(not idle)
        self.text_align_combo.setVisible(FONT in supported and isinstance(active, _TextBase))
        self._align_label.setVisible(self.text_align_combo.isVisibleTo(self.font_style_popup))
        self.default_button.setEnabled(bool(supported) and len(items) == 1)
        if TOTALS_GROUP in shown:
            self._fill_totals(items)
        if not self.style_bar.isVisibleTo(self):
            self.style_bar.setVisible(True)
            changed = True
        if changed or getattr(self, "_style_bar_tables", False):
            # which controls it holds changed: lay it out again (it used to
            # be hidden and shown, which did this as a side effect). Not when
            # nothing came or went: laying the bar out was a quarter of
            # picking a tool or a markup (novice finding 25).
            self.style_bar.layout().invalidate()
            self.style_bar.layout().activate()
        self._style_bar_tables = False
        if active is None:
            return
        controls = ((self.stroke_button, active.style.stroke, "set_color"),
                    (self.fill_button, active.style.fill, "set_color"),
                    (self.width_spin, active.style.width, "setValue"),
                    (self.arrow_size_spin, active.style.arrow_size, "setValue"),
                    (self.arrow_start_size_spin, active.style.start_size(), "setValue"),
                    (self.font_auto_button, bool(active.style.font_auto), "setChecked"),
                    (self.arrow_start_combo,
                     max(self.arrow_start_combo.findData(active.style.arrow_start), 0),
                     "setCurrentIndex"),
                    (self.arrow_end_combo,
                     max(self.arrow_end_combo.findData(active.style.arrow_end), 0),
                     "setCurrentIndex"),
                    (self.dash_combo,
                     line_style_index(self.dash_combo, active.style.line_style),
                     "setCurrentIndex"),
                    (self.dash_scale_spin, active.style.dash_scale, "setValue"),
                    (self.font_spin, active.style.font_size, "setValue"),
                    (self.font_family_combo, QFont(QFontInfo(active.style.font()).family()),
                     "setCurrentFont"),
                    (self.text_colour_button, active.style.text_color, "set_color"),
                    (self.text_align_combo, active.style.align, "setCurrentText"),
                    (self.hatch_combo, hatch_index(self.hatch_combo, active.style.hatch),
                     "setCurrentIndex"),
                    (self.hatch_scale_spin, active.style.hatch_scale * 100, "setValue"),
                    (self.hatch_colour_button, active.style.hatch_color, "set_color"),
                    (self.hatch_bar_colour_button, active.style.hatch_color, "set_color"),
                    (self.hatch_opacity_spin,
                     int(round(getattr(active.style, "hatch_opacity", 1.0) * 100)), "setValue"),
                    (self.cloud_spin, float(getattr(active, "cloud_size", self.default_cloud_size))
                     if items else self.default_cloud_size, "setValue"),
                    (self.corner_spin, float(active.style.corner_radius) if items
                     else self.default_style.corner_radius, "setValue"),
                    (self.symbol_combo, getattr(active, "symbol", self.view.count_symbol)
                     if items else self.view.count_symbol, "setCurrentText"),
                    (self.opacity_spin, int(round(active.style.opacity * 100)),
                     "setValue"),
                    (self.fill_opacity_spin,
                     int(round(active.style.fill_opacity * 100)), "setValue"),
                    (self.highlight_button, active.style.blend == "multiply", "setChecked"),
                    (self.callout_shape_combo,
                     1 if getattr(active, "shape_kind", "box") == "cloud" else 0,
                     "setCurrentIndex"))
        for control, value, method in controls:
            control.blockSignals(True)
            getattr(control, method)(value)
            control.blockSignals(False)
        for name, button in self.font_buttons.items():
            button.blockSignals(True)
            button.setChecked(getattr(active.style, name))
            button.blockSignals(False)
        # the lists were set quietly: their tooltips (the shown pattern's
        # name) follow, or they would name what the last markup had
        from .propbar import hatch_tip
        hatch_tip(self.hatch_combo)
        self.dash_combo.setToolTip(self.dash_combo.currentText())

    # -- undo --------------------------------------------------------------
    def _open_editor_document(self):
        """The text document being typed into, if anything is being typed into."""
        item = self.view.editing_item()
        editor = getattr(item, "_editor", None) if item is not None else None
        return editor.document() if editor is not None else None

    # ==================================================================
    # calculation (SMath)
    # ==================================================================
    def toggle_calc_mode(self, on=None) -> None:
        """Calc mode or Markup mode (decision 5), shown in the status bar."""
        calc = self.view.calc
        if on is None or not isinstance(on, bool):
            on = calc.mode != "calc"
        calc.leave()
        calc.mode = "calc" if on else "markup"
        if not on:
            calc.clear_cross()
        for widget in (getattr(self, "act_calc_mode", None), getattr(self, "mode_switch", None)):
            if widget is not None and widget.isChecked() != on:
                widget.blockSignals(True)
                widget.setChecked(on)
                widget.blockSignals(False)
        self.status_hint.setText("Calc mode — typing on the page starts an equation" if on
                                 else "Markup mode — the markup tools' keys")
        self._apply_mode_keys()
        self.view.viewport().update()

    def calculate(self) -> None:
        """F9: every equation, in reading order."""
        from ..calc.docsheet import sheet_for
        self.view.calc.leave()
        sheet_for(self.document).recalculate(force=True)
        self.status_hint.setText("Calculated")

    def set_auto_calc(self, on: bool) -> None:
        from ..calc.docsheet import sheet_for
        sheet_for(self.document).worksheet.auto_calculation = bool(on)
        if on:
            sheet_for(self.document).recalculate()

    def _into_an_equation(self):
        """The equation being typed into, or a new one at the red cross (or
        under the pointer)."""
        calc = self.view.calc
        if calc.editing():
            return calc.item
        frame, point = calc._where_typing_starts()
        if frame is None:
            return None
        item = calc.start(frame, point)
        if item is not None:
            self._opened_by_command = item
        return item

    def _as_opened(self, item) -> None:
        """An equation a command started — If, For, While, Line, a matrix, a
        function or a constant into a new one — opens with what the command
        put in it, as a plot opens with its plot: one Ctrl+Z takes the lot
        away, rather than first leaving an empty equation on the page
        (exercise round 1, F-08). Into an equation already being typed, the
        insert is one more keystroke, taken back on its own."""
        if item is not None and getattr(self, "_opened_by_command", None) is item:
            item.region.editor._undo.clear()
        self._opened_by_command = None

    def insert_matrix(self) -> None:
        from ..calc.engine.model import Matrix
        from . import calcdialogs
        size = calcdialogs.matrix_size(self)
        if size is None:
            return
        item = self._into_an_equation()
        if item is None:
            return
        editor = item.region.editor
        editor._push_undo()
        editor._insert_box(Matrix(size[0], size[1]), into=0)
        self.view.calc._after_edit(item)
        self._as_opened(item)
        self.view.setFocus()

    def insert_plot(self) -> None:
        """A 2-D plot at the red cross, or under the pointer (SMath's @)."""
        calc = self.view.calc
        calc.leave()
        frame, point = calc._where_typing_starts()
        if frame is not None:
            calc.start_plot(frame, point)
            self.view.setFocus()

    def insert_calc_text(self) -> None:
        """Calculation text at the red cross, or under the pointer."""
        calc = self.view.calc
        calc.leave()
        frame, point = calc._where_typing_starts()
        if frame is not None:
            calc.start_calc_text(frame, point)

    def _rename_table(self, item) -> None:
        if not self.interactive_prompts:
            return
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Rename Table",
                                        "Name (formulas and equations that use it follow):",
                                        text=item.name)
        if ok and name.strip():
            self.view.tables.rename_to(item, name.strip())

    def conditional_formatting_rules(self) -> None:
        from .condformat import open_document_rules
        open_document_rules(self)

    def insert_table(self) -> None:
        """Drag out a table (a click gives Excel's handful of cells): the
        Table tool, from the Tools or Calculation toolbar, Tools ▸ Markup or
        Calculation ▸ Table alike."""
        self.view.calc.leave()
        self.view.tables.close()
        self.select_tool("table")
        self.status_hint.setText("Drag out the table: the rows and columns follow the size "
                                 "you drag · a click makes a 4 × 3 table")

    def format_cells_dialog(self) -> None:
        """Format Cells (Ctrl+1) for the selected cells of the open table."""
        tables = self.view.tables
        if not tables.is_open():
            return
        from .celldialog import FormatCellsDialog
        dialog = FormatCellsDialog(tables, self)
        if not self.interactive_prompts:
            self._last_format_dialog = dialog
            return
        dialog.exec()
        from .release import done_with
        done_with(dialog)

    def insert_block(self) -> None:
        """A calculation block round the selected equations (on the page of the
        first), or a new empty one at the red cross or under the pointer."""
        from ..items.calc import CalcBlockItem, CalcItem, CalcTextItem
        from .calcedit import GRID_PT, snap

        calc = self.view.calc
        calc.leave()
        chosen = [i for i in self.selected_items()
                  if isinstance(i, (CalcItem, CalcTextItem)) and i.parentItem() is not None]
        if chosen:
            frame = chosen[0].parentItem()
            chosen = [i for i in chosen if i.parentItem() is frame]
            box = QRectF()
            for item in chosen:
                box = box.united(item.mapRectToParent(item.local_rect()))
            left, top = snap(box.left() - GRID_PT), snap(box.top() - GRID_PT)
            right = snap(box.right() + 2 * GRID_PT)
            bottom = snap(box.bottom() + 2 * GRID_PT)
        else:
            frame, point = calc._where_typing_starts()
            if frame is None:
                return
            left, top = snap(point.x()), snap(point.y())
            right, bottom = left + 36 * GRID_PT, top + 12 * GRID_PT
        block = CalcBlockItem(QRectF(0, 0, right - left, bottom - top))
        block.author = self.document.settings.default_author or self.document.author
        self.view.begin_snapshot([frame])
        frame.add_markup(block, QPointF(left, top))
        self.view.scene().clearSelection()
        block.setSelected(True)
        self.view.commit_snapshot("Add calculation block")
        calc.clear_cross()
        self.refresh_selection()
        # a box takes in whatever is inside it: say so when that is more than
        # what was selected
        extra = [i for i in block.members() if i not in chosen]
        if chosen and extra:
            names = ", ".join(i.text() if hasattr(i, "text") and callable(i.text) else "text"
                              for i in extra[:3])
            self.status_hint.setText(
                f"The block also holds {len(extra)} more inside its box: {names}")
        else:
            self.status_hint.setText("Calculation block: its equations stay in it; "
                                     "right-click for Self-contained")

    def set_measure_variable(self, item, name: str) -> bool:
        """Name a measurement's value for the calculations (decision 24), or
        take the name away with an empty one. One undo step."""
        from ..items.calc import smath_variable_name, valid_variable_name

        name = smath_variable_name(name)
        if name == item.variable:
            return True
        if name and not valid_variable_name(name):
            self.status_hint.setText(
                f"“{name}” is not a variable name: a letter, then letters and digits, "
                "and a subscript after a dot if you like (L.beam)")
            self.refresh_selection()
            return False
        self.view.begin_snapshot(self.view.involved_frames(item))
        item.set_variable(name)
        from ..calc.docsheet import sheet_for
        sheet_for(self.document).settle()
        self.view.commit_snapshot("Variable name" if name else "Remove variable name")
        self.refresh_selection()
        return True

    def show_variable_of(self, item) -> None:
        """Open the Variables panel at a measurement's variable."""
        self.show_panel("dock_variables", True)
        panel = self.variables_panel
        panel.refresh()
        panel.filter.setText("")
        for index in range(panel.tree.topLevelItemCount()):
            node = panel.tree.topLevelItem(index)
            row = panel.row_of(node)
            if row is not None and row.region_id == item.variable_region_id:
                panel.tree.setCurrentItem(node)
                panel.tree.scrollToItem(node)
                return

    def _variable_field(self, menu, item):
        """The measurement's variable name, as a box in its right-click menu:
        Enter (or closing the menu) names it, an empty box takes the name
        away."""
        from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QWidget, QWidgetAction

        holder = QWidget(menu)
        holder.setObjectName("measureVariableRow")
        row = QHBoxLayout(holder)
        row.setContentsMargins(24, 3, 10, 3)
        row.setSpacing(6)
        row.addWidget(QLabel("Variable"))
        # typed and drawn as SMath writes a name: L . beam is L with "beam"
        # under it (the user, 2026-10-16)
        from .namebox import SMathNameEdit
        field = SMathNameEdit(item.variable)
        field.setObjectName("measureVariable")
        field.setPlaceholderText("name")
        field.setToolTip("Name this measurement for the calculations, as in an equation: "
                         "L . beam gives L with a subscript, Ctrl+Alt+F φ; empty for none "
                         "· Enter to set")
        field.setMinimumWidth(110)
        row.addWidget(field, 1)
        action = QWidgetAction(menu)
        action.setDefaultWidget(holder)
        done = {"set": False}

        def commit():
            if done["set"] or item.scene() is None:
                return
            done["set"] = True
            if field.text().strip() != item.variable:
                self.set_measure_variable(item, field.text())

        def on_enter():
            commit()
            menu.close()
        field.returnPressed.connect(on_enter)
        menu.aboutToHide.connect(commit)
        # the box takes the keys as soon as the menu opens
        menu.aboutToShow.connect(lambda: field.setFocus(Qt.PopupFocusReason))
        return action

    def _select_block_members(self, block) -> None:
        self.view.scene().clearSelection()
        for member in block.members():
            member.setSelected(True)
        self.refresh_selection()

    def remove_block_keep_equations(self, block) -> None:
        """The block's frame goes; its equations stay where they are."""
        if block.locked or block.scene() is None:
            return
        frame = block.parentItem()
        self.view.begin_snapshot(self.view.involved_frames(block))
        frame.remove_markup(block)
        self.view.commit_snapshot("Remove block")
        from ..calc.docsheet import sheet_for
        sheet_for(self.document).settle()
        self.refresh_selection()
        self.status_hint.setText("Block removed; its equations are on the page as they were")

    def set_block_self_contained(self, blocks: list, on: bool) -> None:
        blocks = [b for b in blocks if not b.locked and b.self_contained != bool(on)]
        if not blocks:
            return
        self.view.begin_snapshot(self.view.involved_frames(*blocks))
        for block in blocks:
            block.set_self_contained(on)
        from ..calc.docsheet import sheet_for
        sheet_for(self.document).settle()
        self.view.commit_snapshot("Self-contained" if on else "Not self-contained")
        self.refresh_selection()

    # -- the Maths panel (decision 19) --------------------------------------------
    def maths_type(self, text: str) -> None:
        """A Maths panel button: typed into the equation, as its key would be."""
        item = self._into_an_equation()
        if item is None:
            return
        self.view.calc._type(item, text)
        self._as_opened(item)
        self.view.setFocus()

    def maths_key(self, name: str) -> None:
        if self.view.calc.editing():
            self.view.calc._named_key(name)
            self.view.setFocus()

    def insert_structure(self, name: str) -> None:
        self.insert_program(name)

    def insert_operator(self) -> None:
        """Insert > Operator (WebSMath's): the operators by group."""
        from . import calcdialogs, calcedit
        how = calcdialogs.operator_to_insert(self)
        if how:
            calcedit.insert_operator(self.view.calc, how)

    def insert_unit(self) -> None:
        """Every unit SMath knows; the one picked goes in as 'unit."""
        from ..calc.engine.catalog import UNIT_CATALOG
        from . import calcdialogs
        entries = sorted(((n, f"{t} ({c})") for n, (c, t) in UNIT_CATALOG.items()),
                         key=lambda x: x[0].lower())
        name = calcdialogs.pick(self, "Insert unit", entries)
        if name:
            self.maths_type("'" + name)

    def plot_tool(self, tool: str) -> None:
        """What dragging does in a plot that has been double-clicked into."""
        self.view.calc.plot_tool = tool

    def plot_render(self, points: bool) -> None:
        item = self.view.calc.item
        if item is not None and item.region is not None and item.region.plot is not None:
            item.region.plot.points = bool(points)
            item.relayout()
            item.update()

    def insert_program(self, name: str) -> None:
        """A program block — if, for, while — or another line in one, into
        the equation being typed or a new one (SMath's Programming panel)."""
        item = self._into_an_equation()
        if item is None:
            return
        item.region.editor.insert_structure(name)
        self.view.calc._after_edit(item)
        self._as_opened(item)
        self.view.setFocus()

    def insert_function(self) -> None:
        from . import calcdialogs
        name = calcdialogs.function_to_insert(self)
        if name:
            item = self._into_an_equation()
            if item is not None:
                self.view.calc._type(item, name + "(")
                self._as_opened(item)

    def show_constants(self) -> None:
        from . import calcdialogs
        typed = calcdialogs.constant_to_insert(self)
        if typed:
            item = self._into_an_equation()
            if item is not None:
                self.view.calc._type(item, typed)
                self._as_opened(item)

    def double_check(self) -> None:
        """Every result recalculated by a second, independent calculator."""
        from ..calc.docsheet import sheet_for
        from ..calc.engine.verify import double_check
        from . import calcdialogs
        self.view.calc.leave()        # the open equation's result first
        try:
            report = double_check(sheet_for(self.document).worksheet)
        except Exception as error:              # noqa: BLE001 — never break the page
            self.status_hint.setText(f"Double-check could not run: {error}")
            return
        self.status_hint.setText(report.summary())
        calcdialogs.show_double_check(self, report)

    def select_all_equations(self) -> None:
        """Ctrl+A inside an equation: every equation, as SMath selects all regions."""
        self.view.calc.leave()
        self.view.scene().clearSelection()
        for page in self.document.pages:
            if page.frame is None:
                continue
            for item in page.frame.markups():
                if getattr(item, "IS_CALC", False):
                    item.setSelected(True)
        self.view.selectionChanged.emit()

    def _format_equations(self, which: str) -> bool:
        """Bold, italic or underline on the equation being typed into, or the
        equations selected (decision 6: MarkForge's keys reach equations)."""
        calc = self.view.calc
        items = [calc.item] if calc.editing() else [
            i for i in self.selected_items() if getattr(i, "IS_CALC", False) and not i.locked
            and getattr(i, "region", None) is not None]
        if not items:
            return False
        if not calc.editing():
            self.view.begin_snapshot(self.view.involved_frames(*items))
        wanted = not all(getattr(i.region, which) for i in items)
        for item in items:
            setattr(item.region, which, wanted)
            item.relayout()
        if not calc.editing():
            self.view.commit_snapshot(which.capitalize())
        return True

    def undo_something(self) -> None:
        """Take back the typing first, then the document change under it."""
        calc = self.view.calc
        if calc.editing():
            # One history (the brief): the keystrokes of the equation being
            # typed first, then — once it is back to how it was opened — the
            # document's own steps.
            if calc.undo():
                self._refresh_undo_actions()
                return
            calc.leave()
        document = self._open_editor_document()
        if document is not None and document.isUndoAvailable():
            document.undo()
        elif self.undo_stack.canUndo():
            self.undo_stack.undo()
        self._refresh_undo_actions()

    def redo_something(self) -> None:
        if self.view.calc.editing() and self.view.calc.redo():
            self._refresh_undo_actions()
            return
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

    def _style_arrow_size(self, value: float) -> None:
        """End ▾'s size. The start keeps the size it had: Revu sizes each end
        on its own, and a markup whose start followed the end is given its
        own start size first."""
        def mutate(style) -> None:
            if float(style.arrow_start_size or 0.0) <= 0:
                style.arrow_start_size = float(style.arrow_size or 1.0)
            style.arrow_size = value
        self._style_change(ARROW_SIZE, mutate, "Arrowhead size")

    def _style_arrow_start_size(self, value: float) -> None:
        """Start ▾'s size, its own."""
        self._style_change(
            ARROW_SIZE, lambda style: setattr(style, "arrow_start_size", value),
            "Start size")

    def _style_line_ending(self, attribute: str, value: str) -> None:
        if self._edit_markup_style(lambda item: setattr(item.style, attribute, value)):
            return
        if not self.selected_items():
            item = self._style_default_item()
            if item is not None:
                self.apply_default_style(item)
                setattr(item.style, attribute, value)
                toolsets.remember_default(item)
                return
        self._style_change(ARROW_SIZE, lambda style: setattr(style, attribute, value),
                           "Line ending")
        # an end with something on it shows its size, as Revu's does
        self._refresh_style_controls()

    def _style_dash(self, value: str) -> None:
        from ..items import linestyles
        if value == linestyles.MANAGE:
            # Manage… opens Line Styles; the markup keeps its style
            self.dash_combo.blockSignals(True)
            self.dash_combo.setCurrentIndex(
                line_style_index(self.dash_combo, self._line_style_shown()))
            self.dash_combo.blockSignals(False)
            QTimer.singleShot(0, self, self.manage_line_styles)
            return
        self._style_change(DASH, lambda style: linestyles.apply(style, value), "Line style")

    def _line_style_shown(self) -> str:
        chosen = self.selected_items()
        return (chosen[0].style.line_style if chosen else self.default_style.line_style) \
            or "solid"

    def manage_line_styles(self):
        """Revu's line-style Manage…: import a .lin, write a style, take one
        out. The line lists are filled again after. Returned so a test can
        drive it."""
        from .linestyledialog import LineStylesDialog
        dialog = LineStylesDialog(self, _bar_ink())
        dialog.finished.connect(lambda *_: self._line_styles_changed())
        if self.interactive_prompts:
            dialog.exec()
        return dialog

    def _line_styles_changed(self) -> None:
        fill_line_style_combo(self.dash_combo, _bar_ink(), 1, self._line_style_shown(),
                              bool(self.dash_combo.property("cloudStyles")))
        self.refresh_selection()

    def _style_font(self, value: float) -> None:
        """Font size ▾. A size picked is the size: Auto goes off, as Revu's does."""
        def mutate(style) -> None:
            style.font_size = value
            style.font_auto = False
        self._style_change(FONT, mutate, "Font size")
        self.font_auto_button.blockSignals(True)
        self.font_auto_button.setChecked(False)
        self.font_auto_button.blockSignals(False)

    def _style_font_auto(self, on: bool) -> None:
        """Revu's "A": the words set at the largest size that fits the box."""
        self._style_change(FONT, lambda style: setattr(style, "font_auto", bool(on)),
                           "Auto font size")
        self._refresh_style_controls()      # the size it came to, in the size box

    def _style_hatch(self, value: str) -> None:
        from .hatchpatterns import MANAGE
        if value == MANAGE:
            # Manage… opens Hatch Patterns; the markup keeps its pattern
            self.hatch_combo.blockSignals(True)
            self.hatch_combo.setCurrentIndex(
                hatch_index(self.hatch_combo, self._hatch_shown()))
            self.hatch_combo.blockSignals(False)
            QTimer.singleShot(0, self, self.manage_hatches)
            return
        self._style_change(HATCH, lambda style: setattr(style, "hatch", value or ""),
                           "Hatch")

    def _hatch_shown(self) -> str:
        """The pattern the toolbar is showing: the selection's, or the default's."""
        chosen = [i for i in self.view.scene().selectedItems() if isinstance(i, MarkupItem)] \
            if self.view.scene() is not None else []
        return (chosen[0].style.hatch if chosen else self.default_style.hatch) or ""

    def manage_hatches(self):
        """Revu's Hatch Patterns: import a .pat, write one, take one out. The
        hatch lists are filled again after. Returned so a test can drive it."""
        from .hatchpatterns import HatchPatternsDialog
        dialog = HatchPatternsDialog(self, _bar_ink())
        dialog.finished.connect(lambda *_: self._hatches_changed())
        if self.interactive_prompts:
            dialog.exec()
        return dialog

    def _hatches_changed(self) -> None:
        fill_hatch_combo(self.hatch_combo, _bar_ink(), self._hatch_shown())
        self.refresh_selection()

    def _style_opacity(self, percent: int) -> None:
        value = percent / 100.0
        self._style_change(OPACITY, lambda style: setattr(style, "opacity", value),
                           "Opacity")

    # Bluebeam's Properties toolbar leads with what matters for the markup:
    # the font for anything with words in it, the line and fill for shapes.
    # Bluebeam's Properties toolbar: Line: colour, opacity, style, width;
    # Start and End; Fill: colour, opacity; Hatch; Font (words first for
    # anything with words in it)
    _SHAPE_ORDER = (STROKE, OPACITY, DASH, WIDTH, ARROW_SIZE, CLOUD, CORNER,
                    FILL, FILL_OPACITY, HATCH, SYMBOL, FONT)
    _TEXT_ORDER = (FONT, STROKE, OPACITY, DASH, WIDTH, ARROW_SIZE, CLOUD, CORNER,
                   FILL, FILL_OPACITY, HATCH, SYMBOL)

    def _show_subject_popup(self) -> None:
        """Bluebeam's type ▾: Subject (typed in, for every selected markup),
        the number of markups selected — and CalcForge's extras."""
        self.style_kind_menu.showPopup()
        self.subject_field.setFocus()
        self._subject_popup = self.style_more_popup

    def _fill_style_more_popup(self) -> None:
        """What the type ▾ panel shows for the markups picked now."""
        items = [i for i in self.selected_items() if isinstance(i, MarkupItem)]
        self.subject_field.blockSignals(True)
        self.subject_field.setText(items[0].subject if items else "")
        self.subject_field.blockSignals(False)
        self.subject_field.setEnabled(bool(items))
        self.selected_count_label.setText(str(len(items)))
        if items:
            supported = common_capabilities(items)
        else:
            active = self._style_default_item()
            supported = capabilities(active, for_default=True) if active is not None else set()
        form = self._style_more_form
        for widget, field in ((self.dash_scale_spin, DASH),
                              (self.hatch_colour_button, HATCH),
                              (self.hatch_scale_spin, HATCH),
                              (self.hatch_opacity_spin, HATCH)):
            form.setRowVisible(widget, field in supported)

    def _subject_typed(self) -> None:
        items = [i for i in self.selected_items() if isinstance(i, MarkupItem)]
        text = self.subject_field.text()
        if not items or all(one.subject == text for one in items):
            return
        self.view.begin_snapshot(self.view.involved_frames(*items))
        for one in items:
            one.subject = text
            one.touch()
        self.view.commit_snapshot("Subject")
        self.properties_panel.show_items(self.selected_items())

    def _style_highlight(self, on: bool) -> None:
        """Revu's highlight button: the markup multiplies onto the page."""
        value = "multiply" if on else "normal"

        def mutate(style) -> None:
            style.blend = value
        if self._edit_markup_style(lambda item: mutate(item.style)):
            return
        if not self.selected_items():
            item = self._style_default_item()
            if item is not None:
                self.apply_default_style(item)
                mutate(item.style)
                toolsets.remember_default(item)
            return
        self._push_style(mutate, "Highlight",
                         predicate=lambda item: bool(capabilities(item) & {STROKE, FILL}))

    def _style_callout_shape(self, kind: str) -> None:
        """A callout's Shape ▾: its box drawn as a rectangle or a cloud."""
        kind = kind or "box"
        if self._edit_markup_style(lambda item: setattr(item, "shape_kind", kind)):
            return
        items = [i for i in self.selected_items() if isinstance(i, CalloutItem)]
        if not items:
            item = self._style_default_item()
            if isinstance(item, CalloutItem):
                self.apply_default_style(item)
                item.shape_kind = kind
                toolsets.remember_default(item)
            return
        self.view.begin_snapshot(self.view.involved_frames(*items))
        for item in items:
            item.prepareGeometryChange()
            item.shape_kind = kind
            item.touch()
            if hasattr(item, "apply_style"):
                item.apply_style()
            item.update()
        self.view.commit_snapshot("Callout shape")
        self.properties_panel.show_items(self.selected_items())

    def _measure_setting(self, attr: str, value, description: str) -> None:
        """Caption ▾: something of the selected measurements, as one undo step."""
        if getattr(self, "_filling_caption", False):
            return
        items = [i for i in self.selected_items() if isinstance(i, MeasureItem)]
        if not items:
            return
        self.view.begin_snapshot(self.view.involved_frames(*items))
        for item in items:
            item.prepareGeometryChange()
            setattr(item, attr, value)
            item.touch()
            item.update()
        self.view.commit_snapshot(description)
        self.properties_panel.show_items(self.selected_items())

    def _fill_caption_menu(self) -> None:
        items = [i for i in self.selected_items() if isinstance(i, MeasureItem)]
        first = items[0] if items else None
        self._filling_caption = True
        try:
            for action in (self.caption_show_action, self.caption_inline_action):
                action.setEnabled(bool(items))
            self.caption_show_action.setChecked(bool(items) and first.show_label)
            self.caption_inline_action.setChecked(bool(items) and first.label_angle is None)
            # Revu's values: those this kind of measurement can show, ticked
            # when shown; the ones that need a depth greyed until it has one
            offered = first.caption_choices() if first is not None else ()
            shown = first.caption_shown() if first is not None else ()
            for part, action in self.caption_part_actions.items():
                action.setVisible(part in offered)
                action.setEnabled(part in offered and first.caption_available(part))
                action.setChecked(part in shown)
        finally:
            self._filling_caption = False

    def _caption_part(self, part: str, on: bool) -> None:
        """Caption ▾: one of Revu's values shown or not, as one undo step."""
        if getattr(self, "_filling_caption", False):
            return
        items = [i for i in self.selected_items()
                 if isinstance(i, MeasureItem) and part in i.caption_choices()]
        if not items:
            return
        self.view.begin_snapshot(self.view.involved_frames(*items))
        for item in items:
            item.prepareGeometryChange()
            item.set_caption_part(part, on)
            item.refresh()
            item.touch()
            item.update()
        self.view.commit_snapshot("Caption")
        self.properties_panel.show_items(self.selected_items())

    def _measure_page_index(self) -> int:
        """The page of the selected measurement (the current page otherwise)."""
        for item in self.selected_items():
            frame = item.parentItem()
            for index, page in enumerate(self.document.pages):
                if page.frame is not None and page.frame is frame:
                    return index
        return self.current_index

    def _measures_for_units(self) -> list:
        return [i for i in self.selected_items()
                if isinstance(i, MeasureItem) and i.kind not in ("dimension", "calibrate")]

    def _fill_units_panel(self) -> None:
        """Units ▾ for the selected measurement — or, with a measuring tool in
        hand and nothing selected, for the measurements it draws next."""
        from ..items.measure import AREA, PERIMETER, VOLUME
        from .propbar import _unit_words
        page = self.document.pages[self._measure_page_index()]
        items = self._measures_for_units()
        first = items[0] if items else self._style_default_item()
        if not isinstance(first, MeasureItem):
            first = None
        own = dict(first.units) if first is not None else {}
        if not items and first is not None:
            own = dict(self._next_measure_units())
        page_units = {"length": page.scale.display_unit, "area": page.scale.area_unit,
                      "volume": page.scale.area_unit.replace("^2", "^3")
                      if page.scale.area_unit.endswith("^2") else ""}
        kind = first.kind if first is not None else ""
        wanted = {"length": True,
                  "area": kind in (AREA, VOLUME, PERIMETER),
                  "volume": kind == VOLUME or bool(first is not None and first.depth_text
                                                   and kind in (AREA, PERIMETER))}
        for key, combo in self.units_combos.items():
            combo.blockSignals(True)
            shown = page_units[key]
            combo.setItemText(0, f"Page ({_unit_words(shown)})" if shown else "Page")
            unit = own.get(key, "")
            found = combo.findData(unit)
            if found < 0:
                combo.addItem(_unit_words(unit), unit)
                found = combo.count() - 1
            combo.setCurrentIndex(found)
            combo.setEnabled(first is not None)
            combo.blockSignals(False)
            self._units_form.setRowVisible(combo, wanted[key])
        self.units_note.setText("For the selected measurements" if items
                                else "For the next measurements drawn with this tool")

    def _next_measure_units(self) -> dict:
        """The units the tool in hand gives its next measurements (Revu: until
        another tool is picked)."""
        kept = getattr(self, "_measure_units_next", None)
        if kept and kept[0] == self.view.tool_key:
            return kept[1]
        return {}

    def _units_chosen(self, key: str = "length") -> None:
        """Units ▾: the selected measurements written in other units — their
        own, saved with them; "Page" puts them back on the page's. One undo
        step. The value an equation reads is the same quantity whatever the
        unit (6250 mm or 6.25 m)."""
        combo = self.units_combos[key]
        unit = combo.currentData() or ""
        items = self._measures_for_units()
        if not items:
            if isinstance(self._style_default_item(), MeasureItem):
                units = dict(self._next_measure_units())
                units[key] = unit
                self._measure_units_next = (self.view.tool_key,
                                            {k: v for k, v in units.items() if v})
            return
        if all(i.units.get(key, "") == unit for i in items):
            return
        self.view.begin_snapshot(self.view.involved_frames(*items))
        for item in items:
            item.prepareGeometryChange()
            item.set_unit(key, unit)
            item.refresh()
            item.touch()
            item.update()
        self.view.commit_snapshot("Measurement units")
        self.refresh_selection()

    def _fill_totals(self, items: list) -> None:
        """Totals ▾: the selected measurements added up, the first on the box."""
        from . import propbar
        rows = propbar.totals(items)
        menu = self.totals_button.popup_menu
        menu.clear()
        for name, total in rows:
            action = menu.addAction(f"{name} = {total}")
            action.setEnabled(False)
        self.totals_button.set_face(f"{rows[0][0]} = {rows[0][1]}" if rows else "—")

    @staticmethod
    def _type_name(item) -> str:
        """What kind of markup it is — Cloud, Arrow, Area — not what it is
        called (a count's subject, a measurement's label)."""
        from ..items.measure import MEASURE_NAMES
        kind_name = getattr(item, "NAME_FOR_KIND", None)
        if isinstance(kind_name, str) and kind_name:
            return kind_name
        if isinstance(item, MeasureItem):
            return MEASURE_NAMES.get(item.kind, "Measurement")
        return item.NAME

    def _item_setting(self, field: str, attr: str, value, description: str) -> None:
        """A toolbar control that sets something of the markup itself rather
        than its pen (a cloud's arcs, a count's symbol): the selection, as one
        undo step — or, with nothing selected, what the next one is drawn with."""
        items = [i for i in self.selected_items() if field in capabilities(i)]
        if not items:
            return
        self.view.begin_snapshot(self.view.involved_frames(*items))
        for item in items:
            item.prepareGeometryChange()
            setattr(item, attr, value)
            item.touch()
            item.update()
        self.view.commit_snapshot(description)
        self.properties_panel.show_items(self.selected_items())

    def _style_cloud(self, value: float) -> None:
        if self._edit_markup_style(lambda item: setattr(item, "cloud_size", float(value))):
            return
        if not self.selected_items():
            self.default_cloud_size = float(value)
            return
        self._item_setting(CLOUD, "cloud_size", float(value), "Cloud size")

    def _style_symbol(self, value: str) -> None:
        if not value:
            return
        if self._edit_markup_style(lambda item: setattr(item, "symbol", value)):
            return
        if not self.selected_items():
            self.view.count_symbol = value
            return
        self._item_setting(SYMBOL, "symbol", value, "Count symbol")

    def _style_hatch_colour(self, colour: str) -> None:
        """Hatch colour, from the bar's swatch or the type ▾ panel's: the
        selection's, as one undo step, or the next markup's."""
        for button in (self.hatch_bar_colour_button, self.hatch_colour_button):
            if button.color() != colour:
                button.set_color(colour)
        self._style_change(HATCH, lambda style: setattr(style, "hatch_color", colour),
                           "Hatch colour")

    def _style_hatch_opacity(self, percent: int) -> None:
        value = percent / 100.0
        self._style_change(HATCH, lambda style: setattr(style, "hatch_opacity", value),
                           "Hatch opacity")

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
        if self._edit_markup_style(lambda item: mutate(item.style)):
            return
        if self._remember_style_default(mutate):
            return
        if not self.selected_items():
            # nothing picked: the toolbar is what the next markup is drawn with.
            # A change to picked markups is theirs alone (Bluebeam): it used to
            # carry on into every one drawn after (2026-10-10).
            mutate(self.default_style)
            return
        self._push_style(mutate, description,
                         predicate=lambda item: field in capabilities(item))

    def _edit_markup_style(self, mutate) -> bool:
        """With a numbered markup style picked and nothing selected, the
        Properties toolbar edits that style (markupstyles.py)."""
        styles = getattr(self, "markup_styles", None)
        return styles is not None and styles.edit(mutate)

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
        item = tool.factory()
        if isinstance(item, RectItem) and item.kind == "marquee":
            # a region being chosen — Crop, Whiteout — wears no style, so the
            # bar has none to show (F-36: Whiteout's bar showed Crop's dashes)
            return None
        return item

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
        if not item.author:
            # signed with the person's name, as Bluebeam signs a new markup
            from . import preferences
            item.author = preferences.current().author

    def set_as_default(self, item: MarkupItem) -> None:
        """Draw the next markup of this kind the way this one is drawn."""
        key = toolsets.remember_default(item)
        self.status_hint.setText(
            f"New {item.display_name().lower()}s will look like this one "
            f"— Tools ▸ Forget Defaults puts it back")
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
            item.style.dash_array = tuple(style.dash_array or ())
            item.style.arrow_size = style.arrow_size
            item.style.arrow_start_size = style.arrow_start_size
            for key, unit in self._next_measure_units().items():
                item.set_unit(key, unit)
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
        item.style.fill_opacity = style.fill_opacity
        item.style.dash_array = tuple(style.dash_array or ())
        item.style.arrow_size = style.arrow_size
        item.style.arrow_start_size = style.arrow_start_size
        item.style.text_color = style.text_color
        item.style.font_family = style.font_family
        for name in Style.FONT_STYLES:
            setattr(item.style, name, getattr(style, name))
        item.style.font_auto = style.font_auto
        item.style.align = style.align
        if HATCH in capabilities(item):
            item.style.hatch = style.hatch
            item.style.hatch_scale = style.hatch_scale
            item.style.hatch_color = style.hatch_color
            item.style.hatch_opacity = style.hatch_opacity
        caps = capabilities(item)
        if CLOUD in caps:
            item.cloud_size = self.default_cloud_size
        if CORNER in caps:
            item.style.corner_radius = style.corner_radius
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
        # Sketch to Scale's shapes are set out in real dimensions on a scaled
        # page; a plain one is sized on the paper, in the rulers' units
        scaled = item.measures_real(page)
        if not always and (not self.interactive_prompts or not scaled):
            return
        item.refresh(page=page)
        if item.width_value is None or item.height_value is None:
            return
        width_text, height_text = item.size_texts(page)
        dialog = dialogs.RectangleSizeDialog(
            width_text, height_text, item.size_unit(page), self, scaled=scaled,
            sketch=bool(getattr(item, "to_scale", False)),
            shape="Ellipse" if item.kind == "ellipse" else "Rectangle")
        if dialog.exec() != dialogs.QDialog.Accepted:
            return
        width, height = dialog.values()
        if not item.set_real_size(width, height, page):
            self.status_hint.setText("Could not read those dimensions — "
                                     "try something like “3 m”.")

    def edit_measure_text(self, item) -> None:
        """Type on a measurement, where the words are going to appear."""
        self.view.open_label_editor(item, prefill=True)

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
            "Click “Scale Not Set” in the status bar to set one.")

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

    def _selection_changed_on_the_canvas(self) -> None:
        """While the mouse button is down, the panels wait for it to come up:
        rebuilding Properties for a markup somebody has just grabbed held up
        the start of the drag by a tenth of a second (Calcs.pdf, 2026-10-01).
        A click comes up at once, so it still shows straight away."""
        if self.view.pointer_is_down():
            self.view.refresh_on_release = True
            return
        self.refresh_selection()

    def _scene_selection_changed(self) -> None:
        """Every change of what is picked, however it came about (Escape,
        Select All, a deleted markup…): Properties catches up once the
        event loop is free, unless it already shows the selection."""
        if getattr(self, "_selection_check_pending", False):
            return
        self._selection_check_pending = True

        def check():
            self._selection_check_pending = False
            from shiboken6 import isValid
            if not isValid(self.properties_panel):
                return
            self.view.tables.refresh_bar()          # a table picked out shows the formula bar
            shown = self.properties_panel._items
            picked = [i for i in self.selected_items() if isinstance(i, MarkupItem)]
            if picked:
                # something picked: SMath's red cross goes, as SMath's does when
                # a region is selected (it stayed behind a pasted picture or a
                # snapshot being recoloured, 2026-10-14)
                self.view.calc.clear_cross()
            if len(shown) != len(picked) or any(a is not b for a, b in zip(shown, picked)):
                self._selection_changed_on_the_canvas()
        QTimer.singleShot(0, check)

    def refresh_selection(self) -> None:
        scene = self.view.scene()
        if scene is not None and hasattr(scene, "selection_reshaped"):
            scene.selection_reshaped()        # grouped or ungrouped, perhaps
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
        # the Variables panel's bold rows: the definitions the picked equation reads
        panel = getattr(self, "variables_panel", None)
        if panel is not None:
            panel.selection_changed()
        # The box round a group and the handles are painted over the canvas
        # rather than by the items, and Qt only repaints the part of the
        # canvas that changed. Selecting something changed no part of it, so
        # nothing was redrawn and the selection had nothing round it until a
        # menu opening forced the whole viewport to be painted again.
        self.view.viewport().update()

    def delete_selection(self) -> None:
        if self.view.tables.is_open():
            self.view.tables.clear("contents")
            return
        if self.view.editing_item() is not None:
            return                      # Delete belongs to the text being edited
        from ..items.calc import with_block_members
        items = [item for item in with_block_members(self.selected_items())
                 if self.view.editable(item)]
        if not items:
            return
        # A measurement that defines a variable: say what stops being defined
        # (decision 24).
        lost = []
        if any(getattr(item, "variable_region", None) is not None for item in items):
            from .calcedit import undefined_without
            lost = undefined_without(self.document, items)
            if lost and self.interactive_prompts:
                asked = (", ".join(lost) + (" is" if len(lost) == 1 else " are")
                         + " defined by what is being deleted, and will no longer be "
                         "defined. Delete anyway?")
                if QMessageBox.question(self, "Delete", asked) != QMessageBox.Yes:
                    return
        self.view.begin_snapshot()
        for item in items:
            detach(item)
        self.view.commit_snapshot("Delete markup")
        if lost:
            self.status_hint.setText(", ".join(lost) + (" is" if len(lost) == 1 else " are")
                                     + " no longer defined")
            self.refresh_selection()
            return
        self.refresh_selection()

    SNAPSHOT_DPI = 300.0

    def edit_link(self, item, new: bool = False) -> bool:
        """Ask where a link goes. False when the question was cancelled.

        A *new* link is still being drawn: where it goes is part of the one
        undo step that adds it (exercise round 1, F-08), so no step of its
        own is recorded here."""
        if not self.interactive_prompts:
            return True
        view_y = self.view.mapToScene(self.view.viewport().rect().topLeft())
        frame = self.current_page().frame
        top = frame.mapFromScene(view_y).y() if frame is not None else 0.0
        dialog = dialogs.LinkDialog(item, len(self.document.pages),
                                    (self.current_index, max(top, 0.0)), self)
        if dialog.exec() != dialogs.QDialog.Accepted:
            return False
        if new:
            dialog.apply()
            return True
        self.view.begin_snapshot(self.view.involved_frames(item))
        dialog.apply()
        self.view.commit_snapshot("Edit link")
        self.refresh_lists()
        return True

    def follow_link(self, item) -> None:
        """Go where a link goes: a page, a view, a file or a web address."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from ..items.link import PAGE, VIEW, WEB
        if item.kind in (PAGE, VIEW):
            if not 0 <= item.target_page < len(self.document.pages):
                self.status_hint.setText("That link points at a page that is not here")
                return
            self.go_to_page(item.target_page)
            if item.kind == VIEW:
                frame = self.document.pages[item.target_page].frame
                if frame is not None:
                    point = frame.mapToScene(QPointF(frame.page.width_pt / 2,
                                                     item.target_y))
                    self.view.centerOn(point)
            return
        if not item.address:
            self.status_hint.setText("This link has nowhere to go yet")
            return
        url = QUrl.fromUserInput(item.address) if item.kind == WEB \
            else QUrl.fromLocalFile(item.address)
        QDesktopServices.openUrl(url)

    def crop_page_region(self, frame, region: QRectF, every_page: bool = False) -> bool:
        """Crop a page to *region*: the rest of the sheet is cut away.

        The PDF's own CropBox is set, so the page is cropped for every viewer
        and the original is still inside the file; markups keep their place on
        the drawing. With *every_page*, the same box is cropped from every
        page of the same size. One undo step.
        """
        if frame is None:
            return False
        region = QRectF(region).normalized().intersected(frame.page_rect())
        if region.width() < 4 or region.height() < 4:
            self.status_hint.setText("Crop: drag the part of the page to keep")
            return False
        state = getattr(self, "_crop_dialog_state", None)
        if state is not None:
            # Get Window: the dragged region's margins go back to Crop Pages
            from ..core.document import PT_TO_MM
            self._crop_dialog_state = None
            whole = frame.page_rect()
            state["margins"] = {
                "top": (region.top() - whole.top()) * PT_TO_MM,
                "bottom": (whole.bottom() - region.bottom()) * PT_TO_MM,
                "left": (region.left() - whole.left()) * PT_TO_MM,
                "right": (whole.right() - region.right()) * PT_TO_MM}
            state["proportional"] = False
            self.select_tool("select")
            self.crop_pages(state=state)
            return True
        target = frame.page
        pages = [page for page in self.document.pages if page.frame is not None
                 and (page is target or (every_page
                      and abs(page.width_pt - target.width_pt) < 0.5
                      and abs(page.height_pt - target.height_pt) < 0.5))]
        return self._crop_pages([(page, region) for page in pages])

    # -- Crop Pages (Revu's dialog) ----------------------------------------
    def crop_pages_dialog(self, state: Optional[dict] = None) -> "dialogs.CropPagesDialog":
        """Revu's Crop Pages for the page or the run picked out; not yet shown.
        After Get Window it comes back with the dragged region's margins."""
        which = self.current_index
        dialog = dialogs.CropPagesDialog(len(self.document.pages), which,
                                         self.thumbnail_selection(), self, state=state)
        if state is None:
            self._pages_preset(dialog.pages, self._pages_for(), which)
        return dialog

    def crop_pages(self, state: Optional[dict] = None) -> bool:
        """Document ▸ Crop Pages…: margins off the chosen pages, or Get Window
        to drag the part to keep (the Crop tool) and come back."""
        dialog = self.crop_pages_dialog(state)
        answer = dialog.exec()
        if answer == dialogs.CropPagesDialog.PICK:
            self._crop_dialog_state = dialog.state()
            self.select_tool("crop")
            self.status_hint.setText("Crop Pages: drag the part of the page to keep — "
                                     "its margins go back to the dialog")
            return False
        if answer != dialogs.QDialog.Accepted:
            return False
        return self.finish_crop_pages(dialog)

    def finish_crop_pages(self, dialog) -> bool:
        """Cut *dialog*'s margins off each of its pages; one undo step."""
        from ..core.document import MM_TO_PT
        margins = {side: value * MM_TO_PT for side, value in dialog.margins_mm().items()}
        regions = []
        for which in dialog.page_indexes() or []:
            page = self.document.pages[which]
            whole = page.frame.page_rect() if page.frame is not None \
                else QRectF(0, 0, page.width_pt, page.height_pt)
            region = QRectF(whole.left() + margins["left"], whole.top() + margins["top"],
                            whole.width() - margins["left"] - margins["right"],
                            whole.height() - margins["top"] - margins["bottom"])
            if region.width() < 4 or region.height() < 4:
                self.status_hint.setText(f"Crop Pages: those margins leave nothing of "
                                         f"page {which + 1}")
                return False
            regions.append((page, region))
        return self._crop_pages(regions) if regions else False

    def _crop_pages(self, regions: list) -> bool:
        """Crop each (page, region) to its region, in one undo step."""
        changes = []
        for page, region in regions:
            source = None
            if page.pdf_key and page.pdf_page_index is not None:
                source = self._cropped_pdf(page, region)
                if source is None:
                    self.status_hint.setText("Crop failed: the page could not be read")
                    return False
            background = None
            if page.background_key and not page.pdf_key:
                background = self._crop_background(page, region)
            changes.append((page, source, background, region))

        from .calcedit import undefined_without
        off_the_page = []
        cropped_names: list = []

        def apply():
            from ..core.document import PT_TO_MM
            off_the_page.clear()
            for page, source, background, region in changes:
                kept = QRectF(0, 0, region.width(), region.height())
                frame_now = page.frame
                if source is not None:
                    page.pdf_key = self.document.add_asset(source, "pdf")
                if background is not None:
                    page.background_key = background[0]
                if frame_now is not None:
                    frame_now._background = None
                    for item in list(frame_now.markups()):
                        if item.from_drawing:
                            frame_now.remove_markup(item)
                        else:
                            item.setPos(item.pos() - region.topLeft())
                        if getattr(item, "IS_CALC", False) and item.scene() is not None:
                            box = item.mapRectToParent(item.local_rect())
                            if not box.intersects(kept):
                                off_the_page.append(item)
                            elif not kept.contains(box):
                                item.warning = "Partly cropped off the page"
                                item.update()
                    lost = [i for i in off_the_page if i.parentItem() is frame_now]
                    if lost:
                        cropped_names.extend(undefined_without(self.document, lost))
                        for item in lost:
                            frame_now.remove_markup(item)
                setup = page.setup
                setup.size_name = "Custom"
                setup.orientation = "portrait"
                setup.width_mm = region.width() * PT_TO_MM
                setup.height_mm = region.height() * PT_TO_MM
                setup.margin_left = setup.margin_top = 0.0
                setup.margin_right = setup.margin_bottom = 0.0
        self._structural_change("Crop page" if len(changes) == 1 else "Crop pages",
                                apply, preserve_view=True)
        self.status_hint.setText(f"Cropped {len(changes)} page(s) — Undo restores them")
        self.warn_undefined(sorted(set(cropped_names)),
                            f"Cropped {len(changes)} page(s) — Undo restores them. Cropped off")
        return True

    def _cropped_pdf(self, page, region: QRectF):
        """The page's source PDF with its CropBox set to *region*."""
        import pymupdf
        data = self.document.asset(page.pdf_key)
        if not data:
            return None
        try:
            with pymupdf.open(stream=data, filetype="pdf") as source:
                pdf_page = source[int(page.pdf_page_index)]
                sx = pdf_page.rect.width / max(page.width_pt, 1e-6)
                sy = pdf_page.rect.height / max(page.height_pt, 1e-6)
                shown = pymupdf.Rect(region.left() * sx, region.top() * sy,
                                     region.right() * sx, region.bottom() * sy)
                # Display coordinates back to the page's unrotated space, and
                # from the old crop's corner to the media box's.
                flat = shown * pdf_page.derotation_matrix
                flat.normalize()
                corner = pdf_page.cropbox.tl
                pdf_page.set_cropbox(flat + (corner.x, corner.y, corner.x, corner.y))
                return source.tobytes(garbage=3, deflate=True)
        except Exception:                                   # noqa: BLE001
            return None

    def extract_pages_dialog(self, index: Optional[int] = None) -> "dialogs.ExtractPagesDialog":
        """Revu's Extract Pages, set to the page or the run picked out; not
        yet shown."""
        which = self.page_index(index)
        dialog = dialogs.ExtractPagesDialog(len(self.document.pages), which,
                                            self.thumbnail_selection(), self)
        self._pages_preset(dialog.pages, self._pages_for(index), which)
        return dialog

    def extract_pages(self, indices=None, path: str = "") -> str:
        """Document ▸ Extract Pages…: save the chosen pages, with their
        markups, as a new PDF (Revu's dialog first, when none are given)."""
        if indices is not None:
            return self._extract(indices, path)
        dialog = self.extract_pages_dialog()
        if dialog.exec() != dialogs.QDialog.Accepted:
            return ""
        made = self.finish_extract_pages(dialog, path)
        return made[0] if made else ""

    def finish_extract_pages(self, dialog, path: str = "") -> list[str]:
        """What *dialog* chose: the pages to one file at *path* (asked for
        when not given) or, as Separate Files, one file each named after it
        with the page's number or label; then Delete Pages After Extracting
        and Open Files After Extraction. The files written."""
        from PySide6.QtWidgets import QFileDialog
        indices = sorted(dialog.page_indexes() or [])
        if not indices:
            return []
        if not path:
            base = os.path.splitext(self.document.path or "document.pdf")[0]
            path, _ = QFileDialog.getSaveFileName(
                self, "Extract Pages", f"{base} extract.pdf", "PDF files (*.pdf)")
            if not path:
                return []
        if dialog.separate.isChecked():
            stem = os.path.splitext(path)[0]
            made, used = [], set()
            for which in indices:
                name = str(which + 1)
                if dialog.use_labels.isChecked():
                    label = self.document.pages[which].label.strip()
                    name = re.sub(r'[\\/:*?"<>|]+', "-", label) or name
                while name in used:
                    name += f" ({which + 1})"
                used.add(name)
                made.append(self._extract([which], f"{stem} {name}.pdf"))
            made = [one for one in made if one]
            self.status_hint.setText(f"Extracted {len(made)} file(s) beside "
                                     f"{os.path.basename(stem)}")
        else:
            made = [self._extract(indices, path)]
        if dialog.delete_after.isChecked():
            if len(indices) >= len(self.document.pages):
                self.status_hint.setText("Extracted; every page was extracted, so none "
                                         "were deleted (a document keeps one)")
            else:
                self._delete_pages(indices)
        if dialog.open_after.isChecked():
            for one in made:
                self.open_in_new_tab()
                self._open_chosen(one)
        return made

    def _extract(self, indices, path: str) -> str:
        total = len(self.document.pages)
        indices = [i for i in indices if 0 <= i < total]
        if not indices:
            return ""
        if not path:
            from PySide6.QtWidgets import QFileDialog
            base = os.path.splitext(self.document.path or "document.pdf")[0]
            path, _ = QFileDialog.getSaveFileName(
                self, "Extract Pages", f"{base} extract.pdf", "PDF files (*.pdf)")
            if not path:
                return ""
        lost = self._save_pages_as(indices, path)
        self.status_hint.setText(f"Saved {len(indices)} page(s) to {os.path.basename(path)}")
        self.warn_undefined(lost, f"In {os.path.basename(path)}, defined on pages left behind")
        return path

    def _extract_from_menu(self, index: int) -> list[str]:
        """The Thumbnails menu's Extract Pages…: the dialog, set to that page
        or the run picked out."""
        dialog = self.extract_pages_dialog(index)
        if dialog.exec() != dialogs.QDialog.Accepted:
            return []
        return self.finish_extract_pages(dialog)

    def split_document_dialog(self) -> "dialogs.SplitDocumentDialog":
        """Revu's Split Document, for this document; not yet shown."""
        where = self.document.path or ""
        stem = os.path.splitext(os.path.basename(where or "document.pdf"))[0]
        return dialogs.SplitDocumentDialog(len(self.document.pages),
                                           os.path.dirname(where), stem, self)

    def split_into_files(self, every: int = 0, folder: str = "",
                         suffix: str = "part") -> list[str]:
        """Document ▸ Split Document…: files of *every* pages each (Revu's
        dialog first, when not given)."""
        from PySide6.QtWidgets import QFileDialog
        if every <= 0:
            dialog = self.split_document_dialog()
            if folder:
                dialog.folder.setText(folder)
            if dialog.exec() != dialogs.QDialog.Accepted:
                return []
            return self.finish_split(dialog)
        if not folder:
            folder = QFileDialog.getExistingDirectory(self, "Split Document")
            if not folder:
                return []
        stem = os.path.splitext(os.path.basename(self.document.path or "document.pdf"))[0]
        return self._split(every, folder,
                           lambda n: f"{stem} {suffix} {n}.pdf" if suffix else f"{stem} {n}.pdf")

    def finish_split(self, dialog) -> list[str]:
        """Split as *dialog* chose: its Page Count, Folder and suffix."""
        folder = dialog.folder.text().strip()
        if not folder or not os.path.isdir(folder):
            return []
        return self._split(dialog.page_count.value(), folder, dialog.file_name)

    def _split(self, every: int, folder: str, file_name) -> list[str]:
        total = len(self.document.pages)
        every = max(int(every), 1)
        written = []
        warned: list = []
        for number, start in enumerate(range(0, total, every), start=1):
            chunk = list(range(start, min(start + every, total)))
            path = os.path.join(folder, file_name(number))
            lost = self._save_pages_as(chunk, path)
            if lost:
                warned.append(f"{os.path.basename(path)}: {', '.join(lost)}")
            written.append(path)
        self.status_hint.setText(f"Split into {len(written)} file(s)")
        if warned:
            text = ("Variables defined on pages in other parts are undefined in "
                    + "; ".join(warned) + ".")
            self.status_hint.setText(text)
            if self.interactive_prompts:
                QMessageBox.warning(self, "Variables undefined", text)
        return written

    def _save_pages_as(self, indices, path: str) -> list:
        """Write only *indices* of this document to *path*, leaving it as it
        was. Their equations go live into the new file's record; says which
        variables they use that are defined only on pages left behind."""
        from .calcedit import names_left_behind
        self.view.end_item_edit()
        document = self.document
        pages, kept_path, modified = document.pages, document.path, document.modified
        self._recalculate_for_saving()
        lost = names_left_behind(document, [pages[i] for i in indices])
        signed = document.signed_source
        document.pages = [pages[i] for i in indices]
        # Some of a signed file is a new file: written afresh, and the
        # document keeps its own signature for its own saves.
        document.signed_source = None
        try:
            project_io.save_document(document, path)
        finally:
            document.pages = pages
            document.path = kept_path
            document.modified = modified
            document.signed_source = signed
        return lost

    def whiteout_region(self, frame, region):
        """Cut a region out of source artwork without covering live markups."""
        if frame is None or region.normalized().isEmpty():
            return
        page = frame.page
        data = self.document.asset(page.pdf_key) if page.pdf_key else None
        if not data or page.pdf_page_index is None:
            self.status_hint.setText("Whiteout: this page has no source PDF artwork")
            return
        import pymupdf
        region = region.normalized().intersected(frame.page_rect())
        if region.isEmpty():
            return
        try:
            with pymupdf.open(stream=data, filetype="pdf") as source:
                pdf_page = source[int(page.pdf_page_index)]
                sx, sy = pdf_page.rect.width / page.width_pt, pdf_page.rect.height / page.height_pt
                box = pymupdf.Rect(region.left() * sx, region.top() * sy,
                                   region.right() * sx, region.bottom() * sy)
                from ..io.pdfwhiteout import erase_region, surviving_text, restore_search_text
                # Annotations remain live; do not bake their appearances
                # into the replacement page and then draw them a second time.
                annots = source.xref_get_key(pdf_page.xref, "Annots")[1]
                source.xref_set_key(pdf_page.xref, "Annots", "null")
                pdf_page = source.reload_page(pdf_page)
                search_text = surviving_text(pdf_page, box)
                appearance = erase_region(pdf_page, box)
                source.xref_set_key(pdf_page.xref, "Annots", annots)
                pdf_page = source.reload_page(pdf_page)
                # The replacement contains only surviving geometry. Preserve
                # the page object and annotations while replacing its artwork.
                xref = source.get_new_xref()
                source.update_object(xref, "<<>>")
                source.update_stream(xref, b"")
                pdf_page.set_contents(xref)
                rotation = pdf_page.rotation
                pdf_page.set_rotation(0)
                with pymupdf.open(stream=appearance, filetype="pdf") as replacement:
                    pdf_page.show_pdf_page(pdf_page.rect, replacement, 0, rotate=rotation)
                restore_search_text(pdf_page, search_text)
                pdf_page.set_rotation(rotation)
                changed = source.tobytes(garbage=4, deflate=True)
        except Exception as error:
            self.status_hint.setText(f"Whiteout failed: {error}")
            return
        def apply():
            page.pdf_key = self.document.add_asset(changed, "pdf")
            page.background_key = None
            frame._background = None
            for item in list(frame.markups()):
                if item.from_drawing:
                    frame.remove_markup(item)
        self._structural_change("Whiteout", apply, preserve_view=True)
        self.status_hint.setText("Cleared PDF artwork — Undo restores it")

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

        try:
            taken = frame.picture_items(region)
            picture = frame.render_items_picture(taken, region)
        except Exception as error:
            self.status_hint.setText(f"Snapshot failed: {error}")
            return
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
        default_snapshot = SnapshotItem()
        self.apply_default_style(default_snapshot)
        payload[0]["style"] = default_snapshot.serialize()["style"]
        assets = {key: base64.b64encode(data).decode("ascii")}
        for source_item in taken:
            for asset in source_item.assets_used():
                content = self.document.asset(asset)
                if content:
                    assets[asset] = base64.b64encode(content).decode("ascii")

        self._clipboard = payload
        mime = QMimeData()
        mime.setData(CLIPBOARD_TAG, json.dumps({CLIPBOARD_TAG: payload,
                                                "assets": assets}).encode("utf-8"))
        # For everything outside this application, which cannot read a
        # recording: rasterise this same filtered picture at printing
        # resolution. Rendering the page again here would put its background
        # and excluded worksheet items back into the system clipboard.
        scale = self.SNAPSHOT_DPI / 72.0
        # The external clipboard is only a preview. Bound its allocation even
        # for an A0 capture; the internal recording keeps full vector detail.
        scale = min(scale, (16_000_000 / (region.width() * region.height())) ** 0.5)
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
        if _our_clipboard() is not None:
            return False               # our own copy, with its items
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
        """The part of the page's sheet inside the region."""
        image = pdfio.page_raster(self.document, page)
        if image is None or image.isNull():
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

    def make_markups_editable(self, index: Optional[int] = None) -> int:
        """Read the page's own annotations out of the PDF as markups.

        Opening a drawing already reads them out, and leaves each one to the
        file to draw so it looks exactly as its author drew it. This is for a
        page where that did not happen — one whose annotations were not
        imported — and it takes the lot over at once: what comes out is
        MarkForge's own rendering of each, so the page stops drawing them
        itself, or every one would be on the page twice. Says how many were
        read.
        """
        which = self.page_index(index)
        page = self.document.pages[which]
        if not page.pdf_key or not page.pdf_annotations:
            return 0
        source = self.document.asset(page.pdf_key)
        if not source or page.pdf_page_index is None:
            return 0
        import tempfile
        from ..io import pdfio

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
            handle.write(source)
            scratch = handle.name
        try:
            # Ours from the start: the page is about to stop drawing them.
            found = pdfio.markups(scratch, [int(page.pdf_page_index)],
                                  keep_the_look=False, document=self.document)
        finally:
            try:
                os.unlink(scratch)
            except OSError:
                pass
        payloads = found.get(int(page.pdf_page_index)) or []
        if not payloads:
            QMessageBox.information(
                self, "Make markups editable",
                "There are no markups on this page to read out — what is on "
                "it is part of the sheet itself.")
            return 0
        scaled = payloads

        def mutate():
            page.pdf_annotations = False
            frame = page.frame
            if frame is not None:
                frame.forget_sharp_background()
                frame._background = None
                for payload in scaled:
                    item = build_item(dict(payload))
                    if item is not None:
                        frame.add_markup(item)
                frame.update()
        self._structural_change(f"Make {len(scaled)} markup(s) editable", mutate)
        self.status_hint.setText(
            f"{len(scaled)} markup(s) on this page can now be changed")
        return len(scaled)

    def color_processing(self, index: Optional[int] = None):
        """Document ▸ Color Processing, as Bluebeam's (ui/colorprocess.py)."""
        from .colorprocess import color_processing
        return color_processing(self, index)

    def change_colors(self, item):
        """A snapshot's Change Colors; a photo's Color Processing."""
        from .colorprocess import change_colors
        return change_colors(self, item)

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
        image = pdfio.page_raster(self.document, page)
        return None if image is None or image.isNull() else image

    # ==================================================================
    # tool sets
    # ==================================================================
    def add_to_toolset(self, item=None, into: str = "", ask: bool = True) -> None:
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
        # A calculation block is kept with the equations in it, as one tool.
        from ..items.calc import CalcBlockItem
        blocks = [one for one in items if isinstance(one, CalcBlockItem)]
        held = {id(m) for block in blocks for m in block.members()}
        items = [one for one in items if id(one) not in held]
        groups = toolsets.load_toolsets()
        names = [group.name for group in groups]
        if into in names and not ask:
            # chosen from Add to Tool Chest's own list (the Properties panel)
            chosen = into
        else:
            chosen, accepted = QInputDialog.getItem(
                self, "Add to Tool Set", "Tool set:", names,
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
            if isinstance(one, CalcBlockItem) and one.members():
                group.entries.append(toolsets.entry_for_block(one))
                continue
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

    def manage_toolsets(self):
        """Revu's Manage Tool Sets dialog. Returned so a test can drive it."""
        from .managetoolsets import ManageToolSetsDialog
        dialog = ManageToolSetsDialog(self)
        if self.interactive_prompts:
            dialog.exec()
        return dialog

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
        if not payload:
            decoded = _our_clipboard()
            if decoded:
                payload = decoded.get(CLIPBOARD_TAG) or []
                self._take_clipboard_assets(decoded)
        return payload

    def _take_clipboard_assets(self, decoded: dict) -> None:
        """A snapshot carries its images with it, so it can be pasted into a
        document that has never seen them."""
        try:
            for key, encoded in (decoded.get("assets") or {}).items():
                if not self.document.asset(key):
                    self.document.put_asset(key, base64.b64decode(encoded))
        except (ValueError, TypeError):
            pass

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
            rename_groups(copy, renamed)
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
            self.select_tool(key)
            self.view.set_pending_properties(entry.payload)
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
        to_scale = bool(payload.get("to_scale", False))
        for tool in TOOLS:
            if tool.factory is None:
                continue
            sample = tool.factory()
            if sample.TYPE != type_name:
                continue
            sample_kind = getattr(sample, "kind", "") or getattr(sample, "shape_kind", "")
            if kind and sample_kind != kind:
                continue
            # a plain rectangle and Sketch to Scale's are different tools
            if bool(getattr(sample, "to_scale", False)) != to_scale:
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
            # Outside whatever they are already in, so grouping two section
            # marks keeps each one a section mark.
            item.put_in_a_group(name)
            item.touch()
        self.view.commit_snapshot("Group markups")
        self.refresh_selection()
        self.status_hint.setText(f"Grouped {len(items)} markups — Ctrl+Shift+G "
                                 "takes them apart again")

    def ungroup_selection(self) -> None:
        """Take the selected groups apart, one layer at a time.

        A tool set brings groups across as the arrangement of groups they were
        made in — a section mark is a bubble and its label inside the group
        that adds the cut line. Taking the whole lot apart at once would give
        back a heap of loose markups; taking off the outer layer gives back
        the pieces somebody put together.
        """
        items = [i for i in self.selected_items()
                 if isinstance(i, MarkupItem) and i.group]
        if not items:
            self.status_hint.setText("Nothing grouped in the selection")
            return
        self.view.begin_snapshot(self.view.all_frames())
        for item in items:
            item.out_of_its_outer_group()
            item.touch()
        self.view.commit_snapshot("Ungroup markups")
        self.refresh_selection()
        inside = sum(1 for item in items if item.group)
        self.status_hint.setText(
            f"Ungrouped {len(items)} markups"
            + (f" — {inside} of them are still grouped inside" if inside else ""))

    def copy_selection(self) -> None:
        if self.view.tables.is_open() and self.view.tables.copy():
            return
        from . import calcedit
        if calcedit.clipboard(self.view.calc, "copy"):
            return
        if self.view.text_clipboard("copy"):
            self._clipboard = []
            return
            # clipboard now — otherwise the next paste puts the old ones back.
            self._clipboard = []
            return
        from ..items.calc import with_block_members
        items = with_block_members(self.selected_items())
        if not items:
            return
        self._clipboard = [item.serialize() for item in items]
        # Three things at once (decision 26): CalcForge's own copy under its own
        # type, which pastes live here and in another window of it; plain text
        # for anything that takes text ("Mu = 54 kN·m"); and a picture for
        # anything that takes pictures.
        mime = QMimeData()
        mime.setData(CLIPBOARD_TAG, json.dumps({CLIPBOARD_TAG: self._clipboard}).encode("utf-8"))
        words = [line for line in (_plain_text_of(item) for item in items) if line]
        if words:
            mime.setText("\n".join(words))
        picture = self._picture_of(items)
        if picture is not None and not picture.isNull():
            mime.setImageData(picture)
        QApplication.clipboard().setMimeData(mime)
        self.status_hint.setText(f"Copied {len(items)} markup(s)")

    def _picture_of(self, items) -> Optional[QImage]:
        """The copied markups as a picture, at print resolution, on white."""
        frames: dict = {}
        for item in items:
            frame = item.parentItem()
            if frame is not None and hasattr(frame, "paint_items"):
                frames.setdefault(id(frame), (frame, []))[1].append(item)
        if not frames:
            return None
        frame, chosen = next(iter(frames.values()))
        box = QRectF()
        for item in chosen:
            box = box.united(covered_rect(item))
        if box.isEmpty():
            return None
        scale = min(300 / 72.0, (16_000_000 / max(box.width() * box.height(), 1.0)) ** 0.5)
        image = QImage(max(round(box.width() * scale), 1),
                       max(round(box.height() * scale), 1), QImage.Format_ARGB32)
        image.fill(Qt.white)
        painter = QPainter(image)
        painter.scale(scale, scale)
        previous = frame.print_mode
        frame.print_mode = True           # no selection handles in the picture
        try:
            for item in chosen:
                item._handles_visible = False
            frame.paint_items(painter, chosen, box)
        finally:
            frame.print_mode = previous
            for item in chosen:
                item._handles_visible = True
            painter.end()
        return image

    def cut_selection(self) -> None:
        if self.view.tables.is_open() and self.view.tables.copy(cut=True):
            return
        from . import calcedit
        if calcedit.clipboard(self.view.calc, "cut"):
            return
        if self.view.text_clipboard("cut"):
            self._clipboard = []
            return
        self.copy_selection()
        self.delete_selection()

    def paste_items(self) -> None:
        if self.view.tables.is_open() and self.view.tables.paste():
            return
        from . import calcedit
        if calcedit.clipboard(self.view.calc, "paste"):
            return
        if self.view.text_clipboard("paste"):
            return
        payload = self._clipboard
        # A picture copied in another program is what the person wants pasted,
        # not whatever this window happened to copy last. Only the clipboard
        # knows what is really on it, so it is asked first.
        if self._clipboard_is_a_foreign_picture():
            if self.paste_picture_from_clipboard():
                return
        decoded = _our_clipboard()
        if decoded and CLIPBOARD_TAG in decoded:
            payload = decoded[CLIPBOARD_TAG]
            self._take_clipboard_assets(decoded)
        if not payload:
            return
        self._paste_payload(payload)

    def _paste_payload(self, payload: list) -> None:
        """Put a clipboard payload down under the pointer."""
        self.view.begin_snapshot()
        self.view.scene().clearSelection()
        # A paste lands under the pointer, the way it does in Bluebeam —
        # while the pointer is on what is in view. Gone from it (scrolled
        # away, or never on the canvas), the copy goes beside where it was
        # copied from, clear of it (QA F-31), rather than 14 pt over it.
        target = self.view.pointer_scene_pos()
        if not self.view.mapToScene(self.view.viewport().rect()).boundingRect().contains(target):
            target = None
        offset = None
        frame = self.view.frame()
        if target is None and payload:
            previews = [preview for preview in (build_item(entry) for entry in payload)
                        if preview is not None]
            offset = copy_step(previews)
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
            rename_groups(copy, renamed)
            if offset is not None:
                copy["x"] = copy.get("x", 0) + offset.x()
                copy["y"] = copy.get("y", 0) + offset.y()
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
        from ..items.calc import with_block_members
        items = with_block_members(self.selected_items())
        if not items:
            return
        self.view.begin_snapshot()
        self.view.scene().clearSelection()
        step = copy_step(items)
        for item in items:
            copy = item.clone()
            if copy is not None:
                copy.setPos(item.pos() + step)
                if hasattr(copy, "load_from_document"):
                    copy.load_from_document(self.document)
                self._frame_of(item).add_markup(copy)
                copy.setSelected(True)
        self.view.commit_snapshot("Duplicate")
        self.refresh_selection()

    def _frame_of(self, item):
        """The page *item* is on (a copy of it goes on the same page, not on
        whichever page the chrome calls current)."""
        frame = item.parentItem()
        return frame if hasattr(frame, "add_markup") else self.view.frame()

    def select_all(self) -> None:
        tables = self.view.tables
        if tables.is_open():
            rows, cols = tables.item.size
            tables.select((0, 0), (rows - 1, cols - 1), tables.active)
            return
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
        rects = {item: item.mapRectToScene(item.bounds_without_chrome()) for item in items}
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
        """Move or copy the selection at exact spacing, any number of times."""
        items = [i for i in self.selected_items() if self.view.editable(i)]
        if not items:
            self.status_hint.setText("Select something to move or duplicate first.")
            return
        page = self.current_page()
        scaled = page.scale.is_calibrated()
        dialog = dialogs.ArrayDialog(page.scale.display_unit if scaled else "mm",
                                     scaled, self,
                                     across=self._distance_text(copy_step(items, beside=True).x(), page))
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
                    self._frame_of(item).add_markup(copy)
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

    def _distance_text(self, points: float, page) -> Optional[str]:
        """*points* on the paper as a typed distance in the page's units (the
        inverse of distance_in_points), or None if it cannot be said."""
        try:
            if page.scale.is_calibrated():
                unit = page.scale.display_unit
                value = float((page.scale.length(1.0) * points).to(unit).magnitude)
            else:
                unit, value = "mm", points / MM_TO_PT
        except Exception:  # noqa: BLE001 - an odd scale keeps the dialog's own default
            return None
        return f"{value:.4g} {unit}"

    def distance_in_points(self, text: str, page) -> float:
        """Read a typed distance as page points, honouring the page scale."""
        text = (text or "").strip()
        if not text or text in ("0", "0.0"):
            return 0.0
        try:
            quantity = parse_unit(text)
        except Exception:  # noqa: BLE001 - a length in the wrong dimension raises
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

    def pick_markups(self, keys: list) -> None:
        """Select every markup picked in the markups list, on any page.

        With several selected, the style toolbar and Properties change them
        all together, as Bluebeam's list does.
        """
        wanted = {uid for _page, uid in keys}
        scene = self.view.scene()
        scene.clearSelection()
        for item in scene.markups():
            if item.uid in wanted:
                item.setSelected(True)
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

    def replace_image(self, item, source: str = "file") -> bool:
        """Put a different picture in an image already on the page, as Word does.

        *source* is "file" or "clipboard". The new picture keeps its own
        proportions and is fitted into the box the old one filled, from the
        same top-left corner — so a portrait photo swapped for a landscape
        one comes out as wide as the old one was, not stretched to its shape.
        One undo step.
        """
        found = self._image_from_clipboard() if source == "clipboard" \
            else self._image_from_a_file()
        if found is None:
            if source == "clipboard":
                self.status_hint.setText("Replace image: there is no picture on the clipboard")
            return False
        data, suffix = found
        pixmap = QPixmap()
        if not pixmap.loadFromData(QByteArray(data)) or pixmap.isNull():
            QMessageBox.warning(self, "Replace image", "That picture could not be read.")
            return False
        old = item.local_rect().normalized()
        self.view.begin_snapshot(self.view.involved_frames(item))
        item.prepareGeometryChange()
        item.asset_key = self.document.add_asset(data, suffix)
        item.load_from_document(self.document)
        fit = min(old.width() / max(pixmap.width(), 1),
                  old.height() / max(pixmap.height(), 1))
        item.set_local_rect(QRectF(old.left(), old.top(),
                                   max(pixmap.width() * fit, 1.0),
                                   max(pixmap.height() * fit, 1.0)))
        item.touch()
        item.update()
        self.view.commit_snapshot("Replace image")
        self.refresh_selection()
        return True

    def _image_from_a_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Replace image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff);;All files (*)")
        if not path:
            return None
        try:
            with open(path, "rb") as handle:
                data = handle.read()
        except OSError as exc:
            QMessageBox.critical(self, "Replace image", str(exc))
            return None
        return data, os.path.splitext(path)[1].lstrip(".").lower() or "png"

    @staticmethod
    def clipboard_has_image() -> bool:
        mime = QApplication.clipboard().mimeData()
        if mime is None:
            return False
        if mime.hasImage():
            return True
        return any(url.isLocalFile() and os.path.splitext(url.toLocalFile())[1].lower()
                   in (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff")
                   for url in mime.urls())

    def _image_from_clipboard(self):
        """The picture on the clipboard as PNG bytes, or a copied image file."""
        mime = QApplication.clipboard().mimeData()
        if mime is None:
            return None
        for url in mime.urls():
            if url.isLocalFile():
                path = url.toLocalFile()
                suffix = os.path.splitext(path)[1].lstrip(".").lower()
                if suffix in ("png", "jpg", "jpeg", "bmp", "gif", "webp", "tif", "tiff"):
                    try:
                        with open(path, "rb") as handle:
                            return handle.read(), suffix
                    except OSError:
                        pass
        image = QApplication.clipboard().image()
        if image.isNull():
            return None
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, "PNG")
        return bytes(buffer.data()), "png"

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

    def find_in_document(self, text: str = "") -> None:
        """Open the Search panel, with *text* searched for straight away."""
        self.show_panel("dock_search", True)
        panel = self.search_panel
        if text:
            panel.query.setText(text)
            panel.run()
        panel.query.setFocus(Qt.ShortcutFocusReason)
        panel.query.selectAll()

    def replace_in_document(self, _checked: bool = False) -> None:
        """Ctrl+H, Excel's and Word's Replace: the Search panel with its
        Replace box ready to type in — or the Find box first, when there is
        nothing to look for yet."""
        self.show_panel("dock_search", True)
        panel = self.search_panel
        box = panel.replacement if panel.query.text() else panel.query
        box.setFocus(Qt.ShortcutFocusReason)
        box.selectAll()

    # -- the spreadsheet's Page Layout from the menu bar (novice 11) -------------
    def _sheet_for_layout(self):
        """(spreadsheet, active cell, cells picked out) that Calculation ▸
        Page Layout acts on: the spreadsheet open for typing, else the one on
        the page in view (no active cell then); (None, None, None) when there
        is neither."""
        tables = self.view.tables
        item = tables.item
        if item is not None and getattr(item, "SHEET_RUN", False):
            return item, tuple(tables.active), list(tables.selection())
        if self.current_page().sheet is not None:
            from .sheetlayout import _run_item
            item = _run_item(self, self.current_index)
            if item is not None:
                return item, None, None
        return None, None, None

    def _refresh_page_layout_menu(self) -> None:
        from . import sheetlayout
        item, cell, area = self._sheet_for_layout()
        self.act_insert_page_break.setEnabled(cell is not None and (cell[0] > 0 or cell[1] > 0))
        self.act_remove_page_break.setEnabled(
            cell is not None and sheetlayout.has_break(item, *cell))
        self.act_reset_page_breaks.setEnabled(item is not None)
        self.act_set_print_area.setEnabled(area is not None)
        self.act_clear_print_area.setEnabled(item is not None)

    def _page_layout_menu_closed(self) -> None:
        """Greyed only while the menu is open: a key bound to one of them
        still works out what it can do when it is pressed."""
        for action in (self.act_insert_page_break, self.act_remove_page_break,
                       self.act_reset_page_breaks, self.act_set_print_area,
                       self.act_clear_print_area):
            action.setEnabled(True)

    def insert_page_break(self, _checked: bool = False) -> None:
        from . import sheetlayout
        item, cell, _area = self._sheet_for_layout()
        if cell is None:
            self.status_hint.setText("Click the cell the new page starts at first")
            return
        sheetlayout.insert_break(self, item, *cell)

    def remove_page_break(self, _checked: bool = False) -> None:
        from . import sheetlayout
        item, cell, _area = self._sheet_for_layout()
        if cell is not None:
            sheetlayout.remove_break(self, item, *cell)

    def reset_page_breaks(self, _checked: bool = False) -> None:
        from . import sheetlayout
        item, _cell, _area = self._sheet_for_layout()
        if item is not None:
            sheetlayout.reset_breaks(self, item)

    def set_print_area(self, _checked: bool = False) -> None:
        from . import sheetlayout
        item, _cell, area = self._sheet_for_layout()
        if area is not None:
            sheetlayout.set_print_area(self, item, area)

    def clear_print_area(self, _checked: bool = False) -> None:
        from . import sheetlayout
        item, _cell, _area = self._sheet_for_layout()
        if item is not None:
            sheetlayout.set_print_area(self, item, None)

    def find_a_tool(self) -> None:
        """Type what you want to do; it says which tool does it.

        Fifty tools is more than anybody keeps in their head, and the answer
        to "how do I cloud this" should not be hunting along a toolbar. What
        is searched is every tool's name, what it is for, and the key it is
        on, so "revision", "cloud" and "C" all find the same thing.
        """
        # Not a pop-up: the search field is where searching happens, and its
        # dropdown lists everything that matches while it is typed.
        field = getattr(self, "search_field", None)
        if field is not None and field.isVisible():
            field.setFocus(Qt.ShortcutFocusReason)
            field.selectAll()
            return
        from PySide6.QtWidgets import QInputDialog

        wanted, said = QInputDialog.getText(
            self, "Find a Tool", "What do you want to do?")
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


    def _center_page_bar(self) -> None:
        status = self.statusBar()
        viewport = self.view.viewport()
        if isinstance(status, CenteredStatusBar) and viewport.isVisible():
            middle = viewport.mapToGlobal(QPoint(viewport.width() // 2, 0)).x()
            status.center_on(middle)

    def _refresh_lists_soon(self) -> None:
        """The markups changed: the lists are rebuilt once the burst is over,
        not once per markup — pasting or opening a thousand markups rebuilt
        the markups list a thousand times (2026-10-05)."""
        timer = getattr(self, "_lists_timer", None)
        if timer is None:
            timer = self._lists_timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self.refresh_lists)
        if not timer.isActive():
            timer.start(0)

    def refresh_lists(self) -> None:
        timer = getattr(self, "_lists_timer", None)
        if timer is not None:
            timer.stop()
        self.markups_panel.refresh(self.document)
        self.sync_text_bookmarks()
        self.bookmarks_panel.rebuild(self.document)
        self.variables_panel.watch(self.document)
        self.sheet_tabs.refresh()

    # ==================================================================
    # bookmarks
    # ==================================================================
    # -- text boxes as bookmarks, fields in text boxes (the user, 2026-10-15) --
    def _text_box_menu(self, menu, item) -> None:
        mark = menu.addAction("Bookmark")
        mark.setCheckable(True)
        mark.setChecked(bool(getattr(item, "auto_bookmark", False)))
        mark.setToolTip("A bookmark titled with this text, that goes wherever the box goes")
        mark.toggled.connect(lambda on: self.set_text_bookmark(item, on))
        fields = menu.addMenu("Insert Field")
        fields.setObjectName("menuInsertField")
        variables = bindable.data_menu(fields.addMenu("Variable"))      # their names
        names = self.variable_names()
        for name in names[:60]:
            variables.addAction(name, lambda n=name: self.insert_text_field(item, "{=" + n + "}"))
        if not names:
            nothing = variables.addAction("No Variables Yet")
            nothing.setEnabled(False)
        fields.addSeparator()
        from .dialogs import FIELD_CHOICES
        for label, token in FIELD_CHOICES:
            fields.addAction(label, lambda t=token: self.insert_text_field(item, t))

    def variable_names(self) -> list:
        from .variablespanel import variable_rows
        seen: list = []
        try:
            rows = variable_rows(self.document)
        except Exception:  # noqa: BLE001
            return []
        for row in rows:
            if row.value != "function" and row.name not in seen:
                seen.append(row.name)
        return seen

    def insert_text_field(self, item, token: str) -> None:
        """A field at the caret of a box being typed in, or at the end of one
        that is not; one undo step."""
        from PySide6.QtGui import QTextCursor
        editor = getattr(item, "_editor", None)
        if getattr(item, "_editing", False) and editor is not None:
            editor.textCursor().insertText(token)
            return
        self.view.begin_snapshot(self.view.involved_frames(item))
        cursor = QTextCursor(item.doc)
        cursor.movePosition(QTextCursor.End)
        text = item.doc.toPlainText()
        cursor.insertText(("" if not text or text.endswith((" ", "\n")) else " ") + token)
        item.written = item.doc.toPlainText()
        item.touch()
        if hasattr(item, "apply_style"):
            item.apply_style()
        item.update()
        self.view.commit_snapshot("Insert field")

    def set_text_bookmark(self, item, on: bool) -> None:
        self.view.begin_snapshot(self.view.involved_frames(item))
        item.auto_bookmark = bool(on)
        item.touch()
        self.view.commit_snapshot("Bookmark" if on else "Remove bookmark")
        self.sync_text_bookmarks()
        self.bookmarks_panel.rebuild(self.document)
        # said (F-35): the bookmark is in a panel that may well be shut
        from ..items.fields import shown_text
        words = (shown_text(item).strip().splitlines() or ["Text"])[0][:60]
        self.status_hint.setText(f"Bookmarked “{words}”: it goes wherever the box goes"
                                 if on else f"Bookmark “{words}” removed")

    def sync_text_bookmarks(self) -> bool:
        """Each text box marked as a bookmark has one: its words for a title,
        its page — whichever it has been moved to — and its place on it. A
        box deleted takes its bookmark with it. True if anything changed."""
        from ..core.document import Bookmark
        from ..items.fields import shown_text
        from ..items.text import _TextBase
        if self.scene is None:
            return False
        boxes = {}
        for frame in self.scene.frames:
            for item in frame.markups():
                if isinstance(item, _TextBase) and getattr(item, "auto_bookmark", False):
                    boxes[item.uid] = (item, frame)
        changed = False
        kept = []
        for mark in self.document.bookmarks:
            if mark.markup and mark.markup not in boxes:
                changed = True                       # its box has gone
                continue
            kept.append(mark)
        by_box = {mark.markup: mark for mark in kept if mark.markup}
        for uid, (item, frame) in boxes.items():
            words = shown_text(item).strip().splitlines()
            title = (words[0].strip() if words else "")[:80] or "Text"
            place = (title, frame.page.uid, round(float(item.pos().y()), 2))
            mark = by_box.get(uid)
            if mark is None:
                kept.append(Bookmark(*place, markup=uid))
                changed = True
            elif (mark.title, mark.page_uid, round(mark.y, 2)) != place:
                mark.title, mark.page_uid, mark.y = place
                changed = True
        if changed:
            self.document.bookmarks = kept
        return changed

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
        title, accepted = QInputDialog.getText(self, "Add Bookmark", "Name:",
                                               text=suggestion)
        if not accepted:
            return
        self.change_bookmarks("Add bookmark",
                              lambda: self.document.add_bookmark(title, index, y))
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
        title, accepted = QInputDialog.getText(self, "Add Bookmark", "Name:",
                                               text=suggestion)
        if not accepted or not title.strip():
            return
        self.change_bookmarks("Add bookmark",
                              lambda: self.document.add_bookmark(title.strip(), index, 0.0))
        self.status_hint.setText(f"Bookmarked “{title.strip()}”")

    # -- format painter ----------------------------------------------------
    #
    # Bluebeam's: pick up one markup's look, then click others to paint it on.
    # It is held until it is used or Esc is pressed, and the status bar says so
    # the whole time, because an invisible mode that changes what clicking does
    # is the kind of thing that ruins an afternoon.
    # Which style fields each kind of appearance control stands for: what a
    # markup can show is what it can be painted with, and nothing more.
    PAINTED_FIELDS = {
        "stroke": ("stroke",),
        "fill": ("fill",),
        "width": ("width",),
        "dash": ("line_style", "dash_array", "dash_scale"),
        "hatch": ("hatch", "hatch_scale", "hatch_color", "hatch_tile"),
        "opacity": ("opacity",),
        "fill_opacity": ("fill_opacity",),
        "font": ("font_family", "font_size", "bold", "italic", "underline",
                 "strikethrough", "superscript", "subscript", "font_auto",
                 "text_color", "align", "valign"),
        "arrow_size": ("arrow_size", "arrow_start_size", "arrow_start", "arrow_end"),
    }

    def format_painter(self) -> None:
        """Pick up the selected markup's look — or put the painter down.

        As Bluebeam's: every appearance property is picked up — colour, fill,
        both opacities, line width, line type and its spacing, hatch, line
        endings, the whole of the font and the cloud's size — and none of its
        size, its words or what it measures. It stays in hand, clicked onto
        one markup after another or dragged round several, until Esc or the
        button is pressed again.
        """
        from copy import deepcopy
        from .stylecaps import capabilities

        items = self.selected_items()
        if self._held_style is not None:
            self.put_the_format_painter_down()
            return
        if not items:
            self.status_hint.setText("Pick the markup whose look you want first")
            return
        source = items[0]
        self._held_style = {
            "source_type": source.TYPE,
            "source_name": source.display_name().lower(),
            "style": deepcopy(source.style.to_dict()),
            "controls": set(capabilities(source)),
            "cloud": (source.cloud_size, source.cloud_invert)
            if self._is_clouded(source) else None,
            "corner_radius": source.style.corner_radius,
        }
        from .view import format_painter_cursor
        self.view.setCursor(format_painter_cursor())
        self.status_hint.setText(
            f"Format painter: click, or drag round, what should look like this "
            f"{self._held_style['source_name']} · Esc to put it down")

    @staticmethod
    def _is_clouded(item) -> bool:
        return (getattr(item, "kind", "") == "cloud"
                or getattr(item, "shape_kind", "") == "cloud"
                or bool(getattr(item, "clouds_a_region", lambda: False)()))

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
        return self.paint_format_onto_all([item]) > 0

    def paint_format_onto_all(self, items) -> int:
        """Give every one of *items* the held look, as one undo step."""
        from .stylecaps import capabilities

        held = self._held_style
        items = [item for item in items if item is not None]
        if held is None or not items:
            return 0
        self.view.begin_snapshot(self.view.involved_frames(*items))
        painted = 0
        for item in items:
            controls = held["controls"] & set(capabilities(item))
            if not controls:
                continue
            for control in controls:
                for field_name in self.PAINTED_FIELDS.get(control, ()):
                    if field_name in held["style"]:
                        value = held["style"][field_name]
                        if isinstance(value, (list, dict)):
                            from copy import deepcopy
                            value = deepcopy(value)
                        if field_name == "dash_array":
                            value = tuple(value)
                        setattr(item.style, field_name, value)
            if held.get("cloud") and self._is_clouded(item):
                item.prepareGeometryChange()
                item.cloud_size, item.cloud_invert = held["cloud"]
            if getattr(item, "kind", "") == "rect" and held["source_type"] == item.TYPE:
                item.style.corner_radius = held["corner_radius"]
            if hasattr(item, "apply_style"):
                item.apply_style()
            item.touch()
            item.update()
            painted += 1
        self.view.commit_snapshot("Format painter")
        self.refresh_selection()
        from .view import format_painter_cursor
        self.view.setCursor(format_painter_cursor())
        if not painted:
            self.status_hint.setText("Format painter: that markup has none of those properties")
        return painted

    def hide_selection(self) -> None:
        """Take the selected markups off the page without deleting them."""
        # not equations: hiding one would quietly take its values out of the
        # calculation (decision 17)
        items = [i for i in self.selected_items() if isinstance(i, MarkupItem)
                 and not getattr(i, "IS_CALC", False)]
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
        """Right-click ▸ Flatten: the selected markups, at once, with Revu's
        default settings — recoverable with Unflatten. The choices are in
        Document ▸ Flatten Markups (the user, 2026-10-15)."""
        # Equations are already written into the page on every save
        # (decision 3); flattening one would only stop it calculating.
        items = [i for i in self.selected_items() if isinstance(i, MarkupItem)
                 and not getattr(i, "IS_CALC", False)]
        if not items:
            return
        self._flatten_items(items, True)

    @staticmethod
    def _flatten_type(item) -> str:
        """The markup's type as Flatten Markups' Type list names it: Cloud,
        Length, Text box — what it is, never the label somebody gave it."""
        from ..items.measure import CountItem, MEASURE_NAMES, MeasureItem

        kind_name = getattr(item, "NAME_FOR_KIND", None)
        if kind_name:
            return kind_name
        if isinstance(item, CountItem):
            return "Count"
        if isinstance(item, MeasureItem):
            return MEASURE_NAMES.get(item.kind, "Measurement")
        return getattr(item, "NAME", "Markup")

    def _flattenable(self) -> list:
        """(page index, markup) for every markup Flatten Markups could take."""
        return [(index, item) for index, page in enumerate(self.document.pages)
                if page.frame is not None
                for item in page.frame.markups()
                if not item.flattened
                and not item.from_drawing
                and not getattr(item, "IS_CALC", False)]

    def flatten_dialog(self) -> "dialogs.FlattenDialog":
        """Revu's Flatten Markups, filled from this document; not yet shown."""
        from . import preferences

        selected = [i for i in self.selected_items() if isinstance(i, MarkupItem)
                    and not getattr(i, "IS_CALC", False) and not i.flattened]
        types = sorted({self._flatten_type(item) for _index, item in self._flattenable()},
                       key=str.lower)
        picked = self.selected_pages()
        dialog = dialogs.FlattenDialog(
            types, self, selected_markups=len(selected),
            recoverable=preferences.current().recover_flattened,
            count=len(self.document.pages), current=self.current_index,
            selected_pages=picked if len(picked) > 1 else [])
        dialog.markups_selected = selected      # as they were when it opened
        return dialog

    def flatten_document(self) -> None:
        """Document ▸ Flatten Markups: Revu's dialog, then the flattening."""
        dialog = self.flatten_dialog()
        if dialog.exec() != dialogs.QDialog.Accepted:
            return
        self.finish_flatten(dialog)

    def finish_flatten(self, dialog) -> int:
        """Flatten what *dialog* chose; how many markups that was."""
        from . import preferences

        # Allow Markup Recovery is remembered for next time, as Revu does.
        recoverable = dialog.recoverable()
        prefs = preferences.current()
        if prefs.recover_flattened != recoverable:
            prefs.recover_flattened = recoverable
            preferences.save(prefs)
        pages = set(dialog.page_indexes() or [])
        types = dialog.chosen_types()
        scope = dialog.scope()
        chosen = getattr(dialog, "markups_selected", [])
        panel = self.markups_panel
        needle = panel.filter.text().strip().lower()
        items = []
        for index, item in self._flattenable():
            if index not in pages or self._flatten_type(item) not in types:
                continue
            if scope == dialog.SELECTED_MARKUPS and not any(item is c for c in chosen):
                continue
            # Exclude Filtered Markups: what the Markups list's filter hides
            if scope == dialog.EXCLUDE_FILTERED and \
                    not panel._shown(panel.row_for(index, item), needle):
                continue
            items.append(item)
        if not items:
            self.status_hint.setText("Nothing matched those flatten choices")
            return 0
        self._flatten_items(items, recoverable)
        return len(items)

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
                    box = covered_rect(item)
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
        suffix = " · Unflatten can restore them" if recoverable else " · source discarded"
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

    def apply_to_pages_dialog(self) -> "dialogs.ApplyToPagesDialog":
        """Revu's Apply to Pages, a Custom Range of the pages picked in
        Thumbnails when there are some; not yet shown."""
        here = self.document.index_of(self.current_page())
        landscapes = [page.width_pt > page.height_pt for page in self.document.pages]
        picked = [i for i in self.thumbnail_selection() if i != here]
        return dialogs.ApplyToPagesDialog(landscapes, here, picked, self)

    def apply_to_pages(self, item, pages: Optional[list] = None) -> None:
        """Put a copy of this markup on other pages, in the same place."""
        if item is None or len(self.document.pages) < 2:
            self.status_hint.setText("Apply to Pages: this document has only the one page "
                                     "— there is no other page to copy it to")
            return
        if pages is None:
            dialog = self.apply_to_pages_dialog()
            if self.interactive_prompts and dialog.exec() != dialogs.QDialog.Accepted:
                return
            self.finish_apply_to_pages(item, dialog)
            return
        self._copy_onto_pages(item, pages)

    def finish_apply_to_pages(self, item, dialog) -> int:
        """Copy *item* onto the pages *dialog* chose; how many it went on."""
        return self._copy_onto_pages(item, dialog.page_indexes() or [])

    def _copy_onto_pages(self, item, pages) -> int:
        here = self.document.index_of(self.current_page())
        others = [index for index in sorted(set(pages))
                  if 0 <= index < len(self.document.pages) and index != here]
        if not others:
            self.status_hint.setText("No pages to put it on")
            return 0
        # a group goes over whole, as one group on each page (F-11)
        members = self.view.group_of(item) if getattr(item, "group", "") else [item]
        payloads = [(member.serialize(), QPointF(member.pos())) for member in members]
        frames = [self.document.pages[index].frame for index in others
                  if self.document.pages[index].frame is not None]
        self.view.begin_snapshot(frames)
        from ..items.base import rename_groups
        for frame in frames:
            renamed: dict = {}            # one fresh group per page
            for payload, where in payloads:
                data = dict(payload, uid=os.urandom(8).hex())
                rename_groups(data, renamed)
                copy = build_item(data)
                if copy is not None:
                    frame.add_markup(copy, where)
        self.view.commit_snapshot("Apply to Pages")
        self.status_hint.setText(f"Copied onto {len(frames)} page(s)")
        return len(frames)

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
        if not getattr(item, "CAN_LEAD", True):
            return                    # Calculation text never becomes a callout
        arrow = menu.addAction("Add Arrow Leader",
                               lambda: self.add_leader_to(item, "arrow"))
        arrow.setToolTip("A line with a head on it, dragged to what it is about")
        cloud = menu.addAction("Add Cloud Leader",
                               lambda: self.add_leader_to(item, "cloud"))
        cloud.setToolTip("A revision cloud round the area, joined to the note "
                         "by a plain line")
        # The same pictures as the Callout and Cloud+ tools: what gets added
        # is that kind of call-out's leader.
        arrow.setIcon(icon("callout"))
        cloud.setIcon(icon("cloud_callout"))
        # A Cloud+'s own cloud is its body, not a leader to take away (F-12:
        # Remove Leader deleted it): only its other leaders are offered.
        body = item.cloud_leader() if hasattr(item, "cloud_leader") else None
        removable = [i for i, leader in enumerate(getattr(item, "leaders", []))
                     if leader is not body]
        which = item.leader_near(item.mapFromScene(scene_pos))
        if which not in removable:
            which = removable[-1] if removable else None
        if which is not None:
            menu.addAction("Remove Leader",
                           lambda i=which: self.remove_leader_from(item, i))

    def add_leader_to(self, item, kind: str = "arrow") -> None:
        """Another leader on this note — placed, not guessed at.

        Both kinds ask where before anything changes: an arrow wants the thing
        it points at, a cloud wants the area it goes round. Putting an arrow
        down beside the note and leaving it to be dragged made every leader
        two gestures, the first of them wrong.
        """
        if not getattr(item, "CAN_LEAD", True):
            return
        if kind == "cloud":
            self.view.begin_cloud_leader(item)
            return
        self.view.begin_arrow_leader(item)

    def finish_arrow_leader(self, item, scene_point: QPointF) -> None:
        """Put the new arrow leader at the place that was clicked.

        A text box given a leader is a call-out, so it becomes one — the three
        are one object in different states, and this is the state changing.
        """
        where = item.mapFromScene(scene_point)
        item = self.becomes_a_callout(item)
        item.add_leader(where)
        item.touch()
        item.update()
        self.view.commit_snapshot("Add leader")
        self.refresh_selection()
        self.status_hint.setText(
            f"{len(item.leaders)} leader(s) — drag the head to move it")

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
        if item is None or not isinstance(item, _TextBase) or not getattr(item, "CAN_LEAD", True):
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
        if isinstance(item, CalloutItem) or not isinstance(item, TextItem) \
                or not getattr(item, "CAN_LEAD", True):
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

        before = prefs_module.current().result_format()
        dialog = dialogs.PreferencesDialog(prefs_module.current(), self)
        if dialog.exec() != dialogs.QDialog.Accepted:
            return
        self.apply_preferences(dialog.result_preferences(), before)

    def apply_preferences(self, prefs, before: Optional[dict] = None) -> None:
        """Adopt *prefs*. A changed result format is this document's too
        (SMath's Tools > Options is the worksheet's), and new documents'."""
        from . import preferences as prefs_module

        prefs_module.apply(prefs)
        # Filtered Annotation Dim Percent: the page's dimming at the new level
        panel = getattr(self, "markups_panel", None)
        if panel is not None and hasattr(panel, "dim_filtered_now"):
            panel.dim_filtered_now()
        if before is not None and prefs.result_format() != before:
            from ..calc.docsheet import sheet_for
            self.document.settings.calc_format = dict(
                self.document.settings.calc_format or {}, **prefs.result_format())
            sheet = sheet_for(self.document)
            sheet.adopt_format()
            sheet.recalculate(force=True)
            self.mark_modified()
        self.view.use_the_graphics_card(prefs.gpu_drawing)
        self.view.viewport().update()
        self.status_hint.setText("Preferences saved")

    @staticmethod
    def _adopt_calc_defaults(document) -> None:
        """A document that has not said how to show results takes
        Preferences' way (a new one, or a PDF opened for the first time)."""
        if getattr(document.settings, "calc_format", None):
            return
        from . import preferences as prefs_module
        document.settings.calc_format = prefs_module.current().result_format()
        sheet = getattr(document, "_calc_sheet", None)
        if sheet is not None:
            sheet.adopt_format()

    def toggle_bold(self) -> bool:
        """Embolden the words. Says whether it found any.

        Four places count, in the order the caret would be found in them: a
        run of text selected inside a box being typed into, that whole box,
        the cells picked out in a table, and the text markups selected on the
        page. Returning False is what tells Ctrl+B it is free to mean
        "bookmark" instead.
        """
        if self._format_equations("bold"):
            return True
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

    def toggle_strikethrough(self) -> bool:
        """Strike the words through (Revu's Strikethrough), where Bold looks."""
        return self._toggle_text_style("strikethrough")

    def toggle_superscript(self) -> bool:
        """Set the words above the line (Revu's Superscript)."""
        return self._toggle_text_style("superscript")

    def toggle_subscript(self) -> bool:
        """Set the words below the line (Revu's Subscript)."""
        return self._toggle_text_style("subscript")

    def _toggle_text_style(self, which: str) -> bool:
        """A Font Style — bold, italic, underline, strikethrough, superscript
        or subscript — wherever the words happen to be."""
        if which in ("bold", "italic", "underline") and self._format_equations(which):
            return True
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
                markup.style.set_font_style(which, wanted)
                markup.apply_style()
                markup.touch()
                markup.update()
            self.view.commit_snapshot(which.capitalize())
            return True
        if not hasattr(item, "style") or item.locked:
            return False
        self.view.begin_snapshot(self.view.involved_frames(item))
        item.style.set_font_style(which, not getattr(item.style, which))
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
        elif which == "strikethrough":
            fmt.setFontStrikeOut(not current.strikeOut())
        elif which in ("superscript", "subscript"):
            level = (QTextCharFormat.AlignSuperScript if which == "superscript"
                     else QTextCharFormat.AlignSubScript)
            fmt.setVerticalAlignment(QTextCharFormat.AlignNormal
                                     if cursor.charFormat().verticalAlignment() == level
                                     else level)
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

    def change_bookmarks(self, description: str, mutate) -> bool:
        """Add, rename or remove bookmarks as one undo step (exercise round
        1, F-08: Add Bookmark changed the document with nothing to undo).
        False when nothing changed."""
        from ..core.document import Bookmark
        before = [mark.to_dict() for mark in self.document.bookmarks]
        mutate()
        after = [mark.to_dict() for mark in self.document.bookmarks]
        if after == before:
            return False

        def restore(marks: list) -> None:
            self.document.bookmarks = [Bookmark.from_dict(mark) for mark in marks]
            self.bookmarks_changed()

        self.undo_stack.push(DocumentStructureCommand(before, after, description, restore))
        self.bookmarks_changed()
        return True

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
        path, _ = QFileDialog.getSaveFileName(self, "Export to PDF",
                                              in_start_folder(suggested + ".pdf", self.document),
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
        dpi, ok = QInputDialog.getInt(self, "Export Images", "Resolution (dpi):", 200, 72, 600)
        if not ok:
            return
        try:
            written = export_io.export_images(self.document, folder, dpi,
                                              self.document.title or "page")
        except Exception as exc:
            QMessageBox.critical(self, "Export images", str(exc))
            return
        self.status_hint.setText(f"Wrote {len(written)} image(s) to {folder}")

    def export_markups(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Summary",
                                              in_start_folder("markups.csv", self.document),
                                              "CSV files (*.csv)")
        if not path:
            return
        try:
            count = export_io.export_markups_csv(self.document, path)
        except Exception as exc:
            QMessageBox.critical(self, "Summary", str(exc))
            return
        self.status_hint.setText(f"Exported {count} markup(s)")


    def open_print_dialog(self, selected=None, which: Optional[str] = None) -> "PrintDialog":
        """Revu's Print dialog, its preview folded in, shown over the window
        (File ▸ Print…, File ▸ Print Preview… and Print Pages… all open it).
        *selected*: the pages Selected stands for, when it is offered —
        else what Thumbnails has picked out."""
        from .printdialog import PrintDialog, RANGE_KEY
        from .widgets import PagesRange
        from ..settings import app_settings

        if selected is None:
            selected = self.thumbnail_selection()
        if which is None:
            remembered = str(app_settings().value(RANGE_KEY, PagesRange.ALL))
            which = remembered if remembered in (PagesRange.ALL, PagesRange.CURRENT) \
                else PagesRange.ALL
        old = getattr(self, "print_dialog", None)
        if old is not None:
            # the last one is let go only now, so what it printed can still
            # be read after it closed
            try:
                old.close()
                old.deleteLater()
            except RuntimeError:
                pass
        dialog = PrintDialog(self, self.current_index, selected, which)
        self.print_dialog = dialog
        dialog.show()
        return dialog

    def print_document(self) -> "PrintDialog":
        """File ▸ Print… (Ctrl+P): Revu's Print dialog."""
        return self.open_print_dialog()

    def print_preview(self) -> "PrintDialog":
        """File ▸ Print Preview…: the same Print dialog — Revu has no
        separate preview; its Print dialog has one (the user, Round 3)."""
        return self.open_print_dialog()

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
                 settings.snap_to_alignment),
                (getattr(self, "act_snap_pdf_alignment", None),
                 settings.snap_to_pdf_alignment)):
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

    def toggle_pdf_alignment_snap(self, on: bool) -> None:
        self.document.settings.snap_to_pdf_alignment = bool(on)
        self._say_snap_state()

    def toggle_margins(self, on: bool) -> None:
        self.document.settings.show_margins = on
        self._refresh_all_scenes()

    def toggle_name_tags(self, on: bool) -> None:
        self.document.settings.show_name_tags = bool(on)
        if self.scene is not None:
            for item in self.scene.items():
                if getattr(item, "sheet", None) is not None:
                    item.update()          # a cached table draws itself again
        self._refresh_all_scenes()

    def mark_menu_buttons(self) -> None:
        """Every bar button with a menu — on the toolbars, the Properties bar
        (a table's controls too) and the status bar — gets room for its
        arrow, as Revu's split buttons have: the icon, then the arrow part
        beside it. Qt decides a button's popup mode after it is polished, so
        the theme is told by a property of its own and the button polished
        again (an arrow drawn over the icon: the user, 2026-10-18)."""
        roots = list(self.findChildren(QToolBar)) + [self.statusBar()]
        for root in roots:
            for button in root.findChildren(QToolButton):
                if button.objectName() == "qt_toolbar_ext_button":
                    continue
                has_menu = button.menu() is not None or (
                    button.defaultAction() is not None
                    and button.defaultAction().menu() is not None)
                kind = ""
                if has_menu and button.popupMode() == QToolButton.MenuButtonPopup:
                    kind = "split"
                elif has_menu and button.popupMode() == QToolButton.InstantPopup:
                    kind = "only"
                if (button.property("menuButton") or "") == kind:
                    continue
                button.setProperty("menuButton", kind)
                button.style().unpolish(button)
                button.style().polish(button)
                button.updateGeometry()

    def _refresh_status_icons(self) -> None:
        for button, name in getattr(self, "_status_icon_buttons", {}).items():
            button.setIcon(icon(name))
        # the » of every toolbar and of the menu bar, in the theme's ink
        holders = list(getattr(self, "toolbars", [])) + [self.menuBar()]
        for holder in holders:
            for name in ("qt_toolbar_ext_button", "qt_menubar_ext_button"):
                for button in holder.findChildren(QToolButton, name):
                    button.setIcon(icon("overflow"))

    def refresh_icons(self) -> None:
        """Redraw every icon in the colours of the theme now in use."""
        for action, name in self._icon_names.items():
            action.setIcon(icon(name))
        self._refresh_status_icons()
        # the style bar's line and hatch samples, in the theme's ink: drawn
        # near-black they were invisible on the dark bar (the user, 2026-10-01)
        fill_line_style_combo(self.dash_combo, _bar_ink(), 1, self._line_style_shown(),
                              bool(self.dash_combo.property("cloudStyles")))
        for index in range(self.hatch_combo.count()):
            if self.hatch_combo.itemData(index) in HATCH_PATTERNS:   # not Manage…
                self.hatch_combo.setItemIcon(
                    index, _hatch_icon(self.hatch_combo.itemData(index) or "", _bar_ink()))
        from . import propbar
        propbar.refresh_icons(self)
        for dock in self.panels:
            bar = dock.titleBarWidget()
            if hasattr(bar, "refresh_icons"):
                bar.refresh_icons()
        # the panel rails' icons too: drawn for the old theme they all but
        # vanished on the new one
        for rail in (self.left_rail, self.right_rail):
            for name, button in rail.buttons.items():
                if name in self.PANEL_ICONS:
                    button.setIcon(icon(self.PANEL_ICONS[name][1]))
        self.markups_panel.rebuild(self.document)

    def toggle_theme(self, dark: bool) -> None:
        from ..app import apply_theme
        from ..theme import CANVAS, DARK, LIGHT

        theme = DARK if dark else LIGHT
        application = QApplication.instance()
        if application is not None:
            apply_theme(application, theme)
        from . import nativeframe
        nativeframe.follow_theme()           # Windows' caption buttons too
        self._mark_active_pane()
        if self.scene is not None:
            self.scene.set_canvas_colour(CANVAS[theme])
        self.refresh_icons()
        self._refresh_all_scenes()
        self._wrap_toolbar_rows_soon()          # the new style's buttons may be wider
        rulers = getattr(self.view, "rulers", None)
        if rulers is not None:
            rulers.refresh()                 # their ground and corner follow the theme
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
        """The pointer's place in the status bar, at most every 30 ms: set on
        every mouse move it laid the status bar out again under a pan or a
        drag, many times a frame."""
        self._position_wanted = QPointF(point)
        timer = getattr(self, "_position_timer", None)
        if timer is None:
            timer = self._position_timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(30)
            timer.timeout.connect(lambda: self._write_position(self._position_wanted))
        if not timer.isActive():
            timer.start()

    def _write_position(self, point: QPointF) -> None:
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
        """What can be done to this shape's corners and sides, as Revu names
        it: Control Point ▸ (Add / Subtract Control Point), Arc Segment and
        Round All Corners — and CalcForge's own corner rounding and drafting
        break symbol, kept in Control Point ▸.

        The same things the held keys do, for anyone who would rather read
        them than remember them. The pointer picks which corner and which
        side, and when it is not near either of them — right in the middle of
        a big rectangle, say — the nearest are offered and the tooltip says
        so. A straight two-point line has no corner to round and no side to
        arc (QA round 4), so it is offered neither.
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
        straight = isinstance(item, PolyItem) and not item.closed and len(item.points) == 2

        points = menu.addMenu("Control Point")
        if segment is not None:
            add = points.addAction(
                "Add Control Point", lambda: self._reshape(
                    item, "add", segment, local if on_a_side else None))
            add.setToolTip(f"Put a point in {this_side} side; Shift and the pointer "
                           "does this too")
        from .view import fewest_corners
        if vertex is not None and len(corners) > fewest_corners(item):
            take_out = points.addAction("Subtract Control Point",
                                        lambda: self._reshape(item, "delete", vertex))
            take_out.setToolTip(
                f"Remove {this_corner} point; Shift and the pointer does this too")
        if vertex is not None and not straight:
            rounded = item.is_rounded(vertex)
            round_off = points.addAction(
                "Sharpen Corner" if rounded else "Round Corner",
                lambda: self._reshape(item, "round", vertex))
            round_off.setToolTip(
                f"{'Sharpen' if rounded else 'Round'} {this_corner} "
                "corner; Ctrl and the pointer over a corner does this too")
        if segment is not None:
            points.addSeparator()             # CalcForge's own
            broken = bool(item.broken.get(segment))
            break_action = points.addAction(
                "Remove Break" if broken else "Insert Break",
                lambda: self._reshape(item, "break", segment))
            break_action.setToolTip(
                f"{'Remove' if broken else 'Insert'} the structural break symbol "
                f"on {this_side} side")
        if segment is not None and not straight:
            curved = item.is_curved(segment)
            curve = menu.addAction(
                "Straighten Segment" if curved else "Arc Segment",
                lambda: self._reshape(item, "curve", segment))
            curve.setToolTip(f"Change {this_side} side between straight and arced; "
                             "Ctrl and the pointer over a side does this too")
        roundable = self._roundable_corners(item)
        if roundable:
            sharpen = all(item.is_rounded(v) for v in roundable)
            every = menu.addAction("Sharpen All Corners" if sharpen else "Round All Corners",
                                   lambda: self._round_all_corners(item, not sharpen))
            every.setToolTip("Round off every corner of the shape" if not sharpen
                             else "Make every corner square again")

    @staticmethod
    def _roundable_corners(item) -> list:
        """The corners that can be rounded: every one of a closed shape, the
        inner ones of an open line."""
        count = len(item.corner_points())
        closed = isinstance(item, RectItem) or getattr(item, "closed", False)
        if closed:
            return list(range(count)) if count >= 3 else []
        return list(range(1, count - 1))

    def _round_all_corners(self, item, rounded: bool = True) -> None:
        """Revu's Round All Corners (or every corner square again), one undo step."""
        self.view.begin_snapshot(self.view.involved_frames(item))
        item = self.view.swap_for_a_polygon(item)
        for vertex in self._roundable_corners(item):
            if item.is_rounded(vertex) != rounded:
                item.round_corner(vertex)
        self.view.commit_snapshot("Round all corners" if rounded else "Sharpen all corners")
        self.refresh_selection()

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
        """A markup's right-click menu in Revu's order (QA round 4, audit
        C1/C2), or the page's when nothing is under the pointer.

        What belongs to the kind of thing clicked (an equation's settings, a
        table's Edit Table, a measurement's Variable) comes first; then
        Revu's: Cut, Copy, Paste (Paste in Place, Paste Here… and Duplicate
        with them, as on the Edit menu), Multiply…, Format Painter, Delete |
        Control Point ▸, Arc Segment, Round All Corners | Order ▸,
        Alignment ▸, Flatten, Unflatten, Lock, Hide, Show Hidden, Group |
        CalcForge's shape extras | Add to Tool Chest ▸, Set as Default, Apply
        to Pages…, Properties. The Edit menu groups the same families the
        same way (bug hunt E14, E16–E18).
        """
        from . import menutidy
        menu = bindable.set_context(menu or QMenu(self), "canvas")
        menu.setSeparatorsCollapsible(True)
        if item is None:
            self._fill_page_context_menu(menu, scene_pos)
            return menutidy.tidy(menu)
        kind = getattr(item, "TYPE", "")
        is_table = kind == "table"
        # -- what belongs to this kind of thing --------------------------------
        if getattr(item, "IS_CALC", False) and getattr(item, "region", None) is not None:
            from . import calcmenu
            calcmenu.fill(self, menu, item)
        if is_table:
            edit = menu.addAction("Edit Table", lambda: self.view.tables.open(item, (0, 0)))
            edit.setToolTip("Open the table's cells, at A1")
            rename = menu.addAction("Rename Table…", lambda: self._rename_table(item))
            rename.setEnabled(not item.locked)
            menu.addSeparator()
        if kind == "chart":
            edit = menu.addAction("Edit Chart…", lambda: self._edit_chart(item))
            edit.setEnabled(not item.locked)
            menu.addSeparator()
        if kind == "calc_block":
            contained = menu.addAction("Self-Contained")
            contained.setCheckable(True)
            contained.setChecked(item.self_contained)
            contained.setEnabled(not item.locked)
            contained.setToolTip("What the equations in the block define stays inside it")
            contained.triggered.connect(lambda on: self.set_block_self_contained([item], on))
            menu.addAction("Select Its Equations", lambda: self._select_block_members(item))
            remove = menu.addAction("Remove Block, Keep Equations",
                                    lambda: self.remove_block_keep_equations(item))
            remove.setEnabled(not item.locked)
            menu.addSeparator()
        if isinstance(item, ImageItem) and not item.locked:
            swap = menu.addMenu("Replace Image")
            swap.addAction("From File…", lambda: self.replace_image(item, "file"))
            pasted = swap.addAction("From Clipboard",
                                    lambda: self.replace_image(item, "clipboard"))
            pasted.setEnabled(self.clipboard_has_image())
            menu.addAction("Crop Image", lambda: (self.scene.clearSelection(),
                                                  item.setSelected(True),
                                                  self.select_tool("crop_image")))
            menu.addSeparator()
        if kind == "link":
            menu.addAction("Follow Link", lambda: self.follow_link(item))
            menu.addAction("Edit Link…", lambda: self.edit_link(item))
            menu.addSeparator()
        # A group is one thing, as in Revu: its menu offers what applies to
        # the group — the clipboard, order, lock, ungroup, the tool chest —
        # and nothing that would reach inside it to one member (exercise
        # round 1, F-11: Round All Corners, Exact Size and the rest changed
        # only the first member and moved the selection to it).
        grouped = bool(getattr(item, "group", ""))
        if isinstance(item, _TextBase) and not grouped:
            menu.addAction("Edit Text", lambda: self.view.begin_item_edit(item))
            menu.addSeparator()
        if isinstance(item, MeasureItem) and item.kind != "calibrate" and not grouped:
            # first: a measurement's name is what ties it to the calcs,
            # typed right here (the user, 2026-10-01: no separate popup)
            menu.addAction(self._variable_field(menu, item))
            if item.variable:
                menu.addAction("Show in Variables",
                               lambda i=item: self.show_variable_of(i))
            menu.addSeparator()
        # equations and blocks are not drawn with a markup's pen, never
        # hidden or flattened (decision 17): only what applies to them
        calc_like = bool(getattr(item, "IS_CALC", False))
        # -- Revu: the clipboard -------------------------------------------------
        for action in (self.act_cut, self.act_copy, self.act_paste,
                       self.act_paste_in_place, self.act_paste_here, self.act_duplicate,
                       self.act_array):
            menu.addAction(action)
        if not calc_like:
            menu.addAction(self.act_format_painter)
        menutidy.proxy(menu, self.act_delete, "Delete", QKeySequence(Qt.Key_Delete))
        menu.addSeparator()
        # -- Revu: the outline ----------------------------------------------------
        if self.view.has_an_outline(item) and not is_table and not grouped:
            # Rectangles and clouds included: four corners and four sides
            # is an outline like any other, and everything offered on a
            # polygon's is offered on theirs.
            self._fill_outline_menu(menu, item, scene_pos)
        menu.addSeparator()
        # -- Revu: order, alignment, flatten, lock, hide --------------------------
        order = menu.addMenu("Order")
        for action in (self.act_front, self.act_forward, self.act_backward, self.act_back):
            order.addAction(action)
        align = menu.addMenu("Alignment")
        align.setEnabled(len(self.selected_items()) > 1)
        for key in ("left", "hcenter", "right", "top", "vcenter", "bottom"):
            align.addAction(getattr(self, f"act_align_{key}"))
        if not calc_like:
            menu.addAction(self.act_flatten)
            menu.addAction(self.act_recover_flattened)
        menu.addAction(self.act_lock)
        if not calc_like:
            menu.addAction(self.act_hide)
            menu.addAction(self.act_show_hidden)
        if len([i for i in self.selected_items() if isinstance(i, MarkupItem)]) > 1:
            menu.addAction(self.act_group)
        if any(getattr(i, "group", "") for i in self.selected_items()):
            menu.addAction(self.act_ungroup)
        menu.addSeparator()
        # -- CalcForge's extras for this kind of markup ---------------------------
        if isinstance(item, _TextBase) and not grouped:
            self._text_box_menu(menu, item)
            self._fill_leader_menu(menu, item, scene_pos)
        if isinstance(item, MeasureItem) and not grouped:
            menu.addAction("Edit Text…", lambda: self.edit_measure_text(item))
            straight = menu.addAction("Inline Text")
            straight.setToolTip("Keep the measurement text in line with its line")
            straight.setCheckable(True)
            straight.setChecked(item.label_angle is None)
            straight.toggled.connect(
                lambda on, i=item: self.set_label_angle(i, None if on else 0.0))
            menu.addAction(self.act_scale)
        if hasattr(item, "size_to_text") and not grouped:
            menu.addAction(self.act_autosize)
        if isinstance(item, RectItem) and item.kind in SIZED_SHAPES and not is_table \
                and not grouped:
            convert = menu.addAction("Convert to Polygon",
                                     lambda: self.rectangle_to_polygon(item))
            convert.setToolTip("Turn this rectangle or ellipse into a polygon")
            menu.addAction("Exact Size…", lambda: self.set_rectangle_size(item))
            show = menu.addAction("Show Size")
            show.setCheckable(True)
            show.setChecked(item.show_size)
            show.toggled.connect(lambda on: self.set_size_visible(item, on))
        several = self.colour_changeable(item)
        if len(several) > 1:
            # Revu's Change Multiple Colors: one colour of the selection
            # becomes another
            menu.addAction("Change Colours…", lambda: self.change_multiple_colors(several))
        elif isinstance(item, SnapshotItem):
            menu.addAction("Change Colours…", lambda: self.change_colors(item))
        elif isinstance(item, ImageItem):
            menu.addAction("Colour Processing…", lambda: self.change_colors(item))
        menu.addSeparator()
        # -- Revu: the tool chest, defaults and properties ------------------------
        # Bluebeam's Add to Tool Chest: the tool sets, one click each
        add_tool = menu.addMenu("Add to Tool Chest")
        add_tool.setToolTip("Keep this markup in a tool set to use again")
        for group in toolsets.load_toolsets():
            bindable.data_entry(add_tool.addAction(
                group.name, lambda n=group.name: self.add_to_toolset(item, into=n, ask=False)))
        add_tool.addSeparator()
        add_tool.addAction("Choose a Tool Set…", lambda: self.add_to_toolset(item))
        styles = getattr(self, "markup_styles", None)
        if not calc_like and styles is not None and not grouped:
            from .markupstyles import styled
            if styled(styles.tool_for_item(item) or ""):
                # the look kept for its tool, picked again with a number key
                keep = menu.addAction("Save as Markup Style",
                                      lambda: styles.save_markup(item))
                keep.setToolTip("Keep this look as a style of its tool: "
                                "press its number with the tool to draw in it")
        if not calc_like and not grouped:
            default = menu.addAction("Set as Default", lambda: self.set_as_default(item))
            default.setToolTip("Use these properties for new markups of this kind")
        if not calc_like:
            apply_pages = menu.addAction("Apply to Pages…",
                                         lambda: self.apply_to_pages(item))
            apply_pages.setToolTip("Copy this markup to chosen pages")
        menu.addAction("Properties", self.show_properties_panel)
        return menutidy.tidy(menu)

    def _fill_page_context_menu(self, menu, scene_pos: QPointF) -> None:
        """Revu's page menu: Paste; Add Note, Add Bookmark, Add Flag; Next and
        Previous Page; Select All; Print… and Search. Our own entries stay, in
        among them (QA, 2026-10-15) — and in Calc mode SMath's: an equation,
        text, a block or a plot where the pointer is (QA round 4)."""
        from . import menutidy
        frame = self.view.frame_at(scene_pos)
        menu.addAction(self.act_paste)
        menu.addAction(self.act_paste_in_place)
        menu.addAction(self.act_paste_here)
        menu.addAction(icon(TOOL_MAP["note"].icon), "Add Note",
                       lambda _c=False, p=scene_pos: self._insert_at("note", p))
        menu.addAction(self.act_bookmark)
        menu.addAction(icon(TOOL_MAP["flag"].icon), "Add Flag",
                       lambda _c=False, p=scene_pos: self._insert_at("flag", p))
        menu.addSeparator()
        menu.addAction(self.act_next_page)
        menu.addAction(self.act_prev_page)
        menu.addSeparator()
        menu.addAction(self.act_select_all)
        # hidden markups cannot be right-clicked, so the page is where they
        # are brought back from (E17)
        menu.addAction(self.act_show_hidden)
        menu.addSeparator()
        # Everything that can be put in where the pointer is, in one place
        # (E5): in Calc mode SMath's inserts first, then the markups
        insert = menu.addMenu("Insert Here")
        if self.view.calc.calc_mode() and frame is not None:
            self._fill_calc_here(insert, frame, scene_pos)
            insert.addSeparator()
        for key in ("text", "callout", "note", "stamp", "image"):
            tool = TOOL_MAP[key]
            insert.addAction(icon(tool.icon), menutidy.title_case(tool.label),
                             lambda _c=False, k=key, p=scene_pos: self._insert_at(k, p))
        if self.view.calc.calc_mode() and frame is not None:
            index = self.document.index_of(frame.page)
            if index is not None and index >= 0:
                from . import calcsections
                calcsections.add_menu(self, menu, index)
        menu.addSeparator()
        menu.addAction(self.act_page_setup)
        menu.addAction(self.act_scale)
        if frame is not None:
            spot = frame.mapFromScene(scene_pos)
            viewport = frame.page.viewport_at(spot.x(), spot.y())
            if viewport is not None:
                page = frame.page
                menu.addAction(f"{viewport.name} Scale…",
                               lambda: self.edit_viewport(page, viewport))
                menu.addAction("Delete Viewport",
                               lambda: self.delete_viewport(page, viewport))
        menu.addSeparator()
        menu.addAction(self.act_print)
        menu.addAction(self.act_find_text)

    def _fill_calc_here(self, menu, frame, scene_pos: QPointF) -> None:
        """Calc mode's part of Insert Here ▸: SMath's inserts, at the click,
        named as on the Calculation menu and toolbar."""
        from .sheetpages import blocks_calc
        if blocks_calc(frame):
            return                      # no equations on a spreadsheet page
        spot = frame.mapFromScene(scene_pos)

        def here(then=None):
            def run(_checked=False):
                calc = self.view.calc
                calc.leave()
                self.scene.clearSelection()
                calc.place_cross(frame, spot)
                self.view.setFocus(Qt.OtherFocusReason)
                if then is not None:
                    then()
            return run
        # an empty equation here, its cursor waiting, as SMath's Insert ▸
        # Math region (F-35: only the red cross used to move)
        equation = menu.addAction("Equation", here(
            lambda: self._as_opened(self._into_an_equation())))
        equation.setToolTip("An equation here, ready to type into")
        menu.addAction(self.act_insert_calc_text.text(), here(self.insert_calc_text)).setToolTip(
            "Calculation text here (\" in Calc mode)")
        menu.addAction(self.act_insert_block.text(), here(self.insert_block)).setToolTip(
            "An empty calculation block here")
        menu.addAction(self.act_insert_plot.text(), here(self.insert_plot)).setToolTip(
            "A 2-D plot here (@ in Calc mode)")

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
        self._redacted_names = []
        by_page: dict[int, list] = {}
        for index, page, item in targets:
            by_page.setdefault(index, []).append((page, item))
        for index, entries in by_page.items():
            page = entries[0][0]
            boxes = [item.mapRectToScene(item.bounds_without_chrome()) if hasattr(
                item, "bounds_without_chrome") else item.sceneBoundingRect()
                for _page, item in entries]
            self._burn_into_background(page, boxes)
            removed += self._flatten_redactions(page, [item for _page, item in entries], boxes)
        self.document.modified = True
        self.undo_stack.clear()          # the pixels are gone; undo would lie
        self.status_hint.setText(
            f"Applied {len(targets)} redaction(s); removed {removed} covered markup(s)")
        if self._redacted_names:
            names = sorted(set(self._redacted_names))
            self.warn_undefined(names, f"Applied {len(targets)} redaction(s); "
                                       f"removed {removed} covered markup(s). Redacted")

    def _burn_into_background(self, page, boxes: list) -> None:
        """Paint the boxes into the page's background image, destroying it."""
        from PySide6.QtCore import QBuffer, QIODevice
        from PySide6.QtGui import QPainter as _Painter

        image = pdfio.page_raster(self.document, page)
        if image is None or image.isNull():
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
        from .calcedit import undefined_without
        covered = []
        for other in list(frame.markups()):
            if other in items:
                continue
            rect = other.sceneBoundingRect()
            if getattr(other, "IS_CALC", False):
                rect = other.mapRectToScene(other.local_rect())
                if any(box.contains(rect) for box in boxes):
                    covered.append(other)
                elif any(box.intersects(rect) for box in boxes):
                    other.warning = "Partly under a redaction"
                    other.update()
                continue
            if any(box.contains(rect) for box in boxes):
                frame.remove_markup(other)
                removed += 1
        if covered:
            self._redacted_names += undefined_without(self.document, covered)
            for other in covered:
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
            self.act_snap_pdf_alignment.setChecked(
                self.document.settings.snap_to_pdf_alignment)
            self.act_margins.setChecked(self.document.settings.show_margins)
            self.act_name_tags.setChecked(self.document.settings.show_name_tags)
            self._refresh_all_scenes()
            self.update_title()

    def show_shortcuts(self) -> None:
        """F1 opens the one shortcut window there is."""
        self.edit_shortcuts()

    def show_about(self) -> None:
        dialogs.AboutDialog(self).exec()
