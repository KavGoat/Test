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

from PySide6.QtCore import QEvent, QMimeData, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QLineEdit, QMenu,
                               QWidget)

from ..items.base import MarkupItem
from ..items.table import (HEADING_H, ROWNUM_W, TAB_H, TableItem, THIN, cell_font)
from ..sheet import clip
from ..sheet import formula as F
from ..sheet.refs import CellRef, RangeRef, area_text, col_letters, parse_range
from ..sheet.style import Border

REF_COLOURS = ["#1f6fd1", "#d1281f", "#7b2fb0", "#1d8a3a", "#c76a00", "#008b8b", "#b0306e"]


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


class CellEditor(QLineEdit):
    """The text box over the cell being typed into."""

    def __init__(self, tables: "TableEditing", parent):
        super().__init__(parent)
        self.tables = tables
        self.setFrame(False)
        self.setStyleSheet("QLineEdit { background: white; color: black; "
                           "border: 2px solid #217346; padding: 0px 1px; }")
        self.textEdited.connect(tables._typed)
        self.cursorPositionChanged.connect(lambda *_: tables._caret_moved())

    def event(self, event) -> bool:
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Tab, Qt.Key_Backtab):
            self.keyPressEvent(event)
            return True
        if event.type() == QEvent.ShortcutOverride:
            # every key belongs to the text being typed, not to the window's shortcuts
            event.accept()
            return True
        return super().event(event)

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
        self.names.setToolTip("Go to a named cell or block")
        self.names.setPopupMode(QToolButton.InstantPopup)
        names_list = QMenu(self.names)
        names_list.aboutToShow.connect(lambda: self._fill_names(names_list))
        self.names.setMenu(names_list)
        layout.addWidget(self.names)
        fx = QLabel("fx")
        f = fx.font()
        f.setItalic(True)
        f.setBold(True)
        fx.setFont(f)
        fx.setContentsMargins(4, 0, 4, 0)
        layout.addWidget(fx)
        self.edit = QLineEdit()
        self.edit.setToolTip("What is typed in the cell: its formula, or its value")
        self.edit.textEdited.connect(tables._typed_in_bar)
        self.edit.returnPressed.connect(lambda: tables.commit(move=(1, 0)))
        self.edit.installEventFilter(self)
        layout.addWidget(self.edit, 1)
        self.hide()

    def eventFilter(self, obj, event) -> bool:
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


class TableEditing:
    """The open table, its selection, and what the pointer and keys do to it."""

    def __init__(self, view):
        self.view = view
        self._item: Optional[TableItem] = None
        self._uid: Optional[str] = None
        self.anchor = (0, 0)
        self.active = (0, 0)
        self.edge = (0, 0)              # the selection's moving corner
        self.editor: Optional[CellEditor] = None
        self.editing_cell: Optional[tuple] = None
        self.enter_mode = True          # typed straight in: arrows leave the cell
        self.drag: Optional[tuple] = None
        self.point: Optional[tuple] = None   # (start, end) of the reference being pointed
        self.copied: Optional[tuple] = None  # (uid, block, cut)
        self.bar: Optional[FormulaBar] = None
        self.insert_drag: Optional[tuple] = None

    # -- which table ------------------------------------------------------------------
    @property
    def item(self) -> Optional[TableItem]:
        item = self._item
        if item is not None and _alive(item):
            return item
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
        self._item = None
        self._uid = None
        return None

    held_format = None          # Format Painter: the looks being carried

    def _refresh_controls(self) -> None:
        refresh = getattr(self.view.window, "_refresh_style_controls", None)
        if refresh is not None:
            refresh()

    def is_open(self) -> bool:
        return self.item is not None

    def table_at(self, scene_pos: QPointF, chrome: bool = False) -> Optional[TableItem]:
        for item in self.view.scene().items(scene_pos):
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
        item.prepareGeometryChange()
        cell = cell or (0, 0)
        self.anchor = self.active = self.edge = cell
        self._show_selection()
        if self.bar is not None:
            self.bar.show()
        self._refresh_controls()
        view.setFocus()
        view.statusMessage.emit(f"{item.name}: type into the cells · click outside it or Esc to close it")

    def close(self) -> None:
        item = self.item
        if self.editor is not None:
            self.commit(move=None)
        if item is not None:
            item.opened = False
            item.selection = item.active = None
            item.overlay = None
            item.prepareGeometryChange()
            item.update()
        self._item = None
        self._uid = None
        self.copied = None
        self.held_format = None
        if self.bar is not None:
            self.bar.hide()
        self._refresh_controls()

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

    def select(self, anchor: tuple, edge: Optional[tuple] = None, active: Optional[tuple] = None) -> None:
        item = self.item
        if item is None:
            return
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
        self._show_selection()

    def _show_selection(self) -> None:
        item = self._item
        if item is None:
            return
        item.selection = self.selection()
        item.active = self.active
        item.overlay = self._paint_overlay
        item.update()
        self._update_bar()
        controls = getattr(self.view.window, "table_controls", None)
        if controls is not None:
            controls.sync()
        from ..sheet import validation
        rule = validation.at(item.sheet, *self.active) if item.sheet is not None else None
        if rule is not None and rule.get("input"):
            self.view.statusMessage.emit(rule["input"])
        self._scroll_to(self.active)

    def _scroll_to(self, cell) -> None:
        item = self._item
        if item is None or self.drag is not None:
            return
        rect = item.mapRectToScene(item.cell_rect(*cell))
        self.view.ensureVisible(rect, 8, 8)

    def _update_bar(self) -> None:
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
        else:
            bar.name.setText(f"{bottom - top + 1}R × {right - left + 1}C")
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
        if _is_run(item) and item.paging is not None and 0 <= local.x() < w:
            # a page break line: dragged, it becomes a manual break (Excel)
            paging = item.paging
            if xs[paging.first_col] <= local.x() <= xs[paging.last_col + 1]:
                for k, (a, _b) in enumerate(paging.slices[1:], 1):
                    if abs(local.y() - ys[a]) <= tol and 0 <= local.y():
                        return ("break", a)
        if not _is_run(item) and w - 1 <= local.x() <= w + 5 and h - 1 <= local.y() <= h + 5 and \
                not (0 <= local.x() < w and 0 <= local.y() < h):
            return ("grow",)
        if -HEADING_H <= local.y() < 0 and 0 <= local.x() <= w + tol:
            for c in range(1, len(xs)):
                if abs(local.x() - xs[c]) <= tol:
                    return ("col_edge", c - 1)
            if local.x() < w:
                return ("col", item.cell_at(QPointF(local.x(), 0))[1])
        if -ROWNUM_W <= local.x() < 0 and 0 <= local.y() <= h + tol:
            for r in range(1, len(ys)):
                if abs(local.y() - ys[r]) <= tol:
                    return ("row_edge", r - 1)
            if local.y() < h:
                return ("row", item.cell_at(QPointF(0, local.y()))[0])
        if -ROWNUM_W <= local.x() < 0 and -HEADING_H <= local.y() < 0:
            return ("corner",)
        if item.selection is not None:
            box = item.block_rect(*item.selection)
            outer = box.adjusted(-tol, -tol, tol, tol)
            inner = box.adjusted(tol, tol, -tol, -tol)
            if outer.contains(local) and not inner.contains(local):
                return ("border",)
        hit = item.cell_at(local)
        if hit is not None:
            return ("cell",) + hit
        return None

    def mouse_press(self, event, scene_pos: QPointF) -> bool:
        view = self.view
        if event.button() not in (Qt.LeftButton, Qt.RightButton):
            return False
        if view.tool_key == "table" and event.button() == Qt.LeftButton:
            frame = view.frame_at(scene_pos)
            if frame is not None:
                self.close()
                self.insert_drag = (frame, frame.mapFromScene(scene_pos), frame.mapFromScene(scene_pos))
                return True
            return False
        item = self.item
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
                return self._press_zone(item, zone, event, scene_pos)
        if event.button() != Qt.LeftButton or view.tool_key != "select":
            return False
        target = self.table_at(scene_pos)
        if target is None or not view.editable(target):
            return False
        if _is_run(target) and not view.calc.calc_mode():
            # a spreadsheet page: a markup over the cells is picked first,
            # and anywhere else is a cell (the user's choice)
            for other in view.scene().items(scene_pos):
                if other is target:
                    break
                if isinstance(other, MarkupItem) and other.isVisible():
                    return False
            local = target.mapFromScene(scene_pos)
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
            # Calc mode: clicks go to the cells (the user's choice)
            cell = target.cell_at(local)
            if cell is not None:
                self.open(target, cell)
                self.drag = ("select", cell)
                return True
        return False

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
            self.drag = ("col_size", c, scene_pos, item.sheet.width(c), self._chosen_cols(c))
            self.view.begin_snapshot(_frames(item))
        elif kind == "row_edge":
            r = zone[1]
            self.drag = ("row_size", r, scene_pos, item.sheet.height(r), self._chosen_rows(r))
            self.view.begin_snapshot(_frames(item))
        elif kind == "fill":
            self.drag = ("fill", self.selection(), None, ctrl)
        elif kind == "border":
            self.drag = ("move", self.selection(), item.cell_at(item.mapFromScene(scene_pos)) or self.active,
                         None)
        elif kind == "grow":
            self.drag = ("grow", item.size)
            self.view.begin_snapshot(_frames(item))
        elif kind == "break":
            self.drag = ("break", zone[1], zone[1])
        return True

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
            scale = 1.0
            delta = (scene_pos - drag[2])
            moved = delta.x() if kind == "col_size" else delta.y()
            size = max(0.0, drag[3] + moved / scale)
            wb = item.sheet.workbook
            if kind == "col_size":
                wb.set_widths(item.sheet, drag[4], size)
            else:
                wb.set_heights(item.sheet, drag[4], size)
            item.layout_changed()
            self._show_selection()
            self.view.statusMessage.emit(f"{'Width' if kind == 'col_size' else 'Height'}: "
                                         f"{size:.1f} pt ({round(size * 96 / 72)} px)")
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
        elif kind == "break":
            row = max(1, self._cell_near(item, local)[0])
            if local.y() - item.edges()[1][row] > item.sheet.height(row) / 2:
                row += 1
            self.drag = ("break", drag[1], row)
            item.break_drag = item.edges()[1][min(row, len(item.edges()[1]) - 1)]
            item.update()
            self.view.statusMessage.emit(f"Page break above row {row + 1}")
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

    def mouse_release(self, event, scene_pos: QPointF) -> bool:
        if self.insert_drag is not None:
            self._finish_insert()
            return True
        drag, self.drag = self.drag, None
        item = self.item
        if drag is None or item is None:
            return False
        kind = drag[0]
        if kind == "break":
            item.break_drag = None
            item.update()
            if drag[2] != drag[1]:
                from . import sheetlayout
                from ..sheet.pagination import options
                old = drag[1] if drag[1] in options(item.sheet)["breaks"] else None
                sheetlayout.move_break(self.view.window, item, old, drag[2])
            return True
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
            if copy:
                self._change("Copy cells", lambda wb, sheet: wb.copy_block(
                    sheet, *src, sheet, src[0] + dr, src[1] + dc))
            else:
                self._change("Move cells", lambda wb, sheet: wb.move_block(
                    sheet, *src, sheet, src[0] + dr, src[1] + dc))
            self.select((src[0] + dr, src[1] + dc), (src[2] + dr, src[3] + dc))
        elif kind == "select" and self.held_format is not None:
            self._paint_held_format()
        else:
            item.update()
        return True

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
            if cell is not None and cell.comment:
                QToolTip.showText(QCursor.pos(), cell.comment, self.view)
            else:
                QToolTip.hideText()
        cursor = {"col_edge": Qt.SplitHCursor, "row_edge": Qt.SplitVCursor, "fill": Qt.CrossCursor,
                  "break": Qt.SplitVCursor,
                  "border": Qt.SizeAllCursor, "grow": Qt.SizeFDiagCursor, "tab": Qt.OpenHandCursor,
                  "col": Qt.ArrowCursor, "row": Qt.ArrowCursor, "corner": Qt.ArrowCursor,
                  "cell": Qt.CrossCursor}.get(kind)
        if cursor is not None:
            self.view.viewport().setCursor(cursor)

    def hover_cursor(self, scene_pos: QPointF):
        item = self.item
        if item is None:
            return None
        local = item.mapFromScene(scene_pos)
        if not item.chrome_rect().contains(local):
            return None
        zone = self._zone(item, local)
        kind = zone[0] if zone else None
        return {"col_edge": Qt.SplitHCursor, "row_edge": Qt.SplitVCursor, "fill": Qt.CrossCursor,
                "break": Qt.SplitVCursor,
                "border": Qt.SizeAllCursor, "grow": Qt.SizeFDiagCursor, "tab": Qt.OpenHandCursor,
                "cell": Qt.CrossCursor}.get(kind, Qt.ArrowCursor)

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
        self.copied = None
        cell = self.active
        current = item.sheet.input(*cell)
        editor = self.editor
        if editor is None:
            editor = CellEditor(self, self.view.viewport())
            self.editor = editor
        self.editing_cell = cell
        self.enter_mode = enter_mode
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
        top_left = self.view.mapFromScene(rect.topLeft())
        bottom_right = self.view.mapFromScene(rect.bottomRight())
        scale = self.view.transform().m11()
        st = item.sheet.workbook.style_of(item.sheet, *self.editing_cell)
        # the cell's font at the zoom it is seen at (a plain font: the page's
        # exact glyph widths are for 1:1)
        font = QFont(cell_font(st).family())
        font.setPixelSize(max(6, int(round((st.size or 11.0) * scale))))
        font.setBold(st.bold)
        font.setItalic(st.italic)
        editor.setFont(font)
        # (the window's style sheet sets every text box's font size: this
        # one's follows the zoom)
        editor.setStyleSheet(
            "QLineEdit { background: white; color: black; border: 2px solid #217346; "
            f"padding: 0px 1px; font-size: {font.pixelSize()}px; "
            f"font-family: '{font.family()}'; font-weight: {700 if st.bold else 400}; "
            f"font-style: {'italic' if st.italic else 'normal'}; }}")
        width = max(bottom_right.x() - top_left.x() + 2, editor.fontMetrics().horizontalAdvance(
            editor.text() + "  ") + 6)
        height = max(bottom_right.y() - top_left.y() + 2, editor.fontMetrics().height() + 4)
        editor.setGeometry(int(top_left.x()) - 1, int(top_left.y()) - 1, int(width), int(height))

    def view_moved(self) -> None:
        """The canvas scrolled or zoomed: the text box follows its cell."""
        if self.editor is not None and self.editor.isVisible():
            self._place_editor()

    def _typed(self, text: str) -> None:
        if self.bar is not None and self.bar.edit.text() != text:
            self.bar.edit.setText(text)
        self._place_editor()
        self._refresh_point()
        item = self.item
        if item is not None:
            item.update()

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

    def _focus_left(self) -> None:
        focus = QApplication.focusWidget()
        if self.editor is None or focus is self.editor or (self.bar and focus is self.bar.edit):
            return
        if focus is self.view or focus is self.view.viewport():
            return
        self.commit(move=None)

    def commit(self, move: Optional[tuple] = (1, 0), all_selected: bool = False) -> bool:
        """Enter: what was typed goes into the cell (or every selected cell
        with Ctrl+Enter), and the selection moves on. False when it can't."""
        editor, item = self.editor, self.item
        if editor is None:
            if move is not None:
                self.move_active(*move)
            return True
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
            self.move_active(*move)
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
        from PySide6.QtGui import QFontMetricsF
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
        text = format_value(value, st.number_format, st.unit).text
        need = QFontMetricsF(cell_font(st)).horizontalAdvance(text) + 2 * 2.0 + 2
        if need > sheet.width(col):
            wb.set_widths(sheet, [col], need)

    def cancel(self) -> None:
        editor = self.editor
        if editor is None:
            return
        self.editor = None
        self.editing_cell = None
        self.point = None
        editor.hide()
        editor.deleteLater()
        self.view.setFocus()
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

    def _paint_overlay(self, painter: QPainter) -> None:
        """The references of the formula being typed, each in its colour on
        its cells, as Excel shows them; and the copied block's dashed edge."""
        item = self._item
        if item is None:
            return
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
        if self.copied is not None and self.copied[0] == item.uid:
            box = item.block_rect(*self.copied[1])
            pen = QPen(QColor("#217346"), 1.5, Qt.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(box)
        editor = self.editor
        if editor is None or not editor.text().startswith("="):
            return
        spans = F.reference_spans(editor.text()[1:])
        for k, (_s, _e, ref) in enumerate(spans):
            if ref.sheet is not None and ref.sheet.lower() != item.name.lower():
                continue
            colour = QColor(REF_COLOURS[k % len(REF_COLOURS)])
            if isinstance(ref, CellRef):
                t, l, b, r = ref.row, ref.col, ref.row, ref.col
            else:
                t, l, b, r = ref.top, ref.left, ref.bottom, ref.right
            rows, cols = item.size
            if t >= rows or l >= cols:
                continue
            box = item.block_rect(t, l, min(b, rows - 1), min(r, cols - 1))
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
                self.commit(move=(-1, 0) if shift else (1, 0))
            return True
        if key == Qt.Key_Tab:
            self.commit(move=(0, 1))
            return True
        if key == Qt.Key_Backtab:
            self.commit(move=(0, -1))
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
            return True
        arrows = {Qt.Key_Up: (-1, 0), Qt.Key_Down: (1, 0), Qt.Key_Left: (0, -1), Qt.Key_Right: (0, 1)}
        if key in arrows:
            dr, dc = arrows[key]
            if self._pointing():
                # point mode: the arrows move the reference being put in
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
            if self.copied is not None:
                self.copied = None
                item.update()
            else:
                self.close()
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
            self.move_active(-1 if shift else 1, 0, within=True)
            return True
        if key == Qt.Key_Tab:
            self.move_active(0, 1, within=True)
            return True
        if key == Qt.Key_Backtab:
            self.move_active(0, -1, within=True)
            return True
        if key == Qt.Key_Home:
            target = (0, 0) if ctrl else (self.active[0], 0)
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
            step = 10 if key == Qt.Key_PageDown else -10
            self.select((self.active[0] + step, self.active[1]))
            return True
        if key == Qt.Key_F2 and shift:
            from . import datatools
            datatools.comment_dialog(self)
            return True
        if key == Qt.Key_F3 and ctrl:
            from . import names
            if shift:
                names.ask_create_from_selection(self)       # Ctrl+Shift+F3
            else:
                names.name_manager(self)                    # Ctrl+F3
            return True
        if key == Qt.Key_F2:
            self.begin_edit(None, enter_mode=False)
            return True
        if key == Qt.Key_Down and alt:
            self.list_menu()
            return True
        if key in (Qt.Key_Delete,) and not ctrl:
            self.clear("contents")
            return True
        if key == Qt.Key_Backspace and not ctrl:
            self.clear("contents", only_active=True)
            self.begin_edit("", enter_mode=True)
            return True
        if ctrl and key == Qt.Key_Space:
            self.select((0, self.selection()[1]), (rows - 1, self.selection()[3]), self.active)
            return True
        if shift and key == Qt.Key_Space and not ctrl:
            self.select((self.selection()[0], 0), (self.selection()[2], cols - 1), self.active)
            return True
        if ctrl and not alt:
            letter = {Qt.Key_A: "a", Qt.Key_B: "b", Qt.Key_I: "i", Qt.Key_U: "u", Qt.Key_C: "c",
                      Qt.Key_X: "x", Qt.Key_V: "v", Qt.Key_D: "d", Qt.Key_R: "r", Qt.Key_1: "1",
                      Qt.Key_5: "5", Qt.Key_Semicolon: ";", Qt.Key_Colon: ":", Qt.Key_Minus: "-",
                      Qt.Key_Plus: "+", Qt.Key_Equal: "+", Qt.Key_Z: "z", Qt.Key_Y: "y",
                      Qt.Key_9: "9", Qt.Key_0: "0", Qt.Key_F: "f", Qt.Key_H: "h"}.get(key)
            if letter is not None:
                return self._ctrl(letter, shift)
            return False
        if alt and key == Qt.Key_Equal:
            self.autosum()
            return True
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
        if mods & Qt.ControlModifier and key in (Qt.Key_A, Qt.Key_B, Qt.Key_I, Qt.Key_U, Qt.Key_C,
                                                  Qt.Key_X, Qt.Key_V, Qt.Key_D, Qt.Key_R, Qt.Key_1,
                                                  Qt.Key_5, Qt.Key_Semicolon, Qt.Key_Colon,
                                                  Qt.Key_Minus, Qt.Key_Plus, Qt.Key_Equal, Qt.Key_9,
                                                  Qt.Key_0, Qt.Key_Home, Qt.Key_End, Qt.Key_Space,
                                                  Qt.Key_F, Qt.Key_H,
                                                  Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right):
            return True
        if mods & Qt.ControlModifier and key == Qt.Key_F3:
            return True
        if key in (Qt.Key_Delete, Qt.Key_Backspace, Qt.Key_F2, Qt.Key_Escape, Qt.Key_Return,
                   Qt.Key_Enter, Qt.Key_Tab, Qt.Key_Backtab, Qt.Key_Home, Qt.Key_End,
                   Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right, Qt.Key_PageUp, Qt.Key_PageDown):
            return True
        if mods & Qt.AltModifier and key in (Qt.Key_Equal, Qt.Key_Down):
            return True
        text = event.text()
        return bool(text and text.isprintable() and not (mods & (Qt.ControlModifier | Qt.AltModifier)))

    def _ctrl(self, letter: str, shift: bool) -> bool:
        item = self.item
        rows, cols = item.size
        if letter == "a":
            self.select((0, 0), (rows - 1, cols - 1), self.active)
        elif letter == "b":
            self.toggle("bold")
        elif letter == "i":
            self.toggle("italic")
        elif letter == "u":
            self.toggle("underline")
        elif letter == "5":
            self.toggle("strike")
        elif letter == "c":
            self.copy()
        elif letter == "x":
            self.copy(cut=True)
        elif letter == "v":
            self.paste()
        elif letter == "d":
            self.fill_direction("down")
        elif letter == "r":
            self.fill_direction("right")
        elif letter == "1":
            self.view.window.format_cells_dialog() if hasattr(self.view.window, "format_cells_dialog") else None
        elif letter == ";":
            today = datetime.date.today().isoformat()
            self.begin_edit(today if not shift else datetime.datetime.now().strftime("%H:%M"))
        elif letter == ":":
            self.begin_edit(datetime.datetime.now().strftime("%H:%M"))
        elif letter == "-":
            self.delete_cells()
        elif letter == "+":
            self.insert_cells()
        elif letter == "z":
            self.view.window.undo_stack.undo()
        elif letter == "y":
            self.view.window.undo_stack.redo()
        elif letter in ("f", "h"):
            from . import datatools
            datatools.find_dialog(self, replace=letter == "h")
        elif letter == "9":
            self.hide("row", not shift)
        elif letter == "0":
            self.hide("col", not shift)
        return True

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
        return (max(0, min(nr - dr, rows - 1)), max(0, min(nc - dc, cols - 1)))

    def move_active(self, dr: int, dc: int, within: bool = False) -> None:
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
        row = max(0, min(self.active[0] + dr, rows - 1))
        col = max(0, min(self.active[1] + dc, cols - 1))
        self.select((row, col))

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

    def clear(self, what: str = "contents", only_active: bool = False) -> None:
        t, l, b, r = (self.active * 2) if only_active else self.selection()
        if only_active:
            t, l, b, r = self.active[0], self.active[1], self.active[0], self.active[1]
        self._change("Clear", lambda wb, sheet: wb.clear(sheet, t, l, b, r, what))

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
        t, l, b, r = self.selection()
        self._change("Format", lambda wb, sheet: wb.format_block(sheet, t, l, b, r, **fields))

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

    def insert_cells(self) -> None:
        t, l, b, r = self.selection()
        rows, cols = self.item.size
        if l == 0 and r == cols - 1:
            self.insert_rows()
        else:
            self.insert_cols()

    def delete_cells(self) -> None:
        t, l, b, r = self.selection()
        rows, cols = self.item.size
        if l == 0 and r == cols - 1:
            self.delete_rows()
        else:
            self.delete_cols()

    def hide(self, axis: str, hidden: bool) -> None:
        t, l, b, r = self.selection()
        indexes = range(t, b + 1) if axis == "row" else range(l, r + 1)
        if hidden:
            rows, cols = self.item.size
            if len(indexes) >= (rows if axis == "row" else cols):
                return
        else:
            # unhide: those inside the selection
            pass
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
        from PySide6.QtGui import QFontMetricsF
        from ..sheet.numfmt import format_value

        sizes = {}
        for i in indexes:
            best = 0.0
            for (r, c), cell in sheet.cells.items():
                if (c if axis == "col" else r) != i or cell.value is None:
                    continue
                if sheet.merge_at(r, c):
                    continue
                st = wb.styles.get(cell.style)
                text = format_value(cell.value, st.number_format, st.unit).text
                metrics = QFontMetricsF(cell_font(st))
                if axis == "col":
                    best = max(best, metrics.horizontalAdvance(text) + 2 * 2.0 + 1)
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
        from ..sheet.fill import fill

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
        mime = QApplication.clipboard().mimeData()
        formats = {}
        for kind in mime.formats():
            formats[kind] = bytes(mime.data(kind))
        if mime.hasText() and "text/plain" not in formats:
            formats["text/plain"] = mime.text().encode("utf-8")
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
        data = clip.from_clipboard(formats)
        if data is None:
            return False
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
    def context_menu(self, global_pos) -> bool:
        item = self.item
        if item is None:
            return False
        menu = QMenu(self.view)
        menu.addAction("Cut", lambda: self.copy(cut=True), QKeySequence.Cut)
        menu.addAction("Copy", self.copy, QKeySequence.Copy)
        menu.addAction("Paste", self.paste, QKeySequence.Paste)
        special = menu.addMenu("Paste Special")
        special.addAction("Values", lambda: self.paste("values"))
        special.addAction("Formulas", lambda: self.paste("formulas"))
        special.addAction("Formats", lambda: self.paste("formats"))
        menu.addSeparator()
        ins = menu.addMenu("Insert")
        ins.addAction("Rows above", self.insert_rows)
        ins.addAction("Rows below", lambda: self.insert_rows(below=True))
        ins.addAction("Columns to the left", self.insert_cols)
        ins.addAction("Columns to the right", lambda: self.insert_cols(right=True))
        dele = menu.addMenu("Delete")
        dele.addAction("Rows", self.delete_rows)
        dele.addAction("Columns", self.delete_cols)
        clr = menu.addMenu("Clear")
        clr.addAction("Contents", lambda: self.clear("contents"))
        clr.addAction("Formats", lambda: self.clear("formats"))
        clr.addAction("All", lambda: self.clear("all"))
        menu.addSeparator()
        mm = menu.addMenu("Merge")
        mm.addAction("Merge && Center", lambda: self.merge("center"))
        mm.addAction("Merge Across", lambda: self.merge("across"))
        mm.addAction("Merge Cells", lambda: self.merge("cells"))
        mm.addAction("Unmerge Cells", lambda: self.merge("unmerge"))
        size = menu.addMenu("Rows && Columns")
        size.addAction("Distribute Rows Evenly", lambda: self.distribute("row"))
        size.addAction("Distribute Columns Evenly", lambda: self.distribute("col"))
        size.addSeparator()
        size.addAction("AutoFit Column Width", lambda: self.autofit(
            "col", list(range(self.selection()[1], self.selection()[3] + 1))))
        size.addAction("AutoFit Row Height", lambda: self.autofit(
            "row", list(range(self.selection()[0], self.selection()[2] + 1))))
        size.addAction("Row Height…", lambda: self._ask_size("row"))
        size.addAction("Column Width…", lambda: self._ask_size("col"))
        size.addSeparator()
        size.addAction("Hide Rows", lambda: self.hide("row", True))
        size.addAction("Unhide Rows", lambda: self.hide("row", False))
        size.addAction("Hide Columns", lambda: self.hide("col", True))
        size.addAction("Unhide Columns", lambda: self.hide("col", False))
        menu.addSeparator()
        window = self.view.window
        if hasattr(window, "format_cells_dialog"):
            menu.addAction("Format Cells…", window.format_cells_dialog, QKeySequence("Ctrl+1"))
        from . import datatools
        datatools.fill_menu(menu, self)
        menu.addSeparator()
        charts = menu.addMenu("Insert Chart")
        window = self.view.window
        charts.addAction("XY Scatter", lambda: window.insert_chart("scatter", False, True))
        charts.addAction("Scatter with Lines", lambda: window.insert_chart("scatter", True, True))
        charts.addAction("Line", lambda: window.insert_chart("line", True, False))
        charts.addAction("Column", lambda: window.insert_chart("column", False, False))
        names_menu = menu.addMenu("Names")
        names_menu.addAction("Define Name…", self._ask_name)
        from . import names as _names
        names_menu.addAction("Name Manager…", lambda: _names.name_manager(self), QKeySequence("Ctrl+F3"))
        names_menu.addAction("Create from Selection…", lambda: _names.ask_create_from_selection(self),
                             QKeySequence("Ctrl+Shift+F3"))
        if _is_run(item):
            self._page_layout_menu(menu, item)
            menu.addAction("Rename Sheet…", self.rename)
        else:
            menu.addAction("Rename Table…", self.rename)
        menu.exec(global_pos)
        return True

    def _page_layout_menu(self, menu, item) -> None:
        """Excel's Page Layout commands, for a spreadsheet page."""
        from . import sheetlayout
        from ..sheet.pagination import options
        window = self.view.window
        layout = menu.addMenu("Page Layout")
        row = self.active[0]
        breaks = options(item.sheet)["breaks"]
        if row in breaks:
            layout.addAction("Remove Page Break", lambda: sheetlayout.remove_break(window, item, row))
        else:
            act = layout.addAction("Insert Page Break", lambda: sheetlayout.insert_break(window, item, row))
            act.setEnabled(row > 0)
        layout.addAction("Reset All Page Breaks", lambda: sheetlayout.reset_breaks(window, item))
        layout.addSeparator()
        layout.addAction("Set Print Area", lambda: sheetlayout.set_print_area(
            window, item, list(self.selection())))
        layout.addAction("Clear Print Area", lambda: sheetlayout.set_print_area(window, item, None))
        layout.addSeparator()
        index = window.document.index_of(item.parentItem().page)
        layout.addAction("Page Layout…", lambda: window.sheet_page_setup(index))

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
                                        "Name (equations and formulas can then use it):")
        if ok and name.strip():
            self.define_name(name.strip())
