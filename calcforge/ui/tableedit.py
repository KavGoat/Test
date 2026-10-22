"""Working in a table's cells, the way Excel works (items/table.py).

A table is open for its cells — Calc mode: a click on it; Markup mode: a
double-click (the user's choice, 2026-10-09) — until a click outside it or
Esc. While it is open:

* click, drag, Shift+click select cells; the headings select rows and
  columns; the corner selects everything; arrows, Tab, Enter, Home,
  Ctrl+arrows and Ctrl+Home/End move as in Excel, with Shift to extend;
* typing replaces the cell; F2 or a double-click edits it; Enter keeps it,
  Esc throws it away; a formula's references are coloured, a click on a
  cell while typing one puts its address in (Excel's point mode, also with
  the arrows), and F4 cycles $ on the reference at the caret;
* the fill handle (the selection's corner) fills series; the selection's
  border drags the cells elsewhere (Ctrl copies them); the heading borders
  resize rows and columns, and a double-click fits them to what they hold;
* Ctrl+C/X/V copy, cut and paste — also with Excel, formulas and formats
  kept; Delete clears; Ctrl+B/I/U, Ctrl+1 (Format Cells), Ctrl+D/R fill,
  Ctrl+; today, Alt+= AutoSum, Ctrl+Enter fills the selection.

Every change is one undo step on the window's undo stack.
"""
from __future__ import annotations

import datetime
import re
from typing import Callable, Optional

from PySide6.QtCore import QEvent, QMimeData, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QFont, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QLineEdit, QMenu,
                               QWidget)

from ..items.base import MarkupItem
from .cellunits import UnitText
from ..items.table import (HEADING_H, ROWNUM_W, TableItem, THIN, cell_font, shown_width)
from ..sheet import clip
from ..sheet import formula as F
from ..sheet.refs import CellRef, area_text, col_letters, parse_range
from ..sheet.style import Border

REF_COLOURS = ["#1f6fd1", "#d1281f", "#7b2fb0", "#1d8a3a", "#c76a00", "#008b8b", "#b0306e"]


def _spreadsheet_name_cells(sheet, written: str):
    """(sheet, (top, left, bottom, right)) of the cells a spreadsheet's own
    name in a formula on *sheet* names (Name, or Sheet!Name, Excel's way),
    or None: not a name, a CalcForge variable, or a name of no cells."""
    from ..sheet.evaluate import Ctx, RefValue, ev
    from ..sheet.refs import unquote_sheet
    wb = sheet.workbook
    reader, name = sheet, written
    if "!" in written:
        where, _, name = written.rpartition("!")
        reader = wb.sheet(unquote_sheet(where) or "")
        if reader is None:
            return None
    dn = wb.find_name(name, reader)
    if dn is None or dn.variable:
        return None
    home = wb.sheet_by_id(dn.sheet) if dn.sheet else \
        (wb.sheet_by_id(dn.home) if dn.home else None) or reader
    try:
        got = ev(F.parse(dn.refers_to).tree, Ctx(wb, home, 0, 0))
    except Exception:  # noqa: BLE001 - a name that is no cells is not outlined
        return None
    if not isinstance(got, RefValue) or got.sheet is None:
        return None
    return got.sheet, (got.top, got.left, got.bottom, got.right)


import weakref

# every open-for-its-cells session, told when a table or sheet leaves its canvas
_SESSIONS: "weakref.WeakSet" = weakref.WeakSet()


def table_left(uid: str) -> None:
    """A table or sheet with *uid* left its canvas (its pages deleted, an
    undo, a document closed): each session working in it checks, once the
    event loop is back, whether it came back (a page rebuilt puts the same
    table back under the same uid) and, if not, ends (the user, 2026-10-17:
    the formula tip stayed showing after the workbook's pages went)."""
    from PySide6.QtCore import QTimer
    for session in list(_SESSIONS):
        if session._uid == uid:
            QTimer.singleShot(0, session.check_gone)


def _alive(item) -> bool:
    try:
        return item is not None and item.scene() is not None
    except RuntimeError:
        return False


def _frames(item) -> list:
    """The pages a change to a table's cells can touch: its own, or every
    page of a spreadsheet (its markups move with the cells), and those of
    the charts that read it (their ranges follow moved rows)."""
    if getattr(item, "SHEET_RUN", False):
        frames = list(item.run_frames() or [item.parentItem()])
    else:
        frames = [item.parentItem()]
    sheet = item.sheet
    scene = item.scene()
    if sheet is not None and scene is not None:
        from ..sheet.chartdata import sheets_read
        for frame in getattr(scene, "frames", []) or []:
            if frame in frames:
                continue
            for other in frame.markups():
                if getattr(other, "TYPE", "") == "chart" and sheet.name.lower() in sheets_read(other.spec):
                    frames.append(frame)
                    break
    return frames


def _is_run(item) -> bool:
    return bool(getattr(item, "SHEET_RUN", False))


class CellEditor(UnitText):
    """The text box over the cell being typed into (units drawn as SMath
    draws them: ui/cellunits.py)."""

    def __init__(self, tables: "TableEditing", parent):
        super().__init__(parent)
        self.tables = tables
        self.setFrame(False)
        self.on_white = True
        self.setStyleSheet("QLineEdit { background: white; color: black; "
                           "border: 2px solid #217346; border-radius: 0px; padding: 0px 1px; }")
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.textEdited.connect(tables._typed)
        self.cursorPositionChanged.connect(lambda *_: tables._caret_moved())
        self.reference_colours = lambda text: [(a, b, c) for a, b, c, _block
                                               in tables.formula_marks(text)]

    def event(self, event) -> bool:
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Tab, Qt.Key_Backtab):
            self.keyPressEvent(event)
            return True
        if event.type() == QEvent.ShortcutOverride:
            # every key belongs to the text being typed, not to the window's shortcuts
            event.accept()
            return True
        done = super().event(event)
        if event.type() in (QEvent.Polish, QEvent.StyleChange):
            # Its white fills all of it, so what is under it is not drawn
            # again for each key typed (the sheet's page under the box was,
            # its headings and the window too). Said again after each style
            # sheet, which takes it away.
            self.setAttribute(Qt.WA_OpaquePaintEvent)
        return done

    def keyPressEvent(self, event) -> None:
        if self.tables._editor_key(event):
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        bar = self.tables.bar
        if bar is not None and QApplication.focusWidget() is bar.edit:
            return
        if event.reason() in (Qt.ActiveWindowFocusReason, Qt.PopupFocusReason, Qt.MenuBarFocusReason):
            return
        QTimer.singleShot(0, self.tables._focus_left)


class _NameGrip(QWidget):
    """The dots between the Name Box and the formula: dragged, the Name Box
    is wider or narrower (Excel's)."""

    def __init__(self, bar: "FormulaBar"):
        super().__init__()
        self.bar = bar
        self.setObjectName("nameBoxGrip")
        self.setFixedWidth(7)
        self.setCursor(QCursor(Qt.SplitHCursor))
        self.setToolTip("Drag to widen or narrow the Name Box")
        self._from = None

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.palette().mid())
        x, y = self.width() / 2.0, self.height() / 2.0
        for k in (-4, 0, 4):
            painter.drawEllipse(QPointF(x, y + k), 1.1, 1.1)
        painter.end()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._from = (event.globalPosition().x(), self.bar.name.width())

    def mouseMoveEvent(self, event) -> None:
        if self._from is not None:
            start, width = self._from
            self.bar.name.setFixedWidth(int(max(60, min(420, width + event.globalPosition().x()
                                                         - start))))

    def mouseReleaseEvent(self, event) -> None:
        self._from = None


class FormulaBar(QWidget):
    """Excel's name box and formula bar, over the canvas while a table is open."""

    def __init__(self, tables: "TableEditing"):
        super().__init__()
        self.tables = tables
        self.setObjectName("formulaBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        self.name = QLineEdit()
        self.name.setFixedWidth(110)
        self.name.setToolTip("The cell or block selected — type an address (B4, A1:C3) to go there")
        self.name.returnPressed.connect(self._go)
        layout.addWidget(self.name)
        from PySide6.QtWidgets import QToolButton
        self.names = QToolButton()
        self.names.setText("▾")
        self.names.setProperty("menuButton", "plain")       # ▾ is its arrow
        self.names.setToolTip("Go to a named cell or block")
        self.names.setPopupMode(QToolButton.InstantPopup)
        names_list = QMenu(self.names)
        names_list.aboutToShow.connect(lambda: self._fill_names(names_list))
        self.names.setMenu(names_list)
        layout.addWidget(self.names)
        # the dots after the Name Box: dragged, it is wider or narrower (Excel's)
        self.name_grip = _NameGrip(self)
        layout.insertWidget(layout.indexOf(self.names) + 1, self.name_grip)
        # Excel's ✗ Cancel and ✓ Enter while a cell is typed in, and fx
        self.cancel_button = QToolButton()
        self.cancel_button.setObjectName("formulaCancel")
        self.cancel_button.setText("✗")
        self.cancel_button.setAutoRaise(True)
        self.cancel_button.setToolTip("Cancel (Esc): the cell as it was")
        self.cancel_button.clicked.connect(lambda: self.tables.cancel())
        layout.addWidget(self.cancel_button)
        self.enter_button = QToolButton()
        self.enter_button.setObjectName("formulaEnter")
        self.enter_button.setText("✓")
        self.enter_button.setAutoRaise(True)
        self.enter_button.setToolTip("Enter: what is typed goes into the cell")
        self.enter_button.clicked.connect(lambda: self.tables.commit(move=None))
        layout.addWidget(self.enter_button)
        fx = QToolButton()
        fx.setObjectName("formulaInsertFunction")
        fx.setText("fx")
        fx.setAutoRaise(True)
        f = fx.font()
        f.setItalic(True)
        f.setBold(True)
        fx.setFont(f)
        fx.setToolTip("Insert Function: start a formula, and pick a function from the list")
        fx.clicked.connect(lambda: self.tables.insert_function())
        layout.addWidget(fx)
        self.fx = fx
        self.edit = UnitText()
        self.edit.setToolTip("What is typed in the cell: its formula, or its value")
        # through self.tables: in Split View the bar serves whichever view is
        # in hand, and is handed that view's tables
        self.edit.textEdited.connect(lambda text: self.tables._typed_in_bar(text))
        self.edit.reference_colours = lambda text: [
            (a, b, c) for a, b, c, _block in (self.tables.formula_marks(text)
                                              if getattr(self, "tables", None) else ())]
        self.edit.cursorPositionChanged.connect(lambda *_: self.tables._caret_moved())
        self.edit.returnPressed.connect(lambda: self.tables.commit(move=(1, 0), enter=True))
        self.edit.installEventFilter(self)
        layout.addWidget(self.edit, 1)
        # SMath's unit box after the value, as in an equation (ui/unitbox.py);
        # the table controls (ui/tablebar.py) set the cells' display unit from it
        from .unitbox import UnitBox
        self.unit = UnitBox(getattr(tables.view, "window", None))
        layout.addWidget(self.unit)
        self.hide()

    def eventFilter(self, obj, event) -> bool:
        if obj is self.edit and event.type() == QEvent.KeyPress and \
                self.tables._formula_help is not None and self.tables._formula_help.key(event):
            return True
        if obj is self.edit and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            self.tables.cancel()
            return True
        if obj is self.edit and event.type() == QEvent.FocusIn:
            self.tables._bar_focused()
        return False

    def _go(self) -> None:
        self.tables.go_to(self.name.text().strip())

    def _fill_names(self, menu) -> None:
        from . import names
        menu.clear()
        names.names_menu(self.tables, menu)


def _excel(kind):
    from .view import excel_cursor
    return lambda: excel_cursor(kind)


# Excel's pointers: the fat white plus over cells, the thin cross on the fill
# handle, the move arrows on the selection's border, black arrows down and
# across the headings, the split arrows on their edges
_CURSORS = {"cell": _excel("cell"), "fill": lambda: QCursor(Qt.CrossCursor),
            "border": lambda: _border_cursor(), "col": _excel("col"), "row": _excel("row"),
            "corner": _excel("cell"), "col_edge": lambda: QCursor(Qt.SplitHCursor),
            # a page break or the print area's edge (Page Break Preview): the
            # plain double arrow, not a heading edge's split arrow
            "row_edge": lambda: QCursor(Qt.SplitVCursor), "break": lambda: QCursor(Qt.SizeVerCursor),
            "vbreak": lambda: QCursor(Qt.SizeHorCursor),
            "grow": lambda: QCursor(Qt.SizeFDiagCursor),
            # the tab picks the whole table up and moves it: Revu's move pointer
            "tab": lambda: _revu_move()}


def _revu_move():
    from .cursors import move_cursor
    return move_cursor()


#: Seconds a press on a sheet's HYPERLINK cell is held to pick the cell (B7)
LINK_HOLD = 0.5


def _border_cursor():
    """Excel's on the selection's border: the white arrow with the four-
    headed move sign; with Ctrl held, the arrow with the small + (a copy)."""
    from .cursors import copy_cursor, move_cursor
    return copy_cursor() if QApplication.keyboardModifiers() & Qt.ControlModifier \
        else move_cursor()


def _now(fmt: str) -> str:
    return datetime.datetime.now().strftime(fmt)


def clipboard_formats() -> dict:
    """What the clipboard holds, as {MIME type: bytes}; {} when it holds
    nothing. QClipboard.mimeData() is None on an empty clipboard on some
    platforms, so every reader goes through here (QA F-03)."""
    mime = QApplication.clipboard().mimeData()
    if mime is None:
        return {}
    formats = {}
    for kind in mime.formats():
        formats[kind] = bytes(mime.data(kind))
    if mime.hasText() and "text/plain" not in formats:
        formats["text/plain"] = (mime.text() or "").encode("utf-8")
    return {kind: data for kind, data in formats.items() if data}


def clipboard_has_something() -> bool:
    """Whether there is anything on the clipboard to paste, without reading
    it all (a menu being opened asks; a big picture there is not copied out)."""
    mime = QApplication.clipboard().mimeData()
    return mime is not None and bool(mime.formats())


def _cols(te) -> list:
    _top, first, _bottom, last = te.selection()
    return list(range(first, last + 1))


def _rows(te) -> list:
    top, _first, bottom, _last = te.selection()
    return list(range(top, bottom + 1))


def _data(name, *args, **kwargs):
    def run(te):
        from . import datatools
        return getattr(datatools, name)(te, *args, **kwargs)
    return run


def _layout(te, what: str) -> None:
    from . import sheetlayout
    window, item = te.view.window, te.item
    if not _is_run(item):
        window.status_hint.setText("Page layout is for a spreadsheet page")
        return
    if what == "print_area":
        sheetlayout.set_print_area(window, item, list(te.selection()))
    elif what == "page_break" and (te.active[0] > 0 or te.active[1] > 0):
        sheetlayout.insert_break(window, item, te.active[0], te.active[1])
    elif what == "page_layout":
        window.sheet_page_setup(window.document.index_of(item.parentItem().page))


def _select_all(te) -> None:
    """Ctrl+A, Excel's: inside a block of cells the block first (its
    current region), pressed again (or from an empty cell) the whole sheet."""
    from .sheetview import current_region
    item = te.item
    whole = ((0, 0), (item.size[0] - 1, item.size[1] - 1))
    region = current_region(item.sheet, te.active) if item.sheet is not None else None
    if region is not None and tuple(te.selection()) != region:
        te.select(region[:2], region[2:], te.active)
        return
    te.select(*whole, te.active)


def _names(name):
    def run(te):
        from . import names
        return getattr(names, name)(te)
    return run


# What each of the Spreadsheet group's bindings does (shortcuts.SHEET_KEYS).
SHEET_COMMANDS = {
    "edit_cell": lambda te: te.begin_edit(None, enter_mode=False),
    "select_all": lambda te: _select_all(te),
    "new_sheet": lambda te: te.view.window.sheet_tabs.new_sheet(before=True),
    "select_column": lambda te: te.select((0, te.selection()[1]),
                                          (te.item.size[0] - 1, te.selection()[3]), te.active),
    "select_row": lambda te: te.select((te.selection()[0], 0),
                                       (te.selection()[2], te.item.size[1] - 1), te.active),
    "copy": lambda te: te.copy(),
    "cut": lambda te: te.copy(cut=True),
    "paste": lambda te: te.paste(),
    "paste_values": lambda te: te.paste("values"),
    "paste_formulas": lambda te: te.paste("formulas"),
    "paste_formats": lambda te: te.paste("formats"),
    "paste_transpose": lambda te: te.paste("transpose"),
    "fill_down": lambda te: te.fill_direction("down"),
    "fill_right": lambda te: te.fill_direction("right"),
    "autosum": lambda te: te.autosum(),
    "insert_date": lambda te: te.begin_edit(datetime.date.today().isoformat()),
    "insert_time": lambda te: te.begin_edit(_now("%H:%M")),
    "list": lambda te: te.list_menu(),
    "format_cells": lambda te: te.view.window.format_cells_dialog(),
    "bold": lambda te: te.toggle("bold"),
    "italic": lambda te: te.toggle("italic"),
    "underline": lambda te: te.toggle("underline"),
    "strike": lambda te: te.toggle("strike"),
    "format_general": lambda te: te.format(number_format="General"),
    "format_number": lambda te: te.format(number_format="#,##0.00"),
    "format_currency": lambda te: te.format(number_format="$#,##0.00"),
    "format_percent": lambda te: te.format(number_format="0%"),
    "format_scientific": lambda te: te.format(number_format="0.00E+00"),
    "format_date": lambda te: te.format(number_format="d-mmm-yy"),
    "format_time": lambda te: te.format(number_format="h:mm AM/PM"),
    "border_outline": lambda te: te.borders("outside"),
    "border_none": lambda te: te.borders("none"),
    "border_all": lambda te: te.borders("all"),
    "merge_center": lambda te: te.merge("center"),
    "unmerge": lambda te: te.merge("unmerge"),
    "insert_cells": lambda te: te.insert_cells(),
    "delete_cells": lambda te: te.delete_cells(),
    "insert_rows": lambda te: te.insert_rows(),
    "insert_cols": lambda te: te.insert_cols(),
    "delete_rows": lambda te: te.delete_rows(),
    "delete_cols": lambda te: te.delete_cols(),
    "hide_rows": lambda te: te.hide("row", True),
    "unhide_rows": lambda te: te.hide("row", False),
    "hide_cols": lambda te: te.hide("col", True),
    "unhide_cols": lambda te: te.hide("col", False),
    "autofit_cols": lambda te: te.autofit("col", _cols(te)),
    "autofit_rows": lambda te: te.autofit("row", _rows(te)),
    "clear_contents": lambda te: te.clear("contents"),
    "clear_formats": lambda te: te.clear("formats"),
    "clear_all": lambda te: te.clear("all"),
    "find": _data("find_dialog"),
    "replace": _data("find_dialog", replace=True),
    "note": _data("comment_dialog"),
    "define_name": lambda te: te._ask_name(),
    "name_manager": _names("name_manager"),
    "create_names": _names("ask_create_from_selection"),
    "filter": _data("toggle_filter"),
    "sort_ascending": _data("quick_sort", True),
    "sort_descending": _data("quick_sort", False),
    "sort": _data("sort_dialog"),
    "conditional": _data("manage_rules_dialog"),
    "validation": _data("validation_dialog"),
    "remove_duplicates": _data("duplicates_dialog"),
    "text_to_columns": _data("text_columns_dialog"),
    "goal_seek": _data("goal_seek_dialog"),
    "insert_chart": lambda te: te.view.window.insert_chart(),
    "rename": lambda te: te.rename(),
    "page_layout": lambda te: _layout(te, "page_layout"),
    "print_area": lambda te: _layout(te, "print_area"),
    "page_break": lambda te: _layout(te, "page_break"),
}


def _cursor_for(zone) -> Optional[QCursor]:
    if zone and zone[0] == "area":       # the print area's edge: the plain double arrow
        return QCursor(Qt.SizeHorCursor if zone[1] in ("left", "right") else Qt.SizeVerCursor)
    make = _CURSORS.get(zone[0] if zone else None)
    return make() if make is not None else None


def _edge_near(edges: list, at: float, tol: float) -> Optional[int]:
    """The column (row) whose right (bottom) edge is near *at* in a
    heading, or None. Where hidden columns make edges meet, Excel's rule:
    just left of the double line is the column shown before it, just right
    of it the hidden one, which dragging opens again (QA, 2026-10-15)."""
    near = [k for k in range(1, len(edges)) if abs(at - edges[k]) <= tol]
    if not near:
        return None
    first = near[0]
    same = [k for k in near if edges[k] == edges[first]]
    if len(same) > 1 and at > edges[first]:
        return same[-1] - 1
    return first - 1


class TableEditing:
    """The open table, its selection, and what the pointer and keys do to it."""

    hover_tip: Optional[str] = None     # the error tip of the cell under the pointer

    def __init__(self, view):
        self.view = view
        _SESSIONS.add(self)
        self._item: Optional[TableItem] = None
        self._uid: Optional[str] = None
        self.anchor = (0, 0)
        self.active = (0, 0)
        self.edge = (0, 0)              # the selection's moving corner
        self.editor: Optional[CellEditor] = None
        self._formula_help = None          # Excel's Formula AutoComplete (ui/formulahelp.py)
        self.editing_cell: Optional[tuple] = None
        self.enter_mode = True          # typed straight in: arrows leave the cell
        self.drag: Optional[tuple] = None
        self.point: Optional[tuple] = None   # (start, end) of the reference being pointed
        self.copied: Optional[tuple] = None  # (uid, block, cut)
        self.bar: Optional[FormulaBar] = None
        self.highlight_ranges: Optional[list] = None    # outlined blocks (the Rules Manager)
        # the blocks picked before this one with Ctrl (Excel's multiple
        # selection): shaded, summed in the footer, cleared and formatted
        # with it (F2)
        self.extra_ranges: list = []
        self._keep_ranges = False
        self.insert_drag: Optional[tuple] = None

    # -- which table ------------------------------------------------------------------
    @property
    def item(self) -> Optional[TableItem]:
        item = self._item
        try:
            if item is not None and _alive(item) and item.scene() is self.view.scene():
                return item
        except RuntimeError:
            pass
        if self._uid is None:
            return None
        # rebuilt by undo or redo: the same table under the same uid
        scene = self.view.scene()
        for frame in getattr(scene, "frames", []) or []:
            for other in frame.markups():
                if isinstance(other, TableItem) and other.uid == self._uid:
                    self._item = other
                    other.opened = True
                    self._show_selection()
                    return other
        # gone for good: nothing of it may stay showing
        self.end_session()
        return None

    def check_gone(self) -> None:
        """After a table left the canvas: end the session if it didn't come back."""
        try:
            _ = self.item
        except RuntimeError:
            pass                           # the view itself is gone

    def end_session(self) -> None:
        """The sheet or table being worked in has gone, or its canvas has:
        put down everything it showed outside itself, without writing to it
        — the cell's text box, the formula tip and list, the hover tip, the
        unit box, the copy's marching ants, a guide line, and the formula
        bar's Name Box, formula and unit (the user, 2026-10-17)."""
        from PySide6.QtWidgets import QToolTip
        self._item = None
        self._uid = None
        self._hide_help()
        if self._formula_help is not None:
            try:
                self._formula_help.list.hide()
            except RuntimeError:
                pass
        QToolTip.hideText()
        self.hover_tip = None
        editor, self.editor = self.editor, None
        self.editing_cell = None
        self.point = None
        if editor is not None:
            try:
                editor.hide()
                editor.deleteLater()
            except RuntimeError:
                pass
        box = self._result_unit
        if box is not None and not box._done:
            box._done = True
            try:
                box.list.hide()
                box.hide()
            except RuntimeError:
                pass
        self.drag = None
        self.size_guide = None
        self.insert_drag = None
        self.copied = None
        self.held_format = None
        self.highlight_ranges = None
        try:
            self.refresh_bar()
            self._refresh_controls()
        except RuntimeError:
            pass

    held_format = None          # Format Painter: the looks being carried

    def _refresh_controls(self) -> None:
        window = self.view.window
        refresh = getattr(window, "_refresh_style_controls", None)
        if refresh is not None:
            refresh()
        # the Properties panel shows the table open for its cells, or what it
        # showed before (mainwindow.panel_subjects)
        follow = getattr(window, "_scene_selection_changed", None)
        if follow is not None:
            follow()

    def is_open(self) -> bool:
        return self.item is not None

    def _tables_under(self, scene_pos: QPointF) -> list:
        """The tables that could be under *scene_pos*, the topmost first.

        Asked of the canvas, every markup on every page was asked for its
        bounds (the canvas keeps no index), on every move of the pointer and
        every key let go: a twentieth of a second on a set of a thousand
        markups (2026-10-21). The pages' tables are few, and found directly."""
        scene = self.view.scene()
        frames = getattr(scene, "frames", None)
        if frames is None:
            return list(scene.items(scene_pos))
        found = []
        for frame in frames:
            children = frame.childItems()
            for order, item in enumerate(children):
                if isinstance(item, TableItem) and item.isVisible() \
                        and item.sceneBoundingRect().contains(scene_pos):
                    found.append((frame.zValue(), item.zValue(), order, item))
        found.sort(key=lambda entry: entry[:3], reverse=True)
        return [entry[3] for entry in found]

    def table_at(self, scene_pos: QPointF, chrome: bool = False) -> Optional[TableItem]:
        for item in self._tables_under(scene_pos):
            if isinstance(item, TableItem):
                local = item.mapFromScene(scene_pos)
                box = item.chrome_rect() if (chrome and item.opened) else item.local_rect()
                if box.contains(local) or (item.isSelected() and item.tab_rect().contains(local)):
                    return item
        return None

    def open(self, item: TableItem, cell: Optional[tuple] = None) -> None:
        if self.item is not None and self.item is not item:
            self.close()
        view = self.view
        view.calc.leave()
        view.close_block()
        item.setSelected(False)
        self._item, self._uid = item, item.uid
        item.opened = True
        if not getattr(item, "SHEET_RUN", False):
            # on a turned page: upright while its cells are typed into
            item.show_upright(float(getattr(view.scene(), "reading_turn", 0) or 0))
        item.prepareGeometryChange()
        cell = cell or (0, 0)
        self.anchor = self.active = self.edge = cell
        self._show_selection()
        self.refresh_bar()
        self._refresh_controls()
        self._properties_follow(item)
        view.setFocus()
        view.statusMessage.emit(f"{item.name}: type into the cells" if getattr(item, "alone", False)
                                else f"{item.name}: type into the cells · click outside it or "
                                     "Esc to close it")
        from . import sheetview
        sheetview.opened(view, item)      # a sheet's cell clicked on its page: the workbook view

    def refresh_bar(self) -> None:
        """The formula bar shows whenever a sheet or table is in use: one open
        for its cells, a table picked out, or a spreadsheet page in view (the
        user's choice, 2026-10-11); empty and read-only until a cell is chosen."""
        bar = self.bar
        if bar is None:
            return
        from shiboken6 import isValid
        if not isValid(bar):
            return
        view = self.view
        window = getattr(view, "window", None)
        wanted = self.item is not None
        if not wanted:
            scene = view.scene()
            wanted = scene is not None and any(isinstance(i, TableItem) for i in scene.selectedItems())
        if not wanted:
            # the workbook view: a sheet shown alone (sheetview.py)
            from .sheetview import run_shown
            wanted = run_shown(view.scene()) is not None
        if not wanted and window is not None and getattr(window, "document", None) is not None \
                and getattr(window, "view", None) is view:
            pages = window.document.pages
            index = getattr(window, "current_index", 0)
            wanted = 0 <= index < len(pages) and pages[index].sheet is not None
        if self.item is None:
            bar.name.clear()
            bar.edit.clear()
            bar.edit.setPlaceholderText("click a cell")
        bar.edit.setReadOnly(self.item is None)
        bar.name.setReadOnly(self.item is None)
        for button in (getattr(bar, "cancel_button", None), getattr(bar, "enter_button", None)):
            if button is not None:
                button.setEnabled(self.editor is not None)
        bar.unit.setEnabled(self.item is not None)
        if self.item is None:
            bar.unit.clear()
        bar.setVisible(wanted)

    @property
    def help(self):
        if self._formula_help is None:
            from .formulahelp import FormulaHelp
            self._formula_help = FormulaHelp(self)
        return self._formula_help

    def _hide_help(self) -> None:
        if self._formula_help is not None:
            self._formula_help.hide()

    def _typing_widget(self):
        """Where the formula is being typed: the formula bar or the cell."""
        bar = self.bar
        if bar is not None and QApplication.focusWidget() is bar.edit:
            return bar.edit
        return self.editor

    def _formula_from_help(self, widget, text: str, caret: int) -> None:
        """A function or name chosen from the list, put into the formula."""
        if self.editor is None:
            return
        self.editor.setText(text)
        if self.bar is not None:
            self.bar.edit.setText(text)
        widget.setCursorPosition(caret)
        if widget is not self.editor:
            self.editor.setCursorPosition(caret)
        self._typed(text)

    def close(self) -> None:
        self.settle_result_unit()
        if self._uid is not None and self.item is None:
            return                         # it had gone: end_session put it all down
        item = self.item
        self._hide_help()
        if self.editor is not None:
            self.commit(move=None)
        if item is not None:
            item.opened = False
            item.selection = item.active = None
            item.overlay = None
            item.leave_upright()
            item.prepareGeometryChange()
            item.update()
        self._item = None
        self._uid = None
        self.copied = None
        self.held_format = None
        self.extra_ranges = []
        self.refresh_bar()
        self._refresh_controls()
        self._properties_follow(item)

    def _properties_follow(self, item) -> None:
        """A sheet of an imported workbook opened or closed: the Properties
        panel shows (or drops) its Workbook section."""
        window = getattr(self.view, "window", None)
        sheet = getattr(item, "sheet", None)
        panel = getattr(window, "properties_panel", None)
        if panel is None or sheet is None or getattr(sheet, "book", None) is None \
                or window.selected_items():
            return
        panel.show_items([])

    # -- the selection ---------------------------------------------------------------------
    def selection(self) -> tuple:
        (r1, c1), (r2, c2) = self.anchor, self.edge
        top, left, bottom, right = min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2)
        item = self.item
        if item is not None and item.sheet is not None:
            top, left, bottom, right = self._with_merges(item.sheet, top, left, bottom, right)
        return top, left, bottom, right

    @staticmethod
    def _with_merges(sheet, top, left, bottom, right):
        """A selection grows to take in the whole of any merged cell it touches."""
        changed = True
        while changed:
            changed = False
            for m in sheet.merges:
                if m[0] <= bottom and m[2] >= top and m[1] <= right and m[3] >= left:
                    t, l, b, r = min(top, m[0]), min(left, m[1]), max(bottom, m[2]), max(right, m[3])
                    if (t, l, b, r) != (top, left, bottom, right):
                        top, left, bottom, right = t, l, b, r
                        changed = True
        return top, left, bottom, right

    #: Excel: typing along a row with Tab, then Enter, goes to the next row
    #: under the cell the Tabs started from
    tab_start: Optional[int] = None
    _keep_tab = False

    def select(self, anchor: tuple, edge: Optional[tuple] = None, active: Optional[tuple] = None) -> None:
        item = self.item
        if item is None:
            return
        self.settle_result_unit()
        if not self._keep_tab:
            self.tab_start = None
        if self.extra_ranges and self.drag is None and not self._keep_ranges:
            self.extra_ranges = []           # a block picked afresh: the others go
            item.update()
        rows, cols = item.size
        if _is_run(item):
            rows += 1                    # one row past the last page: typing there adds a page
        clamp = lambda rc: (max(0, min(rc[0], rows - 1)), max(0, min(rc[1], cols - 1)))
        self.anchor = clamp(anchor)
        self.edge = clamp(edge if edge is not None else anchor)
        self.active = clamp(active if active is not None else anchor)
        m = item.sheet.merge_at(*self.active) if item.sheet else None
        if m is not None:
            self.active = (m[0], m[1])
        if _is_run(item) and self.active[0] == item.sheet_rows and self.anchor == self.edge:
            # Enter or ↓ off the last row: the sheet gets one more row (the
            # user, 2026-10-17: a row, not a page); a page only when the
            # rows run past the page
            self._add_run_row()
        self._show_selection()

    def _add_run_row(self) -> None:
        """One more row at the end of the spreadsheet being typed in, as
        its own undo step; a new page with it only if the page is full."""
        from . import sheetlayout
        window = self.view.window
        item = self.item
        if item is None or item.sheet is None:
            return
        rows = max(int((item.sheet.page or {}).get("rows") or 0), item.sheet_rows) + 1
        sheetlayout.change_options(window, item, "Add row", rows=rows)
        item = self.item
        if item is not None:
            self._item = item

    def _show_selection(self) -> None:
        item = self._item
        if item is None:
            return
        headings = getattr(self.view, "sheet_headings", None)
        if headings is not None and getattr(item, "SHEET_RUN", False):
            headings.refresh_soon()
        before = (item.selection, item.active)
        item.selection = self.selection()
        item.active = self.active
        item.overlay = self._paint_overlay
        # Only where the selection was and is now is drawn again, when
        # nothing else drawn over the cells has changed since (a click or an
        # arrow key redrew the whole table, every cell of it, as markups
        # are not: they redraw what moved).
        look = self._look_now(item)
        if look == self._look_shown and None not in before:
            area = self._selection_area(item, *before).united(
                self._selection_area(item, item.selection, item.active))
            item.update(area)
        else:
            item.update()
        self._look_shown = look
        self._update_bar()
        controls = getattr(self.view.window, "table_controls", None)
        if controls is not None:
            controls.sync()
        panel = getattr(self.view.window, "properties_panel", None)
        if panel is not None:
            panel.sync_cells()             # its Cells section, as the bar
        from ..sheet import validation
        rule = validation.at(item.sheet, *self.active) if item.sheet is not None else None
        if rule is not None and rule.get("input"):
            self.view.statusMessage.emit(rule["input"])
        # Excel's error tip: what went wrong in the cell, and where (QA, 2026-10-15)
        why = self.error_text(item, *self.active)
        if why:
            self.view.statusMessage.emit(f"{col_letters(self.active[1])}{self.active[0] + 1}: {why}")
        self._scroll_to(self.active)

    #: what the open table showed over its cells besides the selection when
    #: it was last drawn (see _look_now)
    _look_shown = None

    def _look_now(self, item) -> tuple:
        """Everything the open table draws over its cells but the selection:
        while it is the same, a new selection repaints only the cells it
        covers."""
        editor = self.editor
        return (id(item), item.opened, editor is not None,
                self._drawn_refs if editor is not None else None,
                self.drag[0] if self.drag is not None and self.drag[0] in ("fill", "move") else None,
                self.point, self.copied,
                repr(self.highlight_ranges), self._result_unit_open(),
                repr(getattr(item, "circles", ())), item.size,
                self.view.transform().m11(), self.view.transform().m12())

    def _selection_area(self, item, selection, active) -> QRectF:
        """What a selection draws, in the table's coordinates: its box and
        fill handle, the active cell with its list button and unit box, a
        dynamic array's frame, and the row and column headings it lights."""
        scale = max(abs(self.view.transform().m11()) + abs(self.view.transform().m12()), 0.05)
        pad = 6.0 / scale                   # the cosmetic pens and the fill handle
        top, left, bottom, right = selection
        box = item.block_rect(top, left, bottom, right)
        area = box.adjusted(-pad, -pad, pad, pad)
        cell = item.cell_rect(*active)
        # (the list button and SMath's unit box sit just past the cell's right)
        area = area.united(cell.adjusted(-pad, -pad, pad + 40.0, pad))
        sheet = item.sheet
        if sheet is not None:
            block = sheet.workbook.spill_block(sheet, *active)
            if block is not None:
                area = area.united(item.block_rect(*block).adjusted(-pad, -pad, pad, pad))
        heads = HEADING_H + pad
        area = area.united(QRectF(box.left() - pad, -heads, box.width() + 2 * pad, heads))
        area = area.united(QRectF(-ROWNUM_W - pad, box.top() - pad, ROWNUM_W + pad,
                                  box.height() + 2 * pad))
        return area

    @staticmethod
    def error_text(item, row: int, col: int) -> Optional[str]:
        """One line saying why a cell shows an error (None if it doesn't)."""
        if item is None or item.sheet is None:
            return None
        from ..sheet.explain import why
        return why(item.sheet, row, col)

    _keep_view = False          # a heading clicked: the canvas stays where it is (Excel)

    def _scroll_to(self, cell) -> None:
        item = self._item
        if item is None or self.drag is not None or self._keep_view:
            return
        from .sheetfreeze import scroll_to_cell
        if scroll_to_cell(self.view, item, cell):
            return                         # panes frozen: kept below and right of them
        rect = item.mapRectToScene(item.cell_rect(*cell))
        self.view.ensureVisible(rect, 8, 8)

    def _status_soon(self) -> None:
        """Excel's status bar in the workbook view: its mode and the sums
        of the cells picked (sheetstatus.py)."""
        from . import sheetstatus
        sheetstatus.refresh_soon(getattr(self.view, "window", None))

    def _update_bar(self) -> None:
        self._status_soon()
        bar = self.bar
        item = self._item
        if bar is None or item is None or item.sheet is None:
            return
        top, left, bottom, right = self.selection()
        named = self._name_of(item, top, left, bottom, right)
        if named:
            bar.name.setText(named)
        elif (top, left) == (bottom, right) or item.sheet.merge_at(top, left) == (top, left, bottom, right):
            bar.name.setText(col_letters(self.active[1]) + str(self.active[0] + 1))
        elif self.drag is not None and self.drag[0] in ("select", "cols", "rows"):
            # Excel: the size of the block only while the mouse picks it
            bar.name.setText(f"{bottom - top + 1}R × {right - left + 1}C")
        else:
            bar.name.setText(col_letters(self.active[1]) + str(self.active[0] + 1))
        if self.editor is None and QApplication.focusWidget() is not bar.edit:
            bar.edit.setText(item.sheet.input(*self.active))
            # a spilled cell: its formula, greyed (Excel), from the cell it spills from
            cell = item.sheet.cells.get(self.active)
            anchor = cell.spill_from if cell is not None else None
            bar.edit.setPlaceholderText(item.sheet.input(*anchor) if anchor else "")

    # -- the pointer ----------------------------------------------------------------------------
    def _zone(self, item: TableItem, local: QPointF):
        """What part of an open table is under a point: ("cell", r, c),
        ("col", c), ("row", r), ("col_edge", c), ("row_edge", r), ("corner",),
        ("fill",), ("border",), ("grow",), ("tab",) or None."""
        xs, ys = item.edges()
        tol = 2.0 / max(self.view.transform().m11(), 0.05) * 1.5
        if item.tab_rect().contains(local):
            return ("tab",)
        sheet = item.sheet
        if sheet is not None and sheet.filter is not None:
            t, l, b, r = sheet.filter["range"]
            for c in range(l, min(r, item.size[1] - 1) + 1):
                if item.filter_button(c).contains(local):
                    return ("filter", c)
        if item.active is not None and item.list_button() is not None and \
                item.list_button().contains(local):
            return ("list",)
        handle = item.fill_handle_rect()
        if handle is not None and handle.adjusted(-tol, -tol, tol, tol).contains(local):
            return ("fill",)
        w, h = xs[-1], ys[-1]
        from .sheetview import breaks_editable
        breaks = _is_run(item) and item.paging is not None and breaks_editable(item)
        if breaks:
            side = self._area_edge(item, local, tol)
            if side is not None:
                return ("area", side)
        if breaks and 0 <= local.x() < w:
            # a page break line: dragged, it becomes a manual break (Excel)
            paging = item.paging
            if xs[paging.first_col] <= local.x() <= xs[paging.last_col + 1]:
                for k, (a, _b) in enumerate(paging.slices[1:], 1):
                    if abs(local.y() - ys[a]) <= tol and 0 <= local.y():
                        return ("break", a)
                # and one between pages across
                for c0, _c1 in paging.groups[1:]:
                    if abs(local.x() - xs[c0]) <= tol and 0 <= local.y() <= ys[-1]:
                        return ("vbreak", c0)
        if not _is_run(item) and w - 1 <= local.x() <= w + 5 and h - 1 <= local.y() <= h + 5 and \
                not (0 <= local.x() < w and 0 <= local.y() < h):
            return ("grow",)
        if -HEADING_H <= local.y() < 0 and 0 <= local.x() <= w + tol:
            c = _edge_near(xs, local.x(), tol)
            if c is not None:
                return ("col_edge", c)
            if local.x() < w:
                return ("col", item.cell_at(QPointF(local.x(), 0))[1])
        if -ROWNUM_W <= local.x() < 0 and 0 <= local.y() <= h + tol:
            r = _edge_near(ys, local.y(), tol)
            if r is not None:
                return ("row_edge", r)
            if local.y() < h:
                return ("row", item.cell_at(QPointF(0, local.y()))[0])
        if -ROWNUM_W <= local.x() < 0 and -HEADING_H <= local.y() < 0:
            return ("corner",)
        if item.selection is not None:
            box = item.block_rect(*item.selection)
            outer = box.adjusted(-tol, -tol, tol, tol)
            px = 2.0 / max(self.view.transform().m11(), 0.05)   # the border's own width
            inner = box.adjusted(px, px, -px, -px)
            if outer.contains(local) and not inner.contains(local):
                return ("border",)
        hit = item.cell_at(local)
        if hit is not None:
            return ("cell",) + hit
        return None

    # -- HYPERLINK cells: Ctrl+click follows the link -----------------------------------------
    def link_at(self, scene_pos: QPointF) -> Optional[tuple]:
        """(table, cell, link) of a HYPERLINK cell under the pointer, or None."""
        from ..sheet.morefunctions import hyperlink_target
        table = self.table_at(scene_pos)
        if table is None or table.sheet is None:
            return None
        cell = table.cell_at(table.mapFromScene(scene_pos))
        if cell is None:
            return None
        link = hyperlink_target(table.sheet, *cell)
        return (table, cell, link) if link else None

    def follow_link(self, table: TableItem, cell: tuple, link: str) -> None:
        """Where a HYPERLINK goes: "#Sheet2!A1" (or "#Name") is a place in the
        document, which opens there; a web or mail address opens in the
        browser or mail program; anything else (a file on the computer) is
        asked about first, as Excel warns, since a document from someone else
        can name any file."""
        view = self.view
        if link.startswith("#"):
            self._go_to_link(table, cell, link[1:])
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        url = QUrl.fromUserInput(link)
        if not url.isValid():
            view.statusMessage.emit(f"The link can't be opened: {link}")
            return
        if url.scheme().lower() not in ("http", "https", "mailto"):
            window = getattr(view, "window", None)
            if window is None or not getattr(window, "interactive_prompts", True):
                view.statusMessage.emit(f"Not opened (not a web address): {link}")
                return
            from PySide6.QtWidgets import QMessageBox
            answer = QMessageBox.question(
                window, "Open link", f"This link opens something on your computer:\n\n{link}"
                "\n\nOpen it only if you trust the document. Open it?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        QDesktopServices.openUrl(url)
        view.statusMessage.emit(f"Opened {link}")

    def _go_to_link(self, table: TableItem, cell: tuple, where: str) -> None:
        from ..sheet.evaluate import Ctx, RefValue, ev
        try:
            got = ev(F.parse(where, *cell).tree, Ctx(table.sheet.workbook, table.sheet, *cell))
        except Exception:  # noqa: BLE001
            got = None
        target = None if not isinstance(got, RefValue) else next(
            (t for t in self._all_tables() if t.sheet is got.sheet), None)
        if target is None:
            self.view.statusMessage.emit(f"The link's place is not in this document: #{where}")
            return
        self.open(target, (got.top, got.left))
        self.select((got.top, got.left), (got.bottom, got.right), (got.top, got.left))
        self.view.ensureVisible(target.mapRectToScene(target.cell_rect(got.top, got.left)), 40, 40)
        self.view.setFocus()

    def mouse_press(self, event, scene_pos: QPointF) -> bool:
        view = self.view
        if event.button() not in (Qt.LeftButton, Qt.RightButton):
            return False
        if event.button() == Qt.LeftButton and event.modifiers() & Qt.ControlModifier \
                and view.tool_key == "select":
            got = self.link_at(scene_pos)
            if got is not None:
                self.follow_link(*got)
                return True
        if event.button() == Qt.LeftButton and not event.modifiers() \
                and view.tool_key == "select":
            got = self.link_at(scene_pos)
            if got is not None and _is_run(got[0]):
                # Excel: on a sheet a click follows the link; a press held
                # (LINK_HOLD) picks the cell instead
                import time
                self._link_press = (got, time.monotonic())
                return True
        # a click anywhere else on the canvas leaves SMath's unit box (the
        # canvas never takes the focus from it, so it stayed, "=" and all,
        # over whatever came there next: the user, 2026-10-16)
        self.settle_result_unit()
        headings = getattr(view, "sheet_headings", None)
        hit = headings.hit(event.position()) if headings is not None else None
        if hit is not None and view.tool_key == "select":
            # a spreadsheet's headings kept in view: a whole column or row
            run, zone = hit
            if event.button() == Qt.RightButton:
                if self.item is not run:
                    self._open_in_place(run)
                return False
            return self._press_heading(run, zone, event, scene_pos)
        if view.tool_key == "table" and event.button() == Qt.LeftButton:
            frame = view.frame_at(scene_pos)
            if frame is not None:
                self.close()
                self.insert_drag = (frame, frame.mapFromScene(scene_pos), frame.mapFromScene(scene_pos))
                return True
            return False
        item = self.item
        if item is not None and event.button() == Qt.LeftButton and \
                self._press_result_unit(item, item.mapFromScene(scene_pos)):
            return True
        if item is not None:
            local = item.mapFromScene(scene_pos)
            inside = item.chrome_rect().contains(local) or item.tab_rect().contains(local)
            if not inside:
                # pointing at another table's cell while typing a formula
                other = self.table_at(scene_pos)
                if other is not None and self._pointing() and event.button() == Qt.LeftButton:
                    cell = other.cell_at(other.mapFromScene(scene_pos))
                    if cell:
                        self._point_at(cell, cell, other)
                        self.drag = ("point_other", cell, other)
                        return True
                self.close()
                # and the click goes on to whatever is there
            else:
                zone = self._zone(item, local)
                if event.button() == Qt.RightButton:
                    if zone and zone[0] == "cell" and not self._in_selection(zone[1], zone[2]):
                        self.select((zone[1], zone[2]))
                    return False            # the context menu comes with the release
                return self._press_heading(item, zone, event, scene_pos)
        if view.tool_key != "select":
            return False
        if self._press_run_heading(event, scene_pos):
            return True
        if event.button() != Qt.LeftButton:
            return False
        target = self.table_at(scene_pos)
        if target is None or not view.editable(target):
            return False
        if _is_run(target) and event.modifiers() & Qt.ControlModifier:
            return False                 # Ctrl+drag: Bluebeam's selection box over the sheet
        if _is_run(target) and not view.calc.calc_mode():
            # a spreadsheet page: a markup over the cells is picked first,
            # and anywhere else is a cell (the user's choice)
            for other in view.scene().items(scene_pos):
                if other is target:
                    break
                if isinstance(other, MarkupItem) and other.isVisible():
                    return False
            local = target.mapFromScene(scene_pos)
            if self._press_edge(target, local, event, scene_pos):
                return True
            cell = target.cell_at(local)
            if cell is not None:
                self.open(target, cell)
                self.drag = ("select", cell)
                return True
            return False
        if view.calc.calc_mode():
            local = target.mapFromScene(scene_pos)
            if target.tab_rect().contains(local) and target.isSelected():
                return False                 # the name tab picks it up to move it
            if _is_run(target) and self._press_edge(target, local, event, scene_pos):
                return True
            # Calc mode: clicks go to the cells (the user's choice)
            cell = target.cell_at(local)
            if cell is not None:
                self.open(target, cell)
                self.drag = ("select", cell)
                return True
        return False

    HEADING_ZONES = ("row", "col", "corner", "row_edge", "col_edge")

    def _press_run_heading(self, event, scene_pos: QPointF) -> bool:
        """A spreadsheet page not open yet, pressed on its row numbers or
        column letters: they are always drawn, so they select a whole row or
        column (or size one) at once, as Excel's do — in either mode. They
        used to do nothing until a cell had been clicked first (bug hunt,
        2026-10-16: "in calc mode can't select rows")."""
        if self.item is not None or event.modifiers() & Qt.ControlModifier:
            return False
        view = self.view
        for run in view.scene().items(scene_pos):
            if isinstance(run, MarkupItem) and run.isVisible() and not _is_run(run):
                return False             # a markup over the headings is picked first
            if not _is_run(run) or not view.editable(run):
                continue
            local = run.mapFromScene(scene_pos)
            if run.local_rect().contains(local) or not run.chrome_rect().contains(local):
                return False
            zone = self._zone(run, local)
            if not zone or zone[0] not in self.HEADING_ZONES:
                return False
            if event.button() == Qt.RightButton:
                if zone[0] in ("row", "col"):
                    self._press_heading(run, zone, event, scene_pos)
                    self.drag = None
                return False             # the heading menu comes with the release
            if event.button() != Qt.LeftButton:
                return False
            return self._press_heading(run, zone, event, scene_pos)
        return False

    def _open_in_place(self, run) -> None:
        """Open a spreadsheet without scrolling the canvas back to A1."""
        self._keep_view = True
        try:
            self.open(run, (0, 0))
        finally:
            self._keep_view = False

    def _press_heading(self, run, zone, event, scene_pos: QPointF) -> bool:
        """A row number or column letter pressed: the row or column chosen
        where it is — Excel never scrolls the sheet for a heading click (it
        used to jump back to A1, or across to column A)."""
        if self.item is not run:
            self._open_in_place(run)
        self._keep_view = zone is not None and zone[0] in ("row", "col", "corner")
        try:
            return self._press_zone(run, zone, event, scene_pos)
        finally:
            self._keep_view = False

    def _press_edge(self, target, local: QPointF, event, scene_pos: QPointF) -> bool:
        """A spreadsheet page not open yet, pressed on its print area's edge
        or a page break: opened, and the edge dragged from there."""
        edge = self._zone(target, local)
        if not edge or edge[0] not in ("area", "break", "vbreak"):
            return False
        self.open(target, target.cell_at(local) or (0, 0))
        return self._press_zone(target, edge, event, scene_pos)

    def _in_selection(self, r, c) -> bool:
        t, l, b, rr = self.selection()
        return t <= r <= b and l <= c <= rr

    def _press_zone(self, item, zone, event, scene_pos) -> bool:
        shift = bool(event.modifiers() & Qt.ShiftModifier)
        ctrl = bool(event.modifiers() & Qt.ControlModifier)
        rows, cols = item.size
        if zone is None:
            return True
        kind = zone[0]
        if kind == "tab":
            self.close()
            item.setSelected(True)
            return False                     # picked up and dragged like any markup
        if kind == "filter":
            if self.editor is not None and not self.commit(move=None):
                return True
            from . import datatools
            pos = self.view.viewport().mapToGlobal(self.view.mapFromScene(
                item.mapToScene(item.filter_button(zone[1]).bottomLeft())))
            datatools.filter_menu(self, zone[1], pos)
            return True
        if kind == "list":
            self.list_menu()
            return True
        if self.editor is not None:
            if kind == "cell" and self._pointing():
                self._point_at((zone[1], zone[2]), (zone[1], zone[2]))
                self.drag = ("point", (zone[1], zone[2]))
                return True
            if not self.commit(move=None):
                return True
        if kind in ("cell", "col", "row") and ctrl and not shift and _is_run(item):
            # Excel: Ctrl+click (or drag) adds another block to those picked
            self.extra_ranges = self.extra_ranges + [tuple(self.selection())]
            self._keep_ranges = True
            item.update()
        try:
            return self._press_picked(item, zone, kind, shift, rows, cols, scene_pos, event)
        finally:
            self._keep_ranges = False

    def _press_picked(self, item, zone, kind, shift, rows, cols, scene_pos, event) -> bool:
        """The rest of a press on an open table (_press_zone)."""
        ctrl = bool(event.modifiers() & Qt.ControlModifier)
        if kind == "cell":
            cell = (zone[1], zone[2])
            if shift:
                self.select(self.anchor, cell, self.active)
            else:
                self.select(cell)
            self.drag = ("select", self.anchor)
        elif kind == "col":
            c = zone[1]
            if shift:
                self.select((0, self.anchor[1]), (rows - 1, c), self.active)
            else:
                self.select((0, c), (rows - 1, c), (0, c))
            self.drag = ("cols", self.anchor)
        elif kind == "row":
            r = zone[1]
            if shift:
                self.select((self.anchor[0], 0), (r, cols - 1), self.active)
            else:
                self.select((r, 0), (r, cols - 1), (r, 0))
            self.drag = ("rows", self.anchor)
        elif kind == "corner":
            self.select((0, 0), (rows - 1, cols - 1), (0, 0))
        elif kind == "col_edge":
            c = zone[1]
            chosen = self._chosen_cols(c)
            # the widths they have now, kept for Unhide if dragged to nothing
            before = {i: item.sheet.widths.get(i) for i in chosen}
            self.drag = ("col_size", c, scene_pos, item.sheet.width(c), chosen, before)
            self.view.begin_snapshot(_frames(item))
        elif kind == "row_edge":
            r = zone[1]
            chosen = self._chosen_rows(r)
            before = {i: item.sheet.heights.get(i) for i in chosen}
            self.drag = ("row_size", r, scene_pos, item.sheet.height(r), chosen, before)
            self.view.begin_snapshot(_frames(item))
        elif kind == "fill":
            self.drag = ("fill", self.selection(), None, ctrl)
        elif kind == "border":
            self.drag = ("move", self.selection(), item.cell_at(item.mapFromScene(scene_pos)) or self.active,
                         None)
        elif kind == "grow":
            self.drag = ("grow", item.size)
            self.view.begin_snapshot(_frames(item))
        elif kind in ("break", "vbreak"):
            self.drag = (kind, zone[1], zone[1])
        elif kind == "area":
            area = self._print_area(item)
            self.drag = ("area", zone[1], area, list(area))
        return True

    @staticmethod
    def _print_area(item) -> list:
        """The print area of a run of pages as [t, l, b, r]: the one set, or
        the columns that fit on the paper down to the last row used."""
        from ..sheet.pagination import options
        area = options(item.sheet)["print_area"]
        if area:
            return list(area)
        paging = item.paging
        data = item.sheet.data_area()
        bottom = data[2] if data is not None else paging.slices[-1][1]
        return [0, paging.first_col, bottom, paging.last_col]

    @staticmethod
    def _area_edge(item, local: QPointF, tol: float):
        """The edge of the printed area under a point — "left", "right", "top"
        or "bottom" — as Excel's Page Break Preview lets them be dragged.
        Without a print area only the right edge (the paper's width) is one."""
        paging = item.paging
        xs, ys = item.edges()
        c0, c1 = paging.first_col, paging.last_col
        if c1 + 1 >= len(xs):
            return None
        rows = paging.print_rows
        top = ys[rows[0]] if rows else 0.0
        bottom = ys[min(rows[1] + 1, len(ys) - 1)] if rows else ys[-1]
        x, y = local.x(), local.y()
        across = xs[c0] - tol <= x <= xs[c1 + 1] + tol
        down = max(top - tol, 0.0) <= y <= bottom + tol
        if down and abs(x - xs[c1 + 1]) <= tol:
            return "right"
        if rows is None:
            return None
        if down and abs(x - xs[c0]) <= tol and x >= 0:
            return "left"
        if across and abs(y - bottom) <= tol:
            return "bottom"
        if across and abs(y - top) <= tol and y >= 0:
            return "top"
        return None

    def _chosen_cols(self, c) -> list:
        """Dragging the edge of a selected column sizes all the selected ones."""
        item = self.item
        t, l, b, r = self.selection()
        if l <= c <= r and t == 0 and b == item.size[0] - 1:
            return list(range(l, r + 1))
        return [c]

    def _chosen_rows(self, row) -> list:
        item = self.item
        t, l, b, r = self.selection()
        if t <= row <= b and l == 0 and r == item.size[1] - 1:
            return list(range(t, b + 1))
        return [row]

    def mouse_move(self, event, scene_pos: QPointF) -> bool:
        if self.insert_drag is not None:
            frame, start, _end = self.insert_drag
            self.insert_drag = (frame, start, frame.mapFromScene(scene_pos))
            self.view.viewport().update()
            return True
        drag = self.drag
        item = self.item
        if drag is None or item is None:
            if item is not None and not (event.buttons() & Qt.LeftButton):
                self._hover(item, scene_pos)
            return False
        local = item.mapFromScene(scene_pos)
        kind = drag[0]
        cell = self._cell_near(item, local)
        if kind == "select":
            self.select(self.anchor, cell, self.active)
        elif kind == "cols":
            self.select((0, self.anchor[1]), (item.size[0] - 1, cell[1]), self.active)
        elif kind == "rows":
            self.select((self.anchor[0], 0), (cell[0], item.size[1] - 1), self.active)
        elif kind == "point":
            self._point_at(drag[1], cell)
        elif kind == "point_other":
            other = drag[2]
            if _alive(other):
                self._point_at(drag[1], self._cell_near(other, other.mapFromScene(scene_pos)), other)
        elif kind in ("col_size", "row_size"):
            # in the sheet's own points, so the edge stays under the pointer
            # on a sheet or table drawn at another scale
            delta = item.mapFromScene(scene_pos) - item.mapFromScene(drag[2])
            moved = delta.x() if kind == "col_size" else delta.y()
            size = max(0.0, drag[3] + moved)
            # Excel: while the edge is dragged a dashed line shows where it
            # will go and a tip gives the size; the column (row) changes when
            # it is let go. Laid out again on every move, a sheet's rows were
            # drawn afresh each time: 25-60 ms a move (findings 5.3)
            self.drag = drag[:6] + (size,)
            self._show_size_guide(item, kind, drag[1], size)
        elif kind == "fill":
            src = drag[1]
            self.drag = ("fill", src, self._fill_target(src, cell), drag[3])
            item.update()
        elif kind == "move":
            src, grabbed, _ = drag[1], drag[2], drag[3]
            dr, dc = cell[0] - grabbed[0], cell[1] - grabbed[1]
            rows, cols = item.size
            dr = max(-src[0], min(dr, rows - 1 - src[2]))
            dc = max(-src[1], min(dc, cols - 1 - src[3]))
            self.drag = ("move", src, grabbed, (dr, dc))
            item.update()
        elif kind == "area":
            side, area = drag[1], list(drag[2])
            xs, ys = item.edges()
            t, l, b, r = area
            if side in ("left", "right"):
                k = min(range(len(xs)), key=lambda i: abs(xs[i] - local.x()))
                if side == "right":
                    area[3] = max(l, k - 1)
                else:
                    area[1] = min(r, k)
            else:
                k = min(range(len(ys)), key=lambda i: abs(ys[i] - local.y()))
                if side == "bottom":
                    area[2] = max(t, k - 1)
                else:
                    area[0] = min(b, k)
            self.drag = ("area", side, drag[2], area)
            item.area_drag = area
            item.update()
            from ..sheet.refs import area_text
            self.view.statusMessage.emit(f"Print area {area_text(*area)}")
        elif kind == "break":
            row = max(1, self._cell_near(item, local)[0])
            if local.y() - item.edges()[1][row] > item.sheet.height(row) / 2:
                row += 1
            self.drag = ("break", drag[1], row)
            item.break_drag = item.edges()[1][min(row, len(item.edges()[1]) - 1)]
            item.update()
            self.view.statusMessage.emit(f"Page break above row {row + 1}")
        elif kind == "vbreak":
            xs = item.edges()[0]
            col = max(1, self._cell_near(item, local)[1])
            if local.x() - xs[col] > item.sheet.width(col) / 2:
                col += 1
            self.drag = ("vbreak", drag[1], col)
            item.vbreak_drag = xs[min(col, len(xs) - 1)]
            item.update()
            self.view.statusMessage.emit(f"Page break left of column {col_letters(col)}")
        elif kind == "grow":
            xs, ys = item.edges()
            rows, cols = drag[1]
            sheet = item.sheet
            from ..items.table import _count_fitting
            new_rows = _count_fitting(max(local.y(), 1), sheet.height, item.size[0], sheet.default_height)
            new_cols = _count_fitting(max(local.x(), 1), sheet.width, item.size[1], sheet.default_width)
            item.resize_table(new_rows, new_cols)
            self.view.statusMessage.emit(f"{item.name}: {new_rows} rows × {new_cols} columns")
        return True

    def _set_print_area(self, item, area: list) -> None:
        """A dragged print area, one undo step. Wider than the paper, it
        prints on pages across, down then over (the user's choice,
        2026-10-11); Fit to N pages wide shrinks it instead."""
        from . import sheetlayout
        sheetlayout.change_options(self.view.window, item, "Set print area", print_area=list(area))

    def _cell_near(self, item, local: QPointF) -> tuple:
        xs, ys = item.edges()
        x = max(0.0, min(local.x(), xs[-1] - 0.01))
        y = max(0.0, min(local.y(), ys[-1] - 0.01))
        return item.cell_at(QPointF(x, y))

    @staticmethod
    def _fill_target(src, cell):
        t, l, b, r = src
        row, col = cell
        down, up = row - b, t - row
        right, left = col - r, l - col
        best = max(down, up, right, left)
        if best <= 0:
            return None
        if best == down:
            return (b + 1, l, row, r)
        if best == up:
            return (row, l, t - 1, r)
        if best == right:
            return (t, r + 1, b, col)
        return (t, col, b, l - 1)

    #: a HYPERLINK cell pressed on a sheet: (what link_at said, when)
    _link_press = None

    def mouse_release(self, event, scene_pos: QPointF) -> bool:
        pressed, self._link_press = self._link_press, None
        if pressed is not None:
            import time
            (table, cell, link), when = pressed
            if time.monotonic() - when < LINK_HOLD:
                self.follow_link(table, cell, link)
            else:
                if self.item is not table:
                    self.open(table, cell)
                self.select(cell)
            return True
        if self.insert_drag is not None:
            self._finish_insert()
            return True
        drag, self.drag = self.drag, None
        item = self.item
        if drag is None or item is None:
            return False
        kind = drag[0]
        if kind == "area":
            item.area_drag = None
            item.update()
            if drag[3] != drag[2]:
                self._set_print_area(item, drag[3])
            return True
        if kind == "break":
            item.break_drag = None
            item.update()
            if drag[2] != drag[1]:
                from . import sheetlayout
                from ..sheet.pagination import options
                old = drag[1] if drag[1] in options(item.sheet)["breaks"] else None
                sheetlayout.move_break(self.view.window, item, old, drag[2])
            return True
        if kind == "vbreak":
            item.vbreak_drag = None
            item.update()
            if drag[2] != drag[1]:
                from . import sheetlayout
                from ..sheet.pagination import options
                old = drag[1] if drag[1] in (options(item.sheet).get("col_breaks") or []) else None
                sheetlayout.move_break(self.view.window, item, old, drag[2], across=True)
            return True
        if kind in ("col_size", "row_size"):
            self._hide_size_guide(item)
            if len(drag) > 6:              # let go: now the size is set
                axis = "col" if kind == "col_size" else "row"
                # dragged to nothing it is hidden, as in Excel (QA, 2026-10-15)
                item.sheet.workbook.drag_size(item.sheet, axis, drag[4], drag[6], drag[5])
                item.layout_changed()
        if kind in ("col_size", "row_size", "grow"):
            self.view.commit_snapshot({"col_size": "Column width", "row_size": "Row height",
                                       "grow": "Resize table"}[kind])
            self._show_selection()
        elif kind == "fill" and drag[2] is not None:
            src, dst, ctrl = drag[1], drag[2], drag[3]
            from ..sheet.fill import fill

            self._change("Fill", lambda wb, sheet: fill(wb, sheet, src, dst, step_one=ctrl))
            t = min(src[0], dst[0]), min(src[1], dst[1])
            b = max(src[2], dst[2]), max(src[3], dst[3])
            self.select(t, b, self.active)
        elif kind == "move" and drag[3] is not None and drag[3] != (0, 0):
            src, (dr, dc) = drag[1], drag[3]
            copy = bool(event.modifiers() & Qt.ControlModifier)
            if event.modifiers() & Qt.ShiftModifier and not copy:
                # Excel: Shift + drag cuts the cells and inserts them there,
                # the cells between closing up behind them
                moved = self._insert_moved(src, dr, dc)
                if moved is not None:
                    self.select(*moved)
                    return True
            if copy:
                self._change("Copy cells", lambda wb, sheet: wb.copy_block(
                    sheet, *src, sheet, src[0] + dr, src[1] + dc))
            else:
                self._change("Move cells", lambda wb, sheet: wb.move_block(
                    sheet, *src, sheet, src[0] + dr, src[1] + dc))
            self.select((src[0] + dr, src[1] + dc), (src[2] + dr, src[3] + dc))
        elif kind == "select" and self.held_format is not None:
            self._paint_held_format()
        elif kind in ("select", "cols", "rows", "point", "point_other") and \
                item.selection is not None and item.active is not None:
            # nothing was drawn for the drag but the selection itself
            item.update(self._selection_area(item, item.selection, item.active))
            self._update_bar()              # (the Name Box: the active cell again)
        else:
            item.update()
        return True

    def _insert_moved(self, src: tuple, dr: int, dc: int) -> Optional[tuple]:
        """The block *src* cut and inserted *dr* rows down (or *dc* columns
        across, whichever is the longer way): one undo step. The
        (anchor, edge) it is at afterwards, or None (nowhere to go)."""
        t, l, b, r = src
        down = abs(dr) >= abs(dc)
        n = (b - t + 1) if down else (r - l + 1)
        step = dr if down else dc
        if step == 0:
            return None
        start = t if down else l
        # where it goes in: before the row (column) the drag reached
        at = start + step if step < 0 else start + step + n
        if start <= at <= start + n:
            return None

        def change(wb, sheet):
            if down:
                wb.shift_cells(sheet, at, l, at + n - 1, r, "row", True)
                old = t + n if at <= t else t
                wb.move_block(sheet, old, l, old + n - 1, r, sheet, at, l)
                wb.shift_cells(sheet, old, l, old + n - 1, r, "row", False)
            else:
                wb.shift_cells(sheet, t, at, b, at + n - 1, "col", True)
                old = l + n if at <= l else l
                wb.move_block(sheet, t, old, b, old + n - 1, sheet, t, at)
                wb.shift_cells(sheet, t, old, b, old + n - 1, "col", False)
        self._change("Move cells", change)
        first = at if at < start else at - n
        if down:
            return (first, l), (first + n - 1, r)
        return (t, first), (b, first + n - 1)

    def _paint_held_format(self) -> None:
        """Format Painter: the carried looks go onto the cells picked (as a
        pattern when more cells are picked than were carried)."""
        held, self.held_format = self.held_format, None
        controls = getattr(self.view.window, "table_controls", None)
        if controls is not None:
            controls.painter.setChecked(False)
        t, l, b, r = self.selection()
        h, w = len(held), len(held[0])

        def change(wb, sheet):
            wb.restyle(sheet, t, l, b, r, lambda st, i, j: held[(i - t) % h][(j - l) % w], "Format Painter")
        self._change("Format Painter", change)

    def mouse_double_click(self, event, scene_pos: QPointF) -> bool:
        if event.button() != Qt.LeftButton or self.view.tool_key != "select":
            return False
        item = self.item
        if item is None:
            top = self.view.markup_at(scene_pos)
            if top is not None and not isinstance(top, TableItem):
                return False                 # a markup or chart over the cells: its own
            target = self.table_at(scene_pos)
            if target is None or not self.view.editable(target):
                return False
            cell = target.cell_at(target.mapFromScene(scene_pos))
            self.open(target, cell)
            return True
        local = item.mapFromScene(scene_pos)
        zone = self._zone(item, local)
        if zone is None:
            return False
        if zone[0] == "tab":
            self.rename()
            return True
        if zone[0] == "col_edge":
            self.autofit("col", self._chosen_cols(zone[1]))
            return True
        if zone[0] == "row_edge":
            self.autofit("row", self._chosen_rows(zone[1]))
            return True
        if zone[0] == "cell":
            self.select((zone[1], zone[2]))
            self.begin_edit(None, enter_mode=False)
            return True
        return True

    def _hover(self, item, scene_pos) -> None:
        zone = self._zone(item, item.mapFromScene(scene_pos))
        kind = zone[0] if zone else None
        if kind == "cell":
            cell = item.sheet.cells.get((zone[1], zone[2]))
            from PySide6.QtWidgets import QToolTip
            why = self.error_text(item, zone[1], zone[2])
            if cell is not None and cell.comment:
                tip = cell.comment + ("\n\n" + why if why else "")
                QToolTip.showText(QCursor.pos(), tip, self.view)
            elif why:
                QToolTip.showText(QCursor.pos(), why, self.view)     # Excel's error tip
            else:
                QToolTip.hideText()
            self.hover_tip = why
        cursor = _cursor_for(zone)
        if kind == "cell" and self.view.tool_key == "select" and self.link_at(scene_pos):
            cursor = QCursor(Qt.PointingHandCursor)       # a HYPERLINK: Ctrl+click follows it
        if cursor is not None:
            self.view.viewport().setCursor(cursor)

    def edge_cursor(self, item, scene_pos: QPointF) -> Optional[QCursor]:
        """Over a run of spreadsheet pages not open yet: the pointer for its
        print area's edges and its page breaks, which drag from there too."""
        zone = self._zone(item, item.mapFromScene(scene_pos))
        return _cursor_for(zone) if zone and zone[0] in ("area", "break", "vbreak") else None

    def hover_cursor(self, scene_pos: QPointF):
        if self.view.tool_key == "select" and self.link_at(scene_pos) is not None:
            # a HYPERLINK cell: the pointing hand, as Excel's
            table = self.link_at(scene_pos)[0]
            self.view.statusMessage.emit(
                "Click to follow the link · click and hold to pick the cell" if _is_run(table)
                else "Ctrl+click to follow the link")
            return QCursor(Qt.PointingHandCursor)
        item = self.item
        if item is None:
            return None
        local = item.mapFromScene(scene_pos)
        if not item.chrome_rect().contains(local):
            return None
        zone = self._zone(item, local)
        if zone and zone[0] == "border" and getattr(self.view, "_control_held", False):
            from .cursors import copy_cursor
            return copy_cursor()               # Ctrl held: a drag copies (Excel's +)
        return _cursor_for(zone) or QCursor(Qt.ArrowCursor)

    # -- inserting a table by dragging ---------------------------------------------------------
    def insert_preview(self) -> Optional[tuple]:
        """(frame, rect in page points, rows, cols) of the table being dragged out."""
        if self.insert_drag is None:
            return None
        frame, start, end = self.insert_drag
        rect = QRectF(start, end).normalized()
        from ..sheet.workbook import DEFAULT_HEIGHT, DEFAULT_WIDTH

        cols = max(1, int(round(rect.width() / DEFAULT_WIDTH)))
        rows = max(1, int(round(rect.height() / DEFAULT_HEIGHT)))
        return frame, QRectF(rect.topLeft(), rect.topLeft() + QPointF(cols * DEFAULT_WIDTH,
                                                                       rows * DEFAULT_HEIGHT)), rows, cols

    def paint_insert_preview(self, painter: QPainter) -> None:
        got = self.insert_preview()
        if got is None:
            return
        frame, rect, rows, cols = got
        box = frame.mapRectToScene(rect)
        painter.save()
        pen = QPen(QColor("#217346"), 0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QColor(33, 115, 70, 20))
        painter.drawRect(box)
        w, h = box.width() / cols, box.height() / rows
        for c in range(1, cols):
            painter.drawLine(QPointF(box.left() + c * w, box.top()), QPointF(box.left() + c * w, box.bottom()))
        for r in range(1, rows):
            painter.drawLine(QPointF(box.left(), box.top() + r * h), QPointF(box.right(), box.top() + r * h))
        font = QFont()
        font.setPixelSize(12)
        painter.setFont(font)
        painter.resetTransform()
        corner = self.view.mapFromScene(box.bottomRight())
        painter.setPen(QColor("#217346"))
        painter.drawText(QPointF(corner.x() + 6, corner.y() + 14), f"{rows} × {cols}")
        painter.restore()

    def _finish_insert(self) -> None:
        got = self.insert_preview()
        start, end = self.insert_drag[1], self.insert_drag[2]
        self.insert_drag = None
        self.view.viewport().update()
        if got is None:
            return
        frame, rect, rows, cols = got
        from .sheetpages import blocks_calc
        if blocks_calc(frame):
            self.view.statusMessage.emit("Tables don't go on spreadsheet pages: "
                                         "type into its cells instead")
            return
        if abs(end.x() - start.x()) < 4 and abs(end.y() - start.y()) < 4:
            rows, cols = 4, 3                 # a click: Excel's handful of cells
        item = TableItem(rows, cols)
        window = self.view.window
        item.author = window.document.settings.default_author or window.document.author
        self.view.begin_snapshot([frame])
        frame.add_markup(item, rect.topLeft())
        self.view.commit_snapshot("Add table")
        self.view.set_tool("select")
        window.sync_tool_buttons() if hasattr(window, "sync_tool_buttons") else None
        self.open(item, (0, 0))

    # -- typing into a cell --------------------------------------------------------------------
    def begin_edit(self, text: Optional[str], enter_mode: bool = True) -> None:
        """Start typing into the active cell: with text, replacing it; with
        None, editing what is there (F2)."""
        item = self.item
        if item is None or item.sheet is None:
            return
        if not self.view.editable(item):
            return
        had_copied = self.copied is not None
        self.copied = None
        cell = self.active
        current = item.sheet.input(*cell)
        editor = self.editor
        if editor is None:
            editor = CellEditor(self, self.view.viewport())
            self.editor = editor
        self.editing_cell = cell
        self.enter_mode = enter_mode
        if had_copied or item.selection is None or item.active is None:
            self._drawn_refs = False        # drawn afresh: the copied block's edge has gone
        else:
            # Nothing is drawn again but SMath's unit box after the cell's
            # value, which goes while it is typed in (the whole sheet was
            # drawn again for the first key of every entry; with OpenGL,
            # the whole canvas)
            self._drawn_refs = None
            self._drawn_refs_area = QRectF()
            got = item.unit_box_rect(*cell) if not self._result_unit_open() else None
            if got is not None and got[0] == "box":
                item.update(self._selection_area(item, item.selection, item.active))
        editor.setText(current if text is None else text)
        editor.setCursorPosition(len(editor.text()))
        self._place_editor()
        editor.show()
        editor.setFocus()
        self._typed(editor.text())

    def _place_editor(self) -> None:
        item, editor = self.item, self.editor
        if item is None or editor is None or self.editing_cell is None:
            return
        rect = item.mapRectToScene(item.cell_rect(*self.editing_cell))
        from .sheetfreeze import shown_point          # (a frozen cell: where it is drawn)
        top_left = shown_point(self.view, item, rect.topLeft())
        bottom_right = shown_point(self.view, item, rect.bottomRight())
        scale = self.view.transform().m11()
        st = item.sheet.workbook.style_of(item.sheet, *self.editing_cell)
        # the cell's font at the zoom it is seen at (a plain font: the page's
        # exact glyph widths are for 1:1)
        font = QFont(cell_font(st).family())
        font.setPixelSize(max(6, int(round((st.size or 11.0) * scale))))
        font.setBold(st.bold)
        font.setItalic(st.italic)
        # (the window's style sheet sets every text box's font size: this
        # one's follows the zoom)
        sheet_text = (
            "QLineEdit { background: white; color: black; border: 2px solid #217346; border-radius: 0px; "
            f"padding: 0px 1px; font-size: {font.pixelSize()}px; "
            f"font-family: '{font.family()}'; font-weight: {700 if st.bold else 400}; "
            f"font-style: {'italic' if st.italic else 'normal'}; }}")
        # Only what has changed is set again. This runs on every repaint of
        # the canvas (it follows the cell as the view scrolls), and setting a
        # style sheet repaints the box -- which repainted the canvas under
        # it, which set the style sheet again: the canvas was redrawn without
        # end while a cell was being typed in (2026-10-16).
        if getattr(editor, "_cell_look", None) != sheet_text:
            editor.setFont(font)
            editor.setStyleSheet(sheet_text)
            editor._cell_look = sheet_text
        width = max(bottom_right.x() - top_left.x() + 2, editor.fontMetrics().horizontalAdvance(
            editor.text() + "  ") + 6)
        height = max(bottom_right.y() - top_left.y() + 2, editor.fontMetrics().height() + 4)
        box = QRect(int(top_left.x()) - 1, int(top_left.y()) - 1, int(width), int(height))
        if editor.geometry() != box:
            editor.setGeometry(box)

    def view_moved(self) -> None:
        """The canvas scrolled or zoomed: the text box follows its cell."""
        if self.editor is not None and self.editor.isVisible():
            self._place_editor()

    #: what the open table last drew for the text being typed: the
    #: references of a formula (each outlined in its colour on its cells)
    _drawn_refs = None

    def insert_function(self) -> None:
        """fx, Excel's Insert Function: a formula started in the active cell
        (or the one being typed), and the list of functions to pick from."""
        if self.item is None or self.active is None:
            return
        if self.editor is None:
            self.begin_edit("=", enter_mode=True)
        elif not self.editor.text().startswith("="):
            self.editor.setText("=" + self.editor.text())
            self._typed(self.editor.text())
        bar = self.bar
        if bar is not None:
            bar.edit.setFocus()
            bar.edit.setCursorPosition(len(bar.edit.text()))

    def _typed(self, text: str) -> None:
        self._status_soon()
        if self.bar is not None and self.bar.edit.text() != text:
            self.bar.edit.setText(text)
        self._place_editor()
        self._refresh_point()
        item = self.item
        if item is not None:
            # the table is drawn again only when what it shows of the typing
            # changes: the references outlined (a value typed in shows
            # nothing until Enter, and redrawing the sheet for every key was
            # most of the time a key took)
            refs = None
            if text.startswith("="):
                refs = tuple(self.formula_marks(text))
            if refs != self._drawn_refs:
                if self._drawn_refs is False:
                    item.update()           # the edit's start: drawn afresh
                else:
                    # only the cells outlined before and now (every cell of
                    # the sheet was drawn again for each reference typed)
                    area = self._refs_area(item, text).united(self._drawn_refs_area)
                    if not area.isEmpty():
                        item.update(area)
                self._drawn_refs = refs
            self._drawn_refs_area = self._refs_area(item, text)
        widget = self._typing_widget()
        if widget is not None:
            self.help.update(widget)

    #: where those references were outlined, in the table's coordinates
    _drawn_refs_area = QRectF()

    def _refs_area(self, item, text: str) -> QRectF:
        """Where the references of formula *text* are outlined on *item*
        (_paint_overlay draws them), with room for their pens."""
        area = QRectF()
        if not text.startswith("=") or item.sheet is None:
            return area
        scale = max(abs(self.view.transform().m11()) + abs(self.view.transform().m12()), 0.05)
        pad = 4.0 / scale
        for _a, _b, _colour, block in self.formula_marks(text, item):
            if block is not None:
                area = area.united(item.block_rect(*block).adjusted(-pad, -pad, pad, pad))
        return area

    def formula_marks(self, text: str, item=None) -> list:
        """What a formula being typed shows, as Excel shows it: each cell
        reference and each spreadsheet name (Define Name, the Name Box… —
        not a CalcForge variable, the user, 2026-10-22) in a colour of its
        own, in order: [(start, end, colour, block)] — where it is in
        *text* (with its "="), and the block of *item*'s cells it outlines
        in that colour (None when they are elsewhere)."""
        item = self.item if item is None else item
        if not text.startswith("=") or item is None or item.sheet is None:
            return []
        try:
            tokens = F.tokenize(text[1:])
        except F.FormulaError:
            return []
        rows, cols = item.size
        out, at = [], 1
        for tok in tokens:
            start = at + len(tok.lead)
            end = start + len(tok.text)
            at = end
            got = None
            if tok.kind == "ref":
                ref = tok.ref
                if ref.sheet is None or ref.sheet.lower() == item.name.lower():
                    if isinstance(ref, CellRef):
                        got = (ref.row, ref.col, ref.row, ref.col)
                    else:
                        got = (ref.top, ref.left, ref.bottom, ref.right)
                    if got[0] >= rows or got[1] >= cols:
                        got = None
            elif tok.kind == "name":
                named = _spreadsheet_name_cells(item.sheet, tok.text)
                if named is None:
                    continue
                sheet, block = named
                got = block if sheet is item.sheet and block[0] < rows and block[1] < cols else None
            else:
                continue
            if got is not None:
                got = (got[0], got[1], min(got[2], rows - 1), min(got[3], cols - 1))
            out.append((start, end, REF_COLOURS[len(out) % len(REF_COLOURS)], got))
        return out

    def _typed_in_bar(self, text: str) -> None:
        if self.editor is None:
            self.begin_edit(text, enter_mode=False)
            self.bar.edit.setFocus()
            return
        self.editor.setText(text)
        self._typed(text)

    def _bar_focused(self) -> None:
        if self.editor is None and self.item is not None:
            self.begin_edit(None, enter_mode=False)
            self.bar.edit.setFocus()

    def _caret_moved(self) -> None:
        self._refresh_point()
        widget = self._typing_widget()
        if widget is not None and self._formula_help is not None:
            self.help.update(widget)

    def _focus_left(self) -> None:
        focus = QApplication.focusWidget()
        if self.editor is None or focus is self.editor or (self.bar and focus is self.bar.edit):
            return
        if focus is self.view or focus is self.view.viewport():
            return
        self.commit(move=None)

    def commit(self, move: Optional[tuple] = (1, 0), all_selected: bool = False,
               tab: bool = False, enter: bool = False) -> bool:
        """Enter: what was typed goes into the cell (or every selected cell
        with Ctrl+Enter), and the selection moves on. False when it can't."""
        editor, item = self.editor, self.item
        if editor is None:
            if move is not None:
                self.move_active(*move, tab=tab, enter=enter)
            return True
        self._hide_help()
        text = editor.text()
        cell = self.editing_cell
        if item is not None and cell is not None and not self._valid(item, cell, text):
            editor.setFocus()
            return False
        self.editor = None
        self.editing_cell = None
        self.point = None
        editor.hide()
        editor.deleteLater()
        self.view.setFocus()
        self._status_soon()
        if item is None or cell is None:
            return True
        old = item.sheet.input(*cell)
        if text != old or all_selected:
            sel = self.selection()
            if all_selected:
                t, l, b, r = sel

                def put(wb, sheet):
                    for row in range(t, b + 1):
                        for col in range(l, r + 1):
                            moved = text
                            if text.startswith("=") and len(text) > 1:
                                moved = "=" + F.moved_formula(text[1:], row - cell[0], col - cell[1])
                            wb.set_input(sheet, row, col, moved)
                self._change("Typing", put)
            else:
                def put_one(wb, sheet):
                    wb.set_input(sheet, cell[0], cell[1], text)
                    self._widen_for_number(sheet, *cell)
                self._change("Typing", put_one)
            problem = item.sheet.cell(*cell).problem if item.sheet.cell(*cell) else None
            if problem:
                self.view.statusMessage.emit(f"{col_letters(cell[1])}{cell[0] + 1}: {problem}")
        if move is not None and not all_selected:
            self.move_active(*move, tab=tab, enter=enter)
        else:
            self._show_selection()
        return True

    def _valid(self, item, cell, text: str) -> bool:
        """Data validation: a Stop rule won't take what it doesn't allow
        (Retry or Cancel); a Warning asks; Information tells."""
        from ..sheet import validation
        if text.startswith("=") or text == item.sheet.input(*cell):
            return True
        message = validation.check(item.sheet, cell[0], cell[1], text)
        if message is None:
            return True
        rule = validation.at(item.sheet, *cell)
        style = rule.get("style", "stop")
        window = self.view.window
        self.view.statusMessage.emit(message)
        if not getattr(window, "interactive_prompts", True):
            return style != "stop"
        from PySide6.QtWidgets import QMessageBox
        title = rule.get("error_title") or "CalcForge"
        if style == "stop":
            got = QMessageBox.critical(self.view, title, message, QMessageBox.Retry | QMessageBox.Cancel)
            if got == QMessageBox.Cancel:
                self.cancel()
            return False
        if style == "warning":
            got = QMessageBox.warning(self.view, title, message + "\n\nContinue?",
                                      QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if got == QMessageBox.Cancel:
                self.cancel()
            return got == QMessageBox.Yes
        got = QMessageBox.information(self.view, title, message, QMessageBox.Ok | QMessageBox.Cancel)
        if got == QMessageBox.Cancel:
            self.cancel()
            return False
        return True

    def list_menu(self):
        """A list validation's choices, to pick one for the active cell."""
        from ..sheet import validation
        item = self.item
        if item is None:
            return None
        rule = validation.at(item.sheet, *self.active)
        if rule is None or rule.get("type") != "list":
            return None
        menu = QMenu(self.view)
        row, col = self.active
        for text in validation.list_items(item.sheet, rule, row, col):
            menu.addAction(text, lambda t=text: self._change(
                "Pick", lambda wb, s: wb.set_input(s, row, col, t)))
        if getattr(self.view.window, "interactive_prompts", True):
            rect = item.mapRectToScene(item.cell_rect(row, col))
            menu.exec(self.view.viewport().mapToGlobal(self.view.mapFromScene(rect.bottomLeft())))
        return menu

    @staticmethod
    def _widen_for_number(sheet, row: int, col: int) -> None:
        """Excel's feel: a number typed into a column whose width was never
        set widens it to fit, rather than showing ####. (A column sized by
        hand keeps its width, and shows ####.)"""
        from ..sheet.numfmt import format_value
        from ..sheet.values import Qty

        if col in sheet.widths or sheet.merge_at(row, col):
            return
        cell = sheet.cells.get((row, col))
        if cell is None or cell.is_formula:
            return
        value = cell.value
        if not isinstance(value, (float, Qty)) or isinstance(value, bool):
            return
        wb = sheet.workbook
        st = wb.styles.get(cell.style)
        if st.wrap or st.shrink or st.rotation:
            return
        # as drawn: a unit's raised powers are narrower than "^2"
        need = shown_width(format_value(value, st.number_format, st.unit,
                                        significant=st.significant), st) + 2 * 2.0 + 2
        if need > sheet.width(col):
            wb.set_widths(sheet, [col], need)

    def cancel(self) -> None:
        self._hide_help()
        editor = self.editor
        if editor is None:
            return
        self.editor = None
        self.editing_cell = None
        self.point = None
        editor.hide()
        editor.deleteLater()
        self.view.setFocus()
        self._status_soon()
        self._show_selection()

    # point mode: a formula waiting for a reference at the caret
    _POINTABLE = re.compile(r"(^=|[-+*/^&=<>,(:;%]|\s)\s*$")

    @staticmethod
    def _name_of(item, top, left, bottom, right) -> Optional[str]:
        """The defined name for exactly this block, if it has one (Excel's Name Box)."""
        from ..sheet.refs import quote_sheet
        ref = f"{quote_sheet(item.name)}!${col_letters(left)}${top + 1}"
        if (top, left) != (bottom, right):
            ref += f":${col_letters(right)}${bottom + 1}"
        for dn in item.sheet.workbook.names.values():
            if dn.refers_to.replace(" ", "").lower() == ref.lower():
                return dn.name
        return None

    def _pointing(self) -> bool:
        editor = self.editor
        if editor is None:
            return False
        text = editor.text()
        if not text.startswith("="):
            return False
        if self.point is not None:
            return True
        before = text[:editor.cursorPosition()]
        return bool(self._POINTABLE.search(before))

    def _point_at(self, first: tuple, last: tuple, other: Optional[TableItem] = None) -> None:
        """Put (or change) the reference at the caret: a cell or block of
        this table, or of another one (with its name)."""
        editor = self.editor
        if editor is None:
            return
        text = editor.text()
        if self.point is not None:
            start, end = self.point
        else:
            start = end = editor.cursorPosition()
        t, l = min(first[0], last[0]), min(first[1], last[1])
        b, r = max(first[0], last[0]), max(first[1], last[1])
        ref = area_text(t, l, b, r)
        item = self.item
        if other is not None and other is not item:
            from ..sheet.refs import quote_sheet
            ref = quote_sheet(other.name) + "!" + ref
        text = text[:start] + ref + text[end:]
        self.point = (start, start + len(ref))
        editor.blockSignals(True)
        editor.setText(text)
        editor.setCursorPosition(start + len(ref))
        editor.blockSignals(False)
        self._typed(text)

    def _refresh_point(self) -> None:
        editor = self.editor
        if editor is None or self.point is None:
            return
        start, end = self.point
        if editor.cursorPosition() != end or editor.text()[start:end] == "" :
            self.point = None

    _result_unit = None

    def _result_unit_open(self) -> bool:
        box = self._result_unit
        return box is not None and box.isVisible()

    def settle_result_unit(self) -> None:
        """The unit box after a cell's result, if it is open, finished as
        leaving it finishes it: what was typed is taken (or refused, and
        why said) and the box goes. Done before anything else happens to
        the cells, so it is never left over other cells or another page."""
        box = self._result_unit
        if box is not None and not box._done:
            box.finish(True)

    def _press_result_unit(self, item, local: QPointF) -> bool:
        """A click on SMath's unit box after the active cell's result (or
        on its unit): the box is typed into."""
        if self.editor is not None or self.active is None:
            return False
        got = item.unit_box_rect(*self.active)
        if got is None:
            return False
        tol = 3.0 / max(self.view.transform().m11(), 0.05)
        if not got[1].adjusted(-tol, -tol, tol, tol).contains(local):
            return False
        if self._result_unit is None:
            from .cellunits import ResultUnit
            self._result_unit = ResultUnit(self)
        self._result_unit.open(item, self.active, got[1])
        return True

    # -- a heading's edge being dragged (Excel's guide line and size tip) ------------------
    size_guide: Optional[tuple] = None     # ("col" | "row", x or y in the item)

    def _guide_strip(self, item) -> Optional[QRectF]:
        guide = self.size_guide
        if guide is None:
            return None
        box = item.local_rect()
        axis, at = guide
        pad = 3.0
        if axis == "col":
            return QRectF(at - pad, -HEADING_H, 2 * pad, box.bottom() + HEADING_H + pad)
        return QRectF(-ROWNUM_W, at - pad, box.right() + ROWNUM_W + pad, 2 * pad)

    def _show_size_guide(self, item, kind: str, index: int, size: float) -> None:
        from PySide6.QtWidgets import QToolTip
        xs, ys = item.edges()
        axis = "col" if kind == "col_size" else "row"
        start = (xs if axis == "col" else ys)[index]
        old = self._guide_strip(item)
        self.size_guide = (axis, start + size)
        for strip in (old, self._guide_strip(item)):
            if strip is not None:
                item.update(strip)         # only the two thin strips are drawn again
        what = "Width" if axis == "col" else "Height"
        pixels = round(size * 96 / 72)
        if size <= 0:
            tip = f"{what}: 0 (hidden)"
        elif axis == "col":
            # Excel's: characters of the default font's digits (7 px, 5 of padding)
            chars = max(0.0, (pixels - 5) / 7.0) if pixels > 12 else pixels / 12.0
            tip = f"Width: {chars:.2f} ({pixels} pixels)"
        else:
            tip = f"Height: {size:.2f} ({pixels} pixels)"
        QToolTip.showText(QCursor.pos(), tip, self.view)
        self.view.statusMessage.emit(tip)

    def _hide_size_guide(self, item) -> None:
        from PySide6.QtWidgets import QToolTip
        strip = self._guide_strip(item)
        self.size_guide = None
        if strip is not None:
            item.update(strip)
        QToolTip.hideText()

    def _paint_size_guide(self, painter: QPainter, item) -> None:
        guide = self.size_guide
        if guide is None:
            return
        axis, at = guide
        box = item.local_rect()
        pen = QPen(QColor("#202020"), 1, Qt.DashLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        if axis == "col":
            painter.drawLine(QPointF(at, -HEADING_H), QPointF(at, box.bottom()))
        else:
            painter.drawLine(QPointF(-ROWNUM_W, at), QPointF(box.right(), at))

    def _paint_overlay(self, painter: QPainter) -> None:
        """The references of the formula being typed, each in its colour on
        its cells, as Excel shows them; and the copied block's dashed edge."""
        item = self._item
        if item is None:
            return
        self._paint_size_guide(painter, item)
        drag = self.drag
        if drag is not None and drag[0] == "fill" and drag[2] is not None:
            box = item.block_rect(*drag[2]).united(item.block_rect(*drag[1]))
            pen = QPen(QColor("#555555"), 1, Qt.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(box)
        if drag is not None and drag[0] == "move" and drag[3] is not None:
            t, l, b, r = drag[1]
            dr, dc = drag[3]
            box = item.block_rect(t + dr, l + dc, b + dr, r + dc)
            pen = QPen(QColor("#217346"), 2, Qt.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(box)
        for block in self.extra_ranges:
            # the blocks picked before with Ctrl: shaded, as Excel's
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 34))
            painter.drawRect(item.block_rect(*block))
        for block in self.highlight_ranges or ():
            # the cells a conditional formatting rule picked in the Rules
            # Manager applies to, outlined as Excel outlines them
            pen = QPen(QColor("#2f6fd6"), 2, Qt.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(QColor(47, 111, 214, 28))
            painter.drawRect(item.block_rect(*block))
        if self.copied is not None and self.copied[0] == item.uid:
            box = item.block_rect(*self.copied[1])
            pen = QPen(QColor("#217346"), 1.5, Qt.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(box)
        editor = self.editor
        if editor is None and self.active is not None and not self._result_unit_open():
            # SMath's black unit box after the selected cell's quantity
            got = item.unit_box_rect(*self.active)
            if got is not None and got[0] == "box":
                painter.fillRect(got[1], QColor("#000000"))
        if editor is None or not editor.text().startswith("="):
            return
        for _a, _b, hue, block in self.formula_marks(editor.text(), item):
            if block is None:
                continue
            colour = QColor(hue)
            box = item.block_rect(*block)
            fill = QColor(colour)
            fill.setAlpha(28)
            painter.fillRect(box, fill)
            pen = QPen(colour, 1.5)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(box)

    # -- keys --------------------------------------------------------------------------------------
    def _editor_key(self, event) -> bool:
        """Keys while typing in a cell; True when handled here."""
        if self._formula_help is not None and self._formula_help.key(event):
            return True                    # the AutoComplete list's Up, Down, Tab, Escape
        key, mods = event.key(), event.modifiers()
        ctrl = bool(mods & Qt.ControlModifier)
        shift = bool(mods & Qt.ShiftModifier)
        editor = self.editor
        if key in (Qt.Key_Return, Qt.Key_Enter):
            if mods & Qt.AltModifier:
                editor.insert("\n")
                return True
            if ctrl:
                self.commit(move=None, all_selected=True)
            else:
                self.commit(move=(-1, 0) if shift else (1, 0), enter=True)
            return True
        if key == Qt.Key_Tab:
            self.commit(move=(0, 1), tab=True)
            return True
        if key == Qt.Key_Backtab:
            self.commit(move=(0, -1), tab=True)
            return True
        if key == Qt.Key_Escape:
            self.cancel()
            return True
        if key == Qt.Key_F4:
            text, caret = F.cycle_reference_at(editor.text()[1:], max(0, editor.cursorPosition() - 1)) \
                if editor.text().startswith("=") else (None, None)
            if text is not None:
                editor.setText("=" + text)
                editor.setCursorPosition(caret + 1)
                self._typed(editor.text())
            return True
        if key == Qt.Key_F2:
            self.enter_mode = not self.enter_mode
            self.view.statusMessage.emit("Edit" if not self.enter_mode else "Enter")
            self._status_soon()
            return True
        arrows = {Qt.Key_Up: (-1, 0), Qt.Key_Down: (1, 0), Qt.Key_Left: (0, -1), Qt.Key_Right: (0, 1)}
        if key in arrows:
            dr, dc = arrows[key]
            if self._pointing() and self.enter_mode:
                # point mode: the arrows move the reference being put in
                # (after F2, Edit mode, they move the caret: Excel's)
                item = self.item
                rows, cols = item.size
                if self.point is None:
                    base = self.editing_cell
                    first = last = (max(0, min(base[0] + dr, rows - 1)), max(0, min(base[1] + dc, cols - 1)))
                    self._point_anchor = first
                else:
                    ref = parse_range(editor.text()[self.point[0]:self.point[1]].split("!")[-1])
                    if isinstance(ref, CellRef):
                        cur = (ref.row, ref.col)
                    elif ref is not None:
                        cur = (ref.last.row, ref.last.col)
                    else:
                        cur = self.editing_cell
                    nxt = (max(0, min(cur[0] + dr, rows - 1)), max(0, min(cur[1] + dc, cols - 1)))
                    if shift:
                        first, last = getattr(self, "_point_anchor", cur), nxt
                    else:
                        first = last = nxt
                        self._point_anchor = nxt
                self._point_at(first, last)
                return True
            if self.enter_mode:
                self.commit(move=(dr, dc))
                return True
            return False
        return False

    def key_press(self, event) -> bool:
        """Keys while a table is open (not typing): Excel's."""
        item = self.item
        if item is None:
            return False
        key, mods = event.key(), event.modifiers()
        ctrl = bool(mods & Qt.ControlModifier)
        shift = bool(mods & Qt.ShiftModifier)
        alt = bool(mods & Qt.AltModifier)
        text = event.text()
        rows, cols = item.size
        arrows = {Qt.Key_Up: (-1, 0), Qt.Key_Down: (1, 0), Qt.Key_Left: (0, -1), Qt.Key_Right: (0, 1)}
        if key == Qt.Key_Escape:
            drag = self.drag
            if drag is not None and drag[0] in ("col_size", "row_size"):
                # Esc while an edge is dragged: left as it was (Excel)
                self.drag = None
                self._hide_size_guide(item)
                self.view.commit_snapshot("Column width" if drag[0] == "col_size" else "Row height")
                return True
            if self.copied is not None:
                self.copied = None
                item.update()
            elif not getattr(item, "alone", False):
                self.close()
            # (the workbook view: there is always an active cell, as in Excel)
            return True
        command = self._bound_command(event)
        if command is not None:
            if command.startswith("menu:"):
                # a cell's right-click entry, or the Style bar's, given a key
                # in Keyboard Shortcuts (bindable.py)
                self.view.window.commands.run(command[5:])
            else:
                SHEET_COMMANDS[command](self)
            return True
        if key in arrows:
            dr, dc = arrows[key]
            if ctrl:
                target = self._jump(self.edge if shift else self.active, dr, dc)
            else:
                base = self.edge if shift else self.active
                target = (base[0] + dr, base[1] + dc)
            if shift:
                self.select(self.anchor, target, self.active)
            else:
                self.select(target)
            return True
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self.move_active(-1 if shift else 1, 0, within=True, enter=True)
            return True
        if key == Qt.Key_Tab:
            self.move_active(0, 1, within=True, tab=True)
            return True
        if key == Qt.Key_Backtab:
            self.move_active(0, -1, within=True, tab=True)
            return True
        if key == Qt.Key_Home:
            from .sheetfreeze import frozen
            # (panes frozen: Excel's Home goes to the first cell not frozen)
            rows, cols = frozen(item) if getattr(item, "alone", False) else (0, 0)
            target = (rows, cols) if ctrl else (self.active[0], cols)
            self.select(self.anchor if shift else target, target if shift else None,
                        self.active if shift else None)
            return True
        if key == Qt.Key_End and ctrl:
            used = item.sheet.used_area()
            target = (used[2], used[3]) if used else (0, 0)
            self.select(self.anchor if shift else target, target if shift else None,
                        self.active if shift else None)
            return True
        if key == Qt.Key_PageDown or key == Qt.Key_PageUp:
            from .sheetview import page_rows
            rows_seen = page_rows(self.view, item)
            step = (rows_seen or 10) * (1 if key == Qt.Key_PageDown else -1)
            if rows_seen and getattr(item, "alone", False):
                # Excel: a screenful down, the window scrolled with the cell
                bar = self.view.verticalScrollBar()
                before = item.mapRectToScene(item.cell_rect(*self.active)).top()
                self._keep_view = True
                try:
                    self.select((self.active[0] + step, self.active[1]))
                finally:
                    self._keep_view = False
                after = item.mapRectToScene(item.cell_rect(*self.active)).top()
                from . import sheetview
                sheetview.fill(self.view, extra=item.mapToScene(
                    item.cell_rect(*self.active).bottomRight()))
                bar.setValue(bar.value() + int(round((after - before) * self.view.zoom())))
                return True
            self.select((self.active[0] + step, self.active[1]))
            return True
        if key in (Qt.Key_Delete,) and not ctrl:
            self.clear("contents")
            return True
        if key == Qt.Key_Backspace and not ctrl:
            self.clear("contents", only_active=True)
            self.begin_edit("", enter_mode=True)
            return True
        if ctrl and not alt and key in (Qt.Key_Z, Qt.Key_Y):
            # one history with the rest of the document (Excel's Ctrl+Z, Ctrl+Y)
            stack = self.view.window.undo_stack
            stack.redo() if key == Qt.Key_Y else stack.undo()
            return True
        if ctrl:
            return False
        if text and text.isprintable() and not ctrl and not alt:
            self.begin_edit(text, enter_mode=True)
            return True
        return False

    def wants_shortcut(self, event) -> bool:
        """Whether a key that is also a window shortcut belongs to the open
        table (so Ctrl+B is bold here, not bookmarks)."""
        if self.item is None or self.editor is not None:
            return False
        key, mods = event.key(), event.modifiers()
        if mods & Qt.ControlModifier and key in (Qt.Key_PageUp, Qt.Key_PageDown):
            return False                 # Excel's next / previous sheet: the window's page keys
        if self._bound_command(event) is not None:
            return True
        if mods & Qt.ControlModifier and key in (Qt.Key_Z, Qt.Key_Y, Qt.Key_Home, Qt.Key_End,
                                                  Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right):
            return True
        if key in (Qt.Key_Delete, Qt.Key_Backspace, Qt.Key_Escape, Qt.Key_Return,
                   Qt.Key_Enter, Qt.Key_Tab, Qt.Key_Backtab, Qt.Key_Home, Qt.Key_End,
                   Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right, Qt.Key_PageUp, Qt.Key_PageDown):
            return True
        text = event.text()
        return bool(text and text.isprintable() and not (mods & (Qt.ControlModifier | Qt.AltModifier)))

    def _bound_command(self, event) -> Optional[str]:
        """The Spreadsheet command a key press is bound to (Excel's keys by
        default; any of them can be changed in Keyboard shortcuts)."""
        from .shortcuts import TABLE
        shortcuts = getattr(self.view.window, "shortcuts", None)
        if shortcuts is None:
            return None
        binding = shortcuts.binding_for_event(event, (TABLE,))
        if binding is None:
            return None
        if binding.kind == "menu":
            return "menu:" + binding.action_id
        if binding.payload not in SHEET_COMMANDS:
            return None
        return binding.payload

    def _jump(self, start: tuple, dr: int, dc: int) -> tuple:
        """Ctrl+arrow: to the edge of the data, as Excel goes."""
        item = self.item
        rows, cols = item.size
        sheet = item.sheet

        def filled(r, c):
            cell = sheet.cells.get((r, c))
            return cell is not None and cell.input != ""

        r, c = start
        nr, nc = r + dr, c + dc
        if not (0 <= nr < rows and 0 <= nc < cols):
            return start
        if filled(r, c) and filled(nr, nc):
            while 0 <= nr + dr < rows and 0 <= nc + dc < cols and filled(nr + dr, nc + dc):
                nr, nc = nr + dr, nc + dc
            return nr, nc
        while 0 <= nr < rows and 0 <= nc < cols and not filled(nr, nc):
            nr, nc = nr + dr, nc + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            return nr, nc
        if getattr(item, "alone", False) and (dr > 0 or dc > 0):
            # the workbook view: on to Excel's last row (or column), the grid
            # grown to reach it (F3)
            from .sheetview import reach
            last = (1_048_575 if dr > 0 else r, 16_383 if dc > 0 else c)
            if reach(self.view, item, last):
                return last
        return (max(0, min(nr - dr, rows - 1)), max(0, min(nc - dc, cols - 1)))

    def move_active(self, dr: int, dc: int, within: bool = False, tab: bool = False,
                    enter: bool = False) -> None:
        """Enter/Tab: on to the next cell (inside the selection when there is one)."""
        item = self.item
        if item is None:
            return
        t, l, b, r = self.selection()
        if within and (t, l) != (b, r):
            row, col = self.active
            if dr:
                row += dr
                if row > b:
                    row, col = t, col + 1 if col < r else l
                elif row < t:
                    row, col = b, col - 1 if col > l else r
            else:
                col += dc
                if col > r:
                    col, row = l, row + 1 if row < b else t
                elif col < l:
                    col, row = r, row - 1 if row > t else b
            self.active = (row, col)
            self._show_selection()
            return
        rows, cols = item.size
        if getattr(item, "SHEET_RUN", False):
            rows += 1                    # one row past the last page (typing there adds one)
        start = self.tab_start
        if tab:
            start = self.active[1] if start is None else start
        elif enter and dr > 0 and dc == 0 and start is not None:
            dc = start - self.active[1]  # Enter after Tabs: back under where they began
            start = None
        else:
            start = None
        row = max(0, min(self.active[0] + dr, rows - 1))
        col = max(0, min(self.active[1] + dc, cols - 1))
        self._keep_tab = True
        try:
            self.select((row, col))
        finally:
            self._keep_tab = False
        self.tab_start = start

    def go_to(self, text: str) -> None:
        ref = parse_range(text.replace("$", ""))
        if ref is None:
            from . import names
            names.go_to_name(self, text)        # a name: go there, or name the selection
            return
        if isinstance(ref, CellRef):
            self.select((ref.row, ref.col))
        else:
            self.select((ref.top, ref.left), (ref.bottom, ref.right), (ref.top, ref.left))
        self.view.setFocus()

    # -- changing the table (each one undo step) ------------------------------------------------------
    def _change(self, label: str, change: Callable) -> None:
        self.settle_result_unit()
        item = self.item
        if item is None or item.sheet is None:
            return
        view = self.view
        view.begin_snapshot(_frames(item))
        sheet = item.sheet
        change(sheet.workbook, sheet)
        item.layout_changed()
        view.commit_snapshot(label)
        if self.item is not None:
            self._show_selection()

    def picked(self) -> list:
        """Every block picked: those added with Ctrl, then the selection."""
        return list(self.extra_ranges) + [tuple(self.selection())]

    def clear(self, what: str = "contents", only_active: bool = False) -> None:
        if only_active:
            blocks = [(self.active[0], self.active[1], self.active[0], self.active[1])]
        else:
            blocks = self.picked()

        def change(wb, sheet):
            for t, l, b, r in blocks:
                wb.clear(sheet, t, l, b, r, what)
        self._change("Clear", change)

    def toggle(self, field: str) -> None:
        item = self.item
        st = item.sheet.workbook.style_of(item.sheet, *self.active)
        value = getattr(st, field)
        if field == "underline":
            new = "" if value else "single"
        else:
            new = not value
        self.format(**{field: new})

    def format(self, **fields) -> None:
        blocks = self.picked()

        def change(wb, sheet):
            for t, l, b, r in blocks:
                wb.format_block(sheet, t, l, b, r, **fields)
        self._change("Format", change)

    # -- Decimal Places and Significant Figures, as an equation's (2026-10-19) --
    def active_style(self):
        item = self.item
        if item is None or item.sheet is None:
            return None
        return item.sheet.workbook.style_of(item.sheet, *self.active)

    def places(self):
        """The decimal places the active cell's format shows, or None (General)."""
        from ..sheet.numfmt import places_of
        st = self.active_style()
        return None if st is None else places_of(st.number_format)

    def set_places(self, places) -> None:
        """Decimal Places ▸ n: the selected cells show *n* places, the active
        cell's format kept in kind (#,##0.00, 0.0%, 0.00E+00) as Excel's
        Increase and Decrease Decimal would leave it; General, a date or a
        fraction becomes Number. None goes back to General. One undo step."""
        from ..sheet.numfmt import with_places
        st = self.active_style()
        if st is None:
            return
        code = None if places is None else with_places(st.number_format, places)
        fields = {"number_format": code}
        if code is None:
            fields["significant"] = False     # General has no places to count
        t, l, b, r = self.selection()
        self._change(f"Decimal places: {places}" if code is not None
                     else "Decimal places: General",
                     lambda wb, sheet: wb.format_block(sheet, t, l, b, r, **fields))

    def set_significant(self, on: bool) -> None:
        """Significant Figures: the selected cells' decimal places count
        significant figures, as an equation's do (SMath's). A cell in
        General is given the document's equation places first, so the tick
        always shows. One undo step."""
        from ..sheet.numfmt import places_of, with_places
        st = self.active_style()
        if st is None:
            return
        fields = {"significant": bool(on)}
        if on and places_of(st.number_format) is None:
            from ..calc.docsheet import sheet_for
            places = sheet_for(self.view.window.document).worksheet.format.decimals
            fields["number_format"] = with_places(st.number_format, places)
        t, l, b, r = self.selection()
        self._change("Significant figures",
                     lambda wb, sheet: wb.format_block(sheet, t, l, b, r, **fields))

    def borders(self, which: str, border: Optional[Border] = None) -> None:
        t, l, b, r = self.selection()
        border = border or THIN
        self._change("Borders", lambda wb, sheet: wb.border_block(sheet, t, l, b, r, which, border))

    def merge(self, how: str = "center") -> None:
        """Merge & Center, Merge Across, Merge Cells, Unmerge."""
        t, l, b, r = self.selection()
        item = self.item
        filled = [p for p in item.sheet.positions_in(t, l, b, r) if item.sheet.input(*p)]
        if how != "unmerge" and len(filled) > 1:
            self.view.statusMessage.emit("Merging keeps only the upper-left value; the others are deleted")

        def change(wb, sheet):
            if how == "unmerge":
                wb.unmerge(sheet, t, l, b, r)
                return
            wb.merge(sheet, t, l, b, r, across=(how == "across"))
            if how == "center":
                wb.format_block(sheet, t, l, b, r, h_align="center")
        self._change("Merge" if how != "unmerge" else "Unmerge", change)
        self.select((t, l), (b, r), (t, l))

    def distribute(self, axis: str) -> None:
        """Distribute rows (or columns) evenly: the selected ones, or all."""
        item = self.item
        t, l, b, r = self.selection()
        rows, cols = item.size
        if axis == "row":
            first, last = (t, b) if b > t else (0, rows - 1)
        else:
            first, last = (l, r) if r > l else (0, cols - 1)
        self._change("Distribute " + ("rows" if axis == "row" else "columns"),
                     lambda wb, sheet: wb.distribute(sheet, axis, first, last))

    def insert_rows(self, below: bool = False) -> None:
        t, l, b, r = self.selection()
        at, n = (b + 1 if below else t), b - t + 1

        def change(wb, sheet):
            wb.insert_rows(sheet, at, n)
            self._look_like_neighbours(wb, sheet, "row", at, n)
        self._change("Insert rows", change)

    def insert_cols(self, right: bool = False) -> None:
        t, l, b, r = self.selection()
        at, n = (r + 1 if right else l), r - l + 1

        def change(wb, sheet):
            wb.insert_cols(sheet, at, n)
            self._look_like_neighbours(wb, sheet, "col", at, n)
        self._change("Insert columns", change)

    @staticmethod
    def _look_like_neighbours(wb, sheet, axis, at, n) -> None:
        """New rows and columns take the look of the one before them (as
        Excel's Format Same As Above), so a bordered table stays bordered."""
        if sheet.size is not None:
            rows, cols = sheet.size
        else:                            # a spreadsheet page: as far as its cells go
            rows = max((r for r, _c in sheet.cells), default=-1) + 1
            cols = max((c for _r, c in sheet.cells), default=-1) + 1
        src = at - 1 if at > 0 else at + n
        for k in range(n):
            i = at + k
            if axis == "row":
                for c in range(cols):
                    s = sheet.cells.get((src, c))
                    if s and not sheet.cells.get((i, c)):
                        wb._set_state(sheet, i, c, ("", s.style, None))
            else:
                for r in range(rows):
                    s = sheet.cells.get((r, src))
                    if s and not sheet.cells.get((r, i)):
                        wb._set_state(sheet, r, i, ("", s.style, None))

    def delete_rows(self) -> None:
        t, l, b, r = self.selection()
        if b - t + 1 >= self.item.size[0]:
            self.view.statusMessage.emit("A table keeps at least one row")
            return
        self._change("Delete rows", lambda wb, sheet: wb.delete_rows(sheet, t, b - t + 1))
        self.select((min(t, self.item.size[0] - 1), l))

    def delete_cols(self) -> None:
        t, l, b, r = self.selection()
        if r - l + 1 >= self.item.size[1]:
            self.view.statusMessage.emit("A table keeps at least one column")
            return
        self._change("Delete columns", lambda wb, sheet: wb.delete_cols(sheet, l, r - l + 1))
        self.select((t, min(l, self.item.size[1] - 1)))

    def _whole(self) -> Optional[str]:
        """"row" when whole rows are selected, "col" for whole columns, else None."""
        t, l, b, r = self.selection()
        rows, cols = self.item.size
        if l == 0 and r == cols - 1:
            return "row"
        if t == 0 and b == rows - 1:
            return "col"
        return None

    def insert_cells(self):
        """Excel's Ctrl++ (Insert…): whole rows or columns selected are
        inserted at once; otherwise the Insert dialog asks how (QA F-13)."""
        whole = self._whole()
        if whole is not None:
            self.insert_or_delete(whole, True)
            return None
        from . import datatools
        return datatools.cells_dialog(self, True)

    def delete_cells(self):
        """Excel's Ctrl+- (Delete…): as Insert, the Delete dialog for cells."""
        whole = self._whole()
        if whole is not None:
            self.insert_or_delete(whole, False)
            return None
        from . import datatools
        return datatools.cells_dialog(self, False)

    def insert_or_delete(self, how: str, insert: bool) -> None:
        """What the Insert or Delete dialog chose: "row" or "col" for whole
        ones, "down"/"right" (insert) or "up"/"left" (delete) to shift the
        cells beside the selection."""
        if how == "row":
            (self.insert_rows if insert else self.delete_rows)()
            return
        if how == "col":
            (self.insert_cols if insert else self.delete_cols)()
            return
        t, l, b, r = self.selection()
        axis = "row" if how in ("down", "up") else "col"
        wb = self.item.sheet.workbook
        if wb.merges_in_the_way(self.item.sheet, t, l, b, r, axis):
            self.view.statusMessage.emit("Cells can't be shifted through merged cells: "
                                         "unmerge them first")   # Excel refuses too
            return
        self._change("Insert cells" if insert else "Delete cells",
                     lambda wb, sheet: wb.shift_cells(sheet, t, l, b, r, axis, insert))
        self.select((t, l), (b, r), (t, l))

    def hide(self, axis: str, hidden: bool) -> None:
        t, l, b, r = self.selection()
        indexes = range(t, b + 1) if axis == "row" else range(l, r + 1)
        if hidden:
            rows, cols = self.item.size
            if len(indexes) >= (rows if axis == "row" else cols):
                return                     # Excel keeps one row or column showing
        self._change("Hide" if hidden else "Unhide",
                     lambda wb, sheet: wb.set_hidden(sheet, axis, indexes, hidden))

    def set_size(self, axis: str, size: float) -> None:
        t, l, b, r = self.selection()
        if axis == "row":
            self._change("Row height", lambda wb, sheet: wb.set_heights(sheet, range(t, b + 1), size))
        else:
            self._change("Column width", lambda wb, sheet: wb.set_widths(sheet, range(l, r + 1), size))

    def autofit(self, axis: str, indexes: list) -> None:
        """Fit columns to their widest text (or rows to their tallest)."""
        item = self.item
        sheet = item.sheet
        wb = sheet.workbook
        from ..items.table import _metrics
        from ..sheet.numfmt import format_value
        from ..sheet.refs import MAX_COLS, MAX_ROWS

        sizes = {}
        for i in indexes:
            best = 0.0
            # the cells of that column (or row) only, not every cell of the sheet
            line = sheet.positions_in(0, i, MAX_ROWS - 1, i) if axis == "col" else \
                sheet.positions_in(i, 0, i, MAX_COLS - 1)
            for r, c in list(line):
                cell = sheet.cells[(r, c)]
                if cell.value is None:
                    continue
                if sheet.merge_at(r, c):
                    continue
                st = wb.styles.get(cell.style)
                shown = format_value(cell.value, st.number_format, st.unit,
                                     significant=st.significant)
                text = shown.text
                metrics = _metrics(st)
                if axis == "col":
                    # as drawn: a quantity's unit with its powers raised
                    width = shown_width(shown, st) if shown.unit and "\n" not in text \
                        else metrics.horizontalAdvance(text)
                    best = max(best, width + 2 * 2.0 + 1)
                else:
                    lines = text.count("\n") + 1
                    best = max(best, metrics.height() * lines + 2)
            sizes[i] = best or (sheet.default_width if axis == "col" else sheet.default_height)

        def change(wb, sheet):
            for i, size in sizes.items():
                if axis == "col":
                    wb.set_widths(sheet, [i], size)
                else:
                    wb.set_heights(sheet, [i], max(size, 0.0))
        self._change("AutoFit", change)

    def fill_direction(self, direction: str) -> None:
        """Ctrl+D / Ctrl+R: copy the top row (left column) through the selection."""
        t, l, b, r = self.selection()

        if direction == "down":
            if b == t:
                if t == 0:
                    return
                src, dst = (t - 1, l, t - 1, r), (t, l, b, r)
            else:
                src, dst = (t, l, t, r), (t + 1, l, b, r)
        else:
            if r == l:
                if l == 0:
                    return
                src, dst = (t, l - 1, b, l - 1), (t, l, b, r)
            else:
                src, dst = (t, l, b, l), (t, l + 1, b, r)

        def change(wb, sheet):
            # Ctrl+D copies; it never counts on
            for i in range(dst[0], dst[2] + 1):
                for j in range(dst[1], dst[3] + 1):
                    si, sj = (src[0], j) if direction == "down" else (i, src[1])
                    cell = sheet.cells.get((si, sj))
                    text = cell.input if cell else ""
                    if text.startswith("=") and len(text) > 1:
                        text = "=" + F.moved_formula(text[1:], i - si, j - sj)
                    wb._set_state(sheet, i, j, (text, cell.style if cell else 0, None))
        self._change("Fill " + direction, change)

    def autosum(self) -> None:
        """Alt+=: =SUM( ) of the numbers above (or to the left)."""
        item = self.item
        sheet = item.sheet
        row, col = self.active
        from ..sheet.values import is_number

        r = row - 1
        while r >= 0 and is_number(sheet.value(r, col)):
            r -= 1
        if r < row - 1:
            self.begin_edit(f"=SUM({area_text(r + 1, col, row - 1, col)})")
            return
        c = col - 1
        while c >= 0 and is_number(sheet.value(row, c)):
            c -= 1
        if c < col - 1:
            self.begin_edit(f"=SUM({area_text(row, c + 1, row, col - 1)})")
            return
        self.begin_edit("=SUM()")
        self.editor.setCursorPosition(5)

    def rename(self) -> None:
        item = self.item or self._selected_table()
        if item is None:
            return
        from PySide6.QtWidgets import QInputDialog
        if not getattr(self.view.window, "interactive_prompts", True):
            return
        name, ok = QInputDialog.getText(self.view, "Rename table", "Name (formulas that use it follow):",
                                        text=item.name)
        if ok and name.strip():
            self.rename_to(item, name.strip())

    def rename_to(self, item: TableItem, name: str) -> bool:
        wb = item.sheet.workbook
        # formulas in any table may name it: every page with a table is recorded
        frames = []
        for other in self._all_tables():
            if other.parentItem() not in frames:
                frames.append(other.parentItem())
        self.view.begin_snapshot(frames)
        try:
            wb.rename_sheet(item.sheet, name)
        except ValueError as e:
            self.view.statusMessage.emit(str(e))
            self.view._snapshot = []
            return False
        # formulas in other tables changed too: their pages are in the snapshot
        self.view.commit_snapshot("Rename table")
        for other in self._all_tables():
            other.update()
        return True

    def _all_tables(self) -> list:
        out = []
        for frame in getattr(self.view.scene(), "frames", []) or []:
            out.extend(i for i in frame.markups() if isinstance(i, TableItem))
        return out

    def _selected_table(self) -> Optional[TableItem]:
        chosen = [i for i in self.view.scene().selectedItems() if isinstance(i, TableItem)]
        return chosen[0] if chosen else None

    def define_name(self, name: str) -> bool:
        """Name the selected cell or block, for formulas and equations (W_total)."""
        item = self.item
        from ..sheet.refs import quote_sheet

        t, l, b, r = self.selection()
        ref = f"{quote_sheet(item.name)}!${col_letters(l)}${t + 1}"
        if (t, l) != (b, r):
            ref += f":${col_letters(r)}${b + 1}"
        wb = item.sheet.workbook
        try:
            self.view.begin_snapshot(_frames(item))
            wb.define_name(name, ref)
            item.update()
            self.view.commit_snapshot("Define name")
        except (ValueError, F.FormulaError) as e:
            self.view.statusMessage.emit(str(e))
            return False
        from ..calc.docsheet import sheet_for
        sheet_for(self.view.window.document).recalculate()
        return True

    # -- clipboard ---------------------------------------------------------------------------------
    def copy(self, cut: bool = False) -> bool:
        item = self.item
        if item is None:
            return False
        if self.editor is not None:
            return False
        if self.extra_ranges:
            # Excel's own words
            self.view.statusMessage.emit("This command cannot be used on multiple selections")
            return False
        block = self.selection()
        mime = QMimeData()
        for kind, data in clip.to_clipboard(item.sheet, *block).items():
            if kind == "text/plain":
                mime.setText(data.decode("utf-8"))
            elif kind == "text/html":
                mime.setHtml(data.decode("utf-8"))
                mime.setData(kind, data)
            else:
                mime.setData(kind, data)
                if kind == clip.MIME_EXCEL_XML:
                    mime.setData(clip.MIME_EXCEL_XML_ALT, data)
        QApplication.clipboard().setMimeData(mime)
        self.copied = (item.uid, block, cut)
        item.update()
        self.view.statusMessage.emit("Select where to paste and press Enter or Ctrl+V")
        return True

    def paste(self, what: str = "all") -> bool:
        item = self.item
        if item is None or self.editor is not None:
            return False
        formats = clipboard_formats()
        t, l, b, r = self.selection()
        copied = self.copied
        if copied is not None and copied[2] and what == "all":
            # a cut moves the cells, and whatever read them follows
            src_item = next((i for i in self._all_tables() if i.uid == copied[0]), None)
            if src_item is not None:
                block = copied[1]
                self.copied = None
                frames = []
                for other in self._all_tables():
                    if other.parentItem() not in frames:
                        frames.append(other.parentItem())
                self.view.begin_snapshot(frames)
                wb = item.sheet.workbook
                wb.move_block(src_item.sheet, *block, item.sheet, t, l)
                item.layout_changed()
                src_item.update()
                self.view.commit_snapshot("Move cells")
                h, w = block[2] - block[0], block[3] - block[1]
                self.select((t, l), (t + h, l + w), (t, l))
                return True
        try:
            data = clip.from_clipboard(formats) if formats else None
        except (ValueError, KeyError, TypeError, IndexError, AttributeError):
            data = None                    # another program's clipboard we can't read
        if not data or not data.get("rows"):
            # Excel does nothing when there is nothing to paste; it is said
            # here, as the menu's Paste is greyed then (QA F-03)
            self.view.statusMessage.emit("Nothing to paste: copy some cells first")
            return False
        if what == "transpose":
            data, what = clip.transposed(data), "all"
        rows = data["rows"]
        h = len(rows)
        w = max((len(x) for x in rows), default=0)
        # a block copied once pastes into every whole multiple of it that is selected
        reps_r = (b - t + 1) // h if h and (b - t + 1) % h == 0 else 1
        reps_c = (r - l + 1) // w if w and (r - l + 1) % w == 0 else 1
        rows_n, cols_n = item.size
        need_r, need_c = t + h * reps_r, l + w * reps_c
        widths = data.get("widths") or []
        grow = need_r > rows_n or need_c > cols_n

        def change(wb, sheet):
            if grow:
                item.resize_table(max(rows_n, need_r), max(cols_n, need_c))
            for i in range(reps_r):
                for j in range(reps_c):
                    clip.paste(wb, sheet, t + i * h, l + j * w, data, what)
            if what == "all" and widths and not data.get("plain"):
                for k, width in enumerate(widths):
                    if width and l + k >= cols_n:
                        wb.set_widths(sheet, [l + k], width)
        self._change("Paste", change)
        self.select((t, l), (t + h * reps_r - 1, l + w * reps_c - 1), (t, l))
        return True

    # -- the right-click menu ----------------------------------------------------------------------
    def context_menu(self, global_pos, heading: Optional[tuple] = None) -> bool:
        """Excel's cell menu, or — *heading* ("row", r) / ("col", c) — its
        short row or column heading menu."""
        item = self.item
        if item is None:
            return False
        if heading is not None:
            menu = self.heading_menu(*heading)
        else:
            menu = self.cell_menu()
        menu.exec(global_pos)
        menu.deleteLater()          # closed: not kept as a hidden window of the view
        return True

    def _clipboard_entries(self, menu) -> None:
        menu.addAction("Cut", lambda: self.copy(cut=True), QKeySequence.Cut)
        menu.addAction("Copy", self.copy, QKeySequence.Copy)
        # greyed while the clipboard holds nothing, as Excel's are (QA F-03)
        something = clipboard_has_something()
        menu.addAction("Paste", self.paste, QKeySequence.Paste).setEnabled(something)
        special = menu.addMenu("Paste Special")
        special.menuAction().setEnabled(something)
        for label, what in (("Values", "values"), ("Formulas", "formulas"),
                            ("Formats", "formats"), ("Transpose", "transpose")):
            special.addAction(label, lambda w=what: self.paste(w)).setEnabled(something)

    def cell_menu(self) -> QMenu:
        """The cells' right-click menu, grouped and named as Excel's (QA round 4)."""
        from . import menutidy, sheetlayout
        item = self.item
        window = self.view.window
        menu = QMenu(self.view)
        menu.setProperty("cf_context", "cell")
        # first, as a measurement's: the name the calculations read the
        # cells by, and whether later calc sections read them (the user,
        # 2026-10-16)
        self._name_entries(menu)
        menu.addSeparator()
        self._clipboard_entries(menu)
        # Excel's Open Hyperlink: greyed unless the cell holds a HYPERLINK
        from ..sheet.morefunctions import hyperlink_target
        link = hyperlink_target(item.sheet, *self.active)
        follow = menu.addAction("Open Hyperlink",
                                lambda: self.follow_link(item, self.active, link) if link else None)
        follow.setEnabled(bool(link))
        follow.setToolTip(f"Follow {link} (Ctrl+click the cell does too)" if link
                          else "The cell holds no HYPERLINK")
        menu.addSeparator()
        # Insert ▸ and Delete ▸ use the names the Style bar's Rows & Columns
        # menu uses, so the two read alike
        row, col = self.active
        ins = menu.addMenu("Insert")
        ins.addAction("Insert Rows Above", self.insert_rows)
        ins.addAction("Insert Rows Below", lambda: self.insert_rows(below=True))
        ins.addAction("Insert Columns Left", self.insert_cols)
        ins.addAction("Insert Columns Right", lambda: self.insert_cols(right=True))
        ins.addAction("Insert Cells…", self.insert_cells, QKeySequence("Ctrl++"))
        if _is_run(item):
            ins.addSeparator()
            brk = ins.addAction("Insert Page Break",
                                lambda: sheetlayout.insert_break(window, item, row, col))
            brk.setToolTip("A page break above the active cell's row and left of its column")
            brk.setEnabled(row > 0 or col > 0)
        ins.addSeparator()
        charts = ins.addMenu("Chart")
        charts.addAction("XY Scatter", lambda: window.insert_chart("scatter", False, True))
        charts.addAction("Scatter with Lines", lambda: window.insert_chart("scatter", True, True))
        charts.addAction("Line", lambda: window.insert_chart("line", True, False))
        charts.addAction("Column", lambda: window.insert_chart("column", False, False))
        dele = menu.addMenu("Delete")
        dele.addAction("Delete Rows", self.delete_rows)
        dele.addAction("Delete Columns", self.delete_cols)
        dele.addAction("Delete Cells…", self.delete_cells, QKeySequence("Ctrl+-"))
        if _is_run(item) and sheetlayout.has_break(item, row, col):
            dele.addSeparator()
            dele.addAction("Remove Page Break",
                           lambda: sheetlayout.remove_break(window, item, row, col))
        clr = menu.addMenu("Clear")
        clr.addAction("Clear Contents", lambda: self.clear("contents"))
        clr.addAction("Clear Formats", lambda: self.clear("formats"))
        clr.addAction("Clear All", lambda: self.clear("all"))
        menu.addSeparator()
        mm = menu.addMenu("Merge")
        mm.addAction("Merge && Centre", lambda: self.merge("center"))
        mm.addAction("Merge Across", lambda: self.merge("across"))
        mm.addAction("Merge Cells", lambda: self.merge("cells"))
        mm.addAction("Unmerge Cells", lambda: self.merge("unmerge"))
        size = menu.addMenu("Rows && Columns")
        size.addAction("Distribute Rows Evenly", lambda: self.distribute("row"))
        size.addAction("Distribute Columns Evenly", lambda: self.distribute("col"))
        size.addSeparator()
        size.addAction("AutoFit Column Width", lambda: self._autofit("col"))
        size.addAction("AutoFit Row Height", lambda: self._autofit("row"))
        size.addAction("Row Height…", lambda: self._ask_size("row"))
        size.addAction("Column Width…", lambda: self._ask_size("col"))
        size.addSeparator()
        size.addAction("Hide Rows", lambda: self.hide("row", True))
        size.addAction("Unhide Rows", lambda: self.hide("row", False))
        size.addAction("Hide Columns", lambda: self.hide("col", True))
        size.addAction("Unhide Columns", lambda: self.hide("col", False))
        menu.addSeparator()
        menu.addAction("Format Cells…", window.format_cells_dialog, QKeySequence("Ctrl+1"))
        from . import datatools
        datatools.fill_menu(menu, self)
        menu.addSeparator()
        names_menu = menu.addMenu("Names")
        names_menu.addAction("Define Name…", self._ask_name)
        from . import names as _names
        names_menu.addAction("Name Manager…", lambda: _names.name_manager(self), QKeySequence("Ctrl+F3"))
        names_menu.addAction("Create from Selection…", lambda: _names.ask_create_from_selection(self),
                             QKeySequence("Ctrl+Shift+F3"))
        if _is_run(item):
            self._page_layout_menu(menu, item)
        # CalcForge's own, after Excel's (Global is at the top, by the name)
        menu.addSeparator()
        menu.addAction("Rename Sheet…" if _is_run(item) else "Rename Table…", self.rename)
        # last, as on every markup's menu: the Properties panel, which shows
        # the selected cells (2026-10-19)
        menu.addAction("Properties", window.show_properties_panel)
        return menutidy.tidy(menu)

    def selection_name(self, variable: bool = True):
        """The CalcForge variable (DefinedName.variable) that refers to
        exactly the selected cell or block, or None: what the right-click's
        Variable box shows. With *variable* False, any defined name."""
        item = self.item
        if item is None or item.sheet is None:
            return None
        t, l, b, r = self.selection()
        wanted = f"{item.name}!{col_letters(l)}{t + 1}"
        if (t, l) != (b, r):
            wanted += f":{col_letters(r)}{b + 1}"

        def plain(text):
            return text.lstrip("=").replace("$", "").replace("'", "").lower()
        for dn in item.sheet.workbook.names.values():
            if plain(dn.refers_to) == plain(wanted) and (dn.variable or not variable):
                return dn
        return None

    def name_selection(self, text: str) -> bool:
        """The Variable box: name the selection *text* as a CalcForge
        variable (a defined name the equations read bare, and tagged on the
        cells; through the Name Manager's own define and delete), rename it,
        or with nothing typed take its name away. One undo step."""
        from . import names
        text = text.strip()
        old = self.selection_name()
        if old is not None and text == old.name:
            return True
        if not text:
            if old is None:
                return True
            problem = names.delete(self, old)
        else:
            item = self.item
            from ..sheet.refs import quote_sheet
            t, l, b, r = self.selection()
            ref = f"{quote_sheet(item.name)}!${col_letters(l)}${t + 1}"
            if (t, l) != (b, r):
                ref += f":${col_letters(r)}${b + 1}"
            problem = names.define(self, text, ref, replacing=old, variable=True)
        if problem:
            self.view.statusMessage.emit(problem)
            return False
        return True

    def _name_entries(self, menu) -> None:
        """Variable [box] and Global, at the top of the cells' menu: the
        measurement's Variable row (mainwindow._variable_field), for a cell."""
        from PySide6.QtWidgets import QWidget, QWidgetAction
        from . import calcsections
        item = self.item
        window = self.view.window
        holder = QWidget(menu)
        holder.setObjectName("cellVariableRow")
        row = QHBoxLayout(holder)
        row.setContentsMargins(24, 3, 10, 3)
        row.setSpacing(6)
        row.addWidget(QLabel("Variable"))
        named = self.selection_name()
        # typed and drawn as SMath writes a name, as the measurement's is
        from .namebox import SMathNameEdit
        field = SMathNameEdit(named.name if named is not None else "")
        field.setObjectName("cellVariable")
        field.setPlaceholderText("name")
        field.setToolTip("Name these cells as a CalcForge variable, read bare by the equations "
                         "and formulas and tagged on the cells, as in an equation: W . total "
                         "gives W with a subscript (in the Name Manager); empty for none · "
                         "Enter to set")
        field.setMinimumWidth(110)
        row.addWidget(field, 1)
        action = QWidgetAction(menu)
        action.setDefaultWidget(holder)
        menu.addAction(action)
        done = {"set": False}

        def commit():
            if done["set"] or self.item is not item:
                return
            done["set"] = True
            now = self.selection_name()
            if field.text().strip() != (now.name if now is not None else ""):
                self.name_selection(field.text())

        def on_enter():
            commit()
            menu.close()
        field.returnPressed.connect(on_enter)
        menu.aboutToHide.connect(commit)
        # the box takes the keys as soon as the menu opens, as the measurement's
        menu.aboutToShow.connect(lambda: field.setFocus(Qt.PopupFocusReason))
        self.name_field = field
        # then, as at the top of an equation's menu (the user, 2026-10-19):
        # how many decimal places the cells show, whether those count
        # significant figures, and Global
        self.number_entries(menu)
        # calculation sections (2026-10-11): cells read by every later section
        area = list(self.selection())
        on = calcsections.cells_global(item.sheet, area)
        made = menu.addAction("Global",
                              lambda: calcsections.set_cells_global(window, item, area, not on))
        made.setCheckable(True)
        made.setChecked(on)
        made.setToolTip("Equations after a section break can use these cells too")

    def number_entries(self, menu) -> None:
        """Decimal Places ▸ (General, 0–15) and Significant Figures, worded
        and placed as an equation's (ui/calcmenu.fill), for the selected
        cells: Excel's Increase/Decrease Decimal, set to a value."""
        st = self.active_style()
        if st is None:
            return
        places = self.places()
        sub = menu.addMenu("Decimal Places")
        sub.setObjectName("menuCellDecimalPlaces")
        general = sub.addAction("General", lambda: self.set_places(None))
        general.setCheckable(True)
        general.setChecked(places is None)
        general.setToolTip("Excel's General: as many places as fit")
        sub.addSeparator()
        for n in range(16):
            action = sub.addAction(str(n), lambda n=n: self.set_places(n))
            action.setCheckable(True)
            action.setChecked(places == n)
        significant = menu.addAction("Significant Figures")
        significant.setCheckable(True)
        significant.setChecked(bool(st.significant))
        significant.setToolTip("Decimal Places counts significant figures, not places "
                               "after the point")
        significant.triggered.connect(
            lambda _=False, on=not st.significant: self.set_significant(on))

    def heading_menu(self, axis: str, index: int) -> QMenu:
        """Excel's row (or column) heading menu: the short one (QA round 4).
        A heading outside the selection picks out that whole row or column
        first, as Excel does."""
        from . import menutidy, sheetlayout
        item = self.item
        window = self.view.window
        rows, cols = item.size
        t, l, b, r = self.selection()
        row = axis == "row"
        whole = (l == 0 and r == cols - 1) if row else (t == 0 and b == rows - 1)
        inside = (t <= index <= b) if row else (l <= index <= r)
        if not (whole and inside):
            if row:
                self.select((index, 0), (index, cols - 1), (index, 0))
            else:
                self.select((0, index), (rows - 1, index), (0, index))
        menu = QMenu(self.view)
        menu.setProperty("cf_context", f"heading.{axis}")
        self._clipboard_entries(menu)
        menu.addSeparator()
        if row:
            menu.addAction("Insert Rows Above", self.insert_rows)
            menu.addAction("Insert Rows Below", lambda: self.insert_rows(below=True))
            menu.addAction("Delete Rows", self.delete_rows)
        else:
            menu.addAction("Insert Columns Left", self.insert_cols)
            menu.addAction("Insert Columns Right", lambda: self.insert_cols(right=True))
            menu.addAction("Delete Columns", self.delete_cols)
        menu.addAction("Clear Contents", lambda: self.clear("contents"))
        menu.addSeparator()
        menu.addAction("Format Cells…", window.format_cells_dialog, QKeySequence("Ctrl+1"))
        which = "row" if row else "col"
        menu.addAction("Row Height…" if row else "Column Width…", lambda: self._ask_size(which))
        menu.addAction("AutoFit Row Height" if row else "AutoFit Column Width",
                       lambda: self._autofit(which))
        menu.addAction("Hide", lambda: self.hide(which, True))
        menu.addAction("Unhide", lambda: self.hide(which, False))
        if _is_run(item):
            menu.addSeparator()
            at = (index, 0) if row else (0, index)
            brk = menu.addAction("Insert Page Break",
                                 lambda: sheetlayout.insert_break(window, item, *at))
            brk.setToolTip("A page break above this row" if row else
                           "A page break left of this column")
            brk.setEnabled(index > 0)
            if sheetlayout.has_break(item, *at):
                menu.addAction("Remove Page Break",
                               lambda: sheetlayout.remove_break(window, item, *at))
        return menutidy.tidy(menu)

    def _autofit(self, axis: str) -> None:
        t, l, b, r = self.selection()
        self.autofit(axis, list(range(t, b + 1)) if axis == "row" else list(range(l, r + 1)))

    def _page_layout_menu(self, menu, item) -> None:
        """Excel's Page Layout commands, for a spreadsheet page, shaped as its
        ribbon (novice 11) and as Calculation ▸ Page Layout on the menu bar:
        Breaks ▸ (Insert Page Break, Remove Page Break, Reset All Page
        Breaks), Print Area ▸ (Set, Clear), Sheet Layout…. The page break
        stays on Insert ▸ and Delete ▸ as well."""
        from . import sheetlayout
        window = self.view.window
        row, col = self.active
        layout = menu.addMenu("Page Layout")
        breaks = layout.addMenu("Breaks")
        brk = breaks.addAction(window.act_insert_page_break.text(),
                               lambda: sheetlayout.insert_break(window, item, row, col))
        brk.setToolTip(window.act_insert_page_break.toolTip())
        brk.setEnabled(row > 0 or col > 0)
        gone = breaks.addAction(window.act_remove_page_break.text(),
                                lambda: sheetlayout.remove_break(window, item, row, col))
        gone.setToolTip(window.act_remove_page_break.toolTip())
        gone.setEnabled(sheetlayout.has_break(item, row, col))
        breaks.addAction(window.act_reset_page_breaks.text(),
                         lambda: sheetlayout.reset_breaks(window, item)).setToolTip(
            window.act_reset_page_breaks.toolTip())
        area = layout.addMenu("Print Area")
        area.addAction(window.act_set_print_area.text(), lambda: sheetlayout.set_print_area(
            window, item, list(self.selection())))
        area.addAction(window.act_clear_print_area.text(),
                       lambda: sheetlayout.set_print_area(window, item, None))
        layout.addSeparator()
        index = window.document.index_of(item.parentItem().page)
        layout.addAction(window.act_sheet_page_setup.text(),
                         lambda: window.sheet_page_setup(index))

    def _ask_size(self, axis: str) -> None:
        from PySide6.QtWidgets import QInputDialog
        item = self.item
        t, l, b, r = self.selection()
        now = item.sheet.height(t) if axis == "row" else item.sheet.width(l)
        value, ok = QInputDialog.getDouble(self.view, "Row height" if axis == "row" else "Column width",
                                           "Points:", now, 0.0, 1000.0, 2)
        if ok:
            self.set_size(axis, value)

    def _ask_name(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self.view, "Define Name",
                                        "Name (the sheet's own: formulas use it, and "
                                        "equations as Sheet.name):")
        if ok and name.strip():
            self.define_name(name.strip())
