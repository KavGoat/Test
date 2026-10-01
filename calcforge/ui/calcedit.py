"""Typing and clicking equations on the canvas (decisions 5, 6, 13, 14).

WebSMath's worksheet view knew how SMath's keyboard works: which key goes to
the equation editor, Enter leaves an equation and puts the red cross under
it, Tab and Up/Down step from region to region in reading order, the
autocomplete list and its keys, and the unit-or-variable clash. That logic is
here, working on MarkForge's canvas: equations are page items (``CalcItem``),
the document has one worksheet, and every edit is one step on the window's
undo stack.

While an equation has the cursor, SMath's keys win (decision 6): the window's
shortcut filter already holds shortcuts back while ``view.is_editing()``, so
Ctrl+0 means ≥ here and fit-page elsewhere. A Ctrl key SMath has no use for
(save, print, zoom) is handed to the window's own command.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QAction, QColor, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import QApplication

from ..calc.docsheet import PT_PER_PX, PX_PER_PT, sheet_for
from ..calc.engine.units import is_unit
from ..calc.ui.suggest import (KEYWORDS, SMATH_LABEL, SuggestionList, _selection_key_name,
                               selected_index, suggestion_entries, unit_box_entries)
from ..items.calc import CalcItem, calc_area, created_here  # noqa: F401

# SMath's worksheet grid: 9 px, which is 6.75 pt on the page.
GRID_PX = 9.0
GRID_PT = GRID_PX * PT_PER_PX
CROSS = QColor("#ff0000")
CALC = "calc"
MARKUP = "markup"


def snap(value: float) -> float:
    return round(value / GRID_PT) * GRID_PT


def undefined_without(document, going: list) -> list:
    """The names the equations in *going* define that nothing left defines —
    the variables that become undefined when they are removed."""
    sheet = sheet_for(document)
    going_ids = set()
    for item in going:
        # an equation, or a measurement that defines a variable (decision 24)
        region = getattr(item, "region", None) or getattr(item, "variable_region", None)
        if region is not None:
            going_ids.add(region.id)
    lost, kept = set(), set()
    for region in sheet.worksheet.regions:
        names = set(region.defined_vars) | {name for name, _ in region.defined_funcs}
        (lost if region.id in going_ids else kept).update(names)
    return sorted(lost - kept)


def names_left_behind(document, kept: list) -> list:
    """The variables equations on the *kept* pages use that are defined only
    on pages left behind — undefined in a file of the kept pages alone."""
    sheet = sheet_for(document)
    kept_uids = {page.uid for page in kept}
    used, here, there = set(), set(), set()
    for region in sheet.worksheet.regions:
        names = set(region.defined_vars) | {name for name, _ in region.defined_funcs}
        if sheet.page_uid(region) in kept_uids:
            used |= set(region.uses)
            here |= names
        else:
            there |= names
    return sorted((used & there) - here)


def snap_px(value: float) -> float:
    """To SMath's grid, in its 96-dpi pixels (a plot's size is kept in them)."""
    return round(value / GRID_PX) * GRID_PX


def _word_char(ch: str) -> bool:
    return ch.isalnum() or ch in "_."


class CalcEditing:
    """The equation being typed into, the red cross, and the keys."""

    def __init__(self, view):
        self.view = view
        self.mode = MARKUP
        self.item: Optional[CalcItem] = None
        self.cross: Optional[tuple] = None          # (frame, page point)
        self.suggestions = SuggestionList(view)
        self.suggestions.hide()
        self.suggestions.itemClicked.connect(self._apply_suggestion)
        # The list is a window of its own, placed on the screen: when the page
        # scrolls or zooms under it, it moves with the equation.
        for bar in (view.horizontalScrollBar(), view.verticalScrollBar()):
            bar.valueChanged.connect(lambda _v: self._follow_the_view())
        self.dynamic_assistance = True
        self._select_drag = None                    # (row, first slot) while dragging a selection
        self._overflow: list = []                   # equations past the bottom of their page
        self._pressed_on: Optional[tuple] = None    # (item, scene point) of a click on an equation
        # What dragging does in a plot that has been double-clicked into
        # (the Maths panel's Plot section): "move" pans, "scale" zooms.
        self.plot_tool = "move"
        self._plot_drag = None                     # (kind, scene start, item, what it was)

    # -- state ---------------------------------------------------------------------
    @property
    def window(self):
        return self.view.window

    def editing(self) -> bool:
        return self.item is not None and self.item.scene() is not None

    def calc_mode(self) -> bool:
        return self.mode == CALC

    # -- where the red cross is ----------------------------------------------------
    def place_cross(self, frame, page_point: QPointF) -> None:
        old = self._cross_rect()
        self.cross = (frame, QPointF(snap(page_point.x()), snap(page_point.y())))
        self.view.viewport().update()
        if old is not None:
            self.view.scene().update(old)

    def clear_cross(self) -> None:
        if self.cross is not None:
            self.cross = None
            self.view.viewport().update()

    def _cross_rect(self) -> Optional[QRectF]:
        if self.cross is None:
            return None
        frame, point = self.cross
        if frame.scene() is None:
            return None
        centre = frame.mapToScene(point)
        return QRectF(centre.x() - GRID_PT, centre.y() - GRID_PT, 2 * GRID_PT, 2 * GRID_PT)

    def draw_cross(self, painter: QPainter) -> None:
        """SMath's red + where the next equation starts (Calc mode only).

        WebSMath's own drawing, line for line (its WorksheetScene.drawForeground),
        in SMath pixels scaled onto the page.
        """
        if self.cross is None or self.editing() or not self.calc_mode():
            return
        frame, point = self.cross
        if frame.scene() is None:
            self.cross = None
            return
        c = frame.mapToScene(point)
        painter.save()
        painter.translate(c)
        painter.scale(PT_PER_PX, PT_PER_PX)
        painter.setPen(QPen(CROSS, 1))
        painter.drawLine(QPointF(-4, 0.5), QPointF(5, 0.5))
        painter.drawLine(QPointF(0.5, -4), QPointF(0.5, 5))
        painter.restore()

    # -- focus -----------------------------------------------------------------------
    def focus(self, item: CalcItem, scene_pos: Optional[QPointF] = None) -> None:
        """Put the cursor in *item* (at the point clicked, if one is given)."""
        if item is self.item:
            if scene_pos is not None:
                self._place_cursor(item, scene_pos)
            return
        self.leave()
        view = self.view
        if view.editing_item() is not None:
            view.end_item_edit()
        view.begin_snapshot(view.involved_frames(item))
        view.scene().clearSelection()
        self.item = item
        item.focused = True
        item.show_upright(self._view_turn())
        item.relayout()
        if scene_pos is not None:
            self._place_cursor(item, scene_pos)
        self.clear_cross()
        view.setFocus(Qt.OtherFocusReason)
        view.selectionChanged.emit()

    def start(self, frame, page_point: QPointF) -> CalcItem:
        """A new, empty equation at *page_point*, with the cursor in it."""
        self.leave()
        view = self.view
        if view.editing_item() is not None:
            view.end_item_edit()
        view.begin_snapshot([frame])
        view.scene().clearSelection()
        item = CalcItem()
        # written on a turned page, it is turned with the page (decision 15)
        item.setRotation(frame.page.turn)
        frame.add_markup(item, QPointF(snap(page_point.x()), snap(page_point.y())))
        region = item.region
        from . import preferences
        prefs = preferences.current()
        region.font_size = float(prefs.equation_font_size)
        region.color = prefs.equation_colour or "#000000"
        self.item = item
        item.focused = True
        item.show_upright(self._view_turn())
        item.relayout()
        self.clear_cross()
        view.setFocus(Qt.OtherFocusReason)
        return item

    def start_plot(self, frame, page_point: QPointF) -> CalcItem:
        """A new 2-D plot (SMath's @), with the cursor in its input."""
        from ..calc.record import region_to_data
        from ..calc.worksheet import Worksheet

        scratch = Worksheet()
        data = region_to_data(scratch.add_plot(0, 0))
        self.leave()
        view = self.view
        view.begin_snapshot([frame])
        view.scene().clearSelection()
        item = CalcItem(data)
        frame.add_markup(item, QPointF(snap(page_point.x()), snap(page_point.y())))
        editor = item.region.editor
        editor.set_cursor(editor.root.items[0].rows[0], 0)
        self.item = item
        item.focused = True
        item.relayout()
        self.clear_cross()
        view.setFocus(Qt.OtherFocusReason)
        return item

    def leave(self, cross_below: bool = False) -> None:
        """Finish the equation being edited: calculate what depends on it,
        and make it one step on the undo stack."""
        item = self.item
        if item is None:
            return
        self.item = None
        self._select_drag = None
        self.hide_suggestions()
        view = self.view
        if item.scene() is None or item.region is None:
            view.commit_snapshot("Edit equation")
            return
        item.focused = False
        item.leave_upright()
        item.region.editor.selection = None
        frame = item.parentItem()
        region = item.region
        empty = (region.plot is None and (
            (region.editor.kind == "math" and region.editor.root.is_empty()) or
            (region.editor.kind == "text" and not region.editor.text.strip())))
        if empty:
            frame.remove_markup(item)
        else:
            region.pending = False
            sheet_for(frame.document).edited(region)
            item.relayout()
            self.note_overflow(item)
        view.commit_snapshot("Edit equation")
        if cross_below and item.scene() is not None:
            # under the equation, wherever it ended up (it may have gone on
            # to the next page)
            rect = item.local_rect()
            self.place_cross(item.parentItem(), QPointF(
                item.pos().x(), item.pos().y() + rect.height() + 5 * PT_PER_PX))
        view.documentEdited.emit()

    def _view_turn(self) -> float:
        return float(getattr(self.view.scene(), "reading_turn", 0) or 0)

    # -- no equation on two pages (decision 11) -------------------------------------------
    def note_overflow(self, item: CalcItem) -> None:
        """Remember *item* if it runs past the bottom of its page's area; it is
        moved when the gesture is committed (view.commit_snapshot)."""
        frame = item.parentItem()
        if frame is None or not hasattr(frame, "page"):
            return
        area = calc_area(frame)
        top = item.pos().y()
        bottom = top + item.local_rect().height()
        if bottom <= area.bottom() + 1e-6 or top <= area.top() + 1e-6:
            return                     # fits — or is taller than a whole page
        if item not in self._overflow:
            self._overflow.append(item)

    def take_overflow(self) -> list:
        items = [i for i in self._overflow if i.scene() is not None]
        self._overflow = []
        return items

    def push_to_next_pages(self, items: list) -> None:
        """Each equation past the bottom of its page goes to the top of the
        next one, at the same distance across; past the last page, a blank
        page is added for it. Called inside the gesture's undo step."""
        window = self.window
        view = self.view
        for item in items:
            frame = item.parentItem()
            pages = window.document.pages
            index = pages.index(frame.page)
            if index == len(pages) - 1:
                self._add_a_page_at_the_end()
                pages = window.document.pages
            target = pages[index + 1].frame
            x = item.pos().x()
            item.setParentItem(target)
            area = calc_area(target)
            item.setPos(QPointF(min(max(x, area.left()), area.right() - GRID_PT), snap(area.top() + GRID_PT)))
        sheet_for(window.document).settle()

    def _add_a_page_at_the_end(self) -> None:
        """A blank page: the last page's size when CalcForge made it, else A4."""
        from ..core.document import PageSetup

        window = self.window
        last = window.document.pages[-1]
        setup = PageSetup.from_dict(last.setup.to_dict()) if created_here(last) \
            else PageSetup.from_name("A4")

        page = window.document.add_page(len(window.document.pages))
        page.setup = setup
        window.rebuild_scenes()

    # -- the mouse pointer, as WebSMath's ---------------------------------------------
    MOVE_EDGE_PX = 4.0     # WebSMath's band along a region's frame that drags it

    @staticmethod
    def move_cursor():
        """SMath's own move cursor (WebSMath's icons/move.cur)."""
        from pathlib import Path

        from PySide6.QtGui import QCursor, QPixmap
        cached = getattr(CalcEditing, "_move_cur", None)
        if cached is None:
            from ..calc import ui as calc_ui
            pm = QPixmap(str(Path(calc_ui.__file__).with_name("icons") / "move.cur"))
            cached = QCursor(pm) if not pm.isNull() else QCursor(Qt.SizeAllCursor)
            CalcEditing._move_cur = cached
        return cached

    def hover_cursor(self, scene_pos: QPointF):
        """What WebSMath shows over an equation: the arrow inside it (typing
        or not, over a plot too), and SMath's move cursor on the band along
        its frame that drags it. None when the pointer isn't on an equation."""
        item = self.calc_item_at(scene_pos)
        if item is None:
            return None
        local = item.mapFromScene(scene_pos)
        rect = item.local_rect()
        # WebSMath's 4 px, on the screen whatever the zoom
        edge = self.MOVE_EDGE_PX / max(self.view.transform().m11(), 0.05)
        on_edge = (local.x() - rect.left() < edge or local.y() - rect.top() < edge
                   or rect.right() - local.x() < edge or rect.bottom() - local.y() < edge)
        if item.region is not None and item.region.plot is not None and not on_edge:
            return Qt.ArrowCursor
        return self.move_cursor() if on_edge else Qt.ArrowCursor

    # -- mouse -----------------------------------------------------------------------
    def calc_item_at(self, scene_pos: QPointF) -> Optional[CalcItem]:
        """The equation under the point, unless it is in a closed calculation
        block: that click is the block's until it is double-clicked open."""
        from ..items.calc import closed_block_of
        for item in self.view.scene().items(scene_pos):
            if isinstance(item, CalcItem) and item.local_rect().contains(item.mapFromScene(scene_pos)):
                return None if closed_block_of(item) is not None else item
        return None

    def mouse_press(self, event, scene_pos: QPointF) -> bool:
        """True when the click was the equation's: the caret, or a selection in it."""
        self._pressed_on = None
        if event.button() != Qt.LeftButton:
            return False
        view = self.view
        if view.tool_key != "select" or view.window.holding_a_format():
            self.leave()
            return False
        item = self.calc_item_at(scene_pos)
        if item is not None and item is self.item and self._on_frame(item, scene_pos):
            # SMath: the frame of the equation being edited picks it up to move
            self.leave()
            if item.scene() is not None:
                item.setSelected(True)
            self._pressed_on = None
            return False
        if item is not None and item is self.item and self._start_plot_drag(item, scene_pos):
            return True
        if item is not None and item is self.item:
            if event.modifiers() & Qt.ShiftModifier:
                self._shift_click(item, scene_pos)
                return True
            hit = self._place_cursor(item, scene_pos)
            if hit is not None:
                self._select_drag = hit
            return True
        self.leave()
        if item is not None:
            # Picked up like any markup — dragged, grouped, box-selected —
            # and opened for typing if it was only clicked (see mouse_release).
            self._pressed_on = (item, QPointF(scene_pos))
            return False
        if self.calc_mode() and view.markup_at(scene_pos) is None:
            frame = view.frame_at(scene_pos)
            if frame is not None:
                self.place_cross(frame, frame.mapFromScene(scene_pos))
        return False

    MOVE_EDGE_PX = 4.0          # SMath's band along the frame that drags the region

    def _on_frame(self, item: CalcItem, scene_pos: QPointF) -> bool:
        point = self._region_point(item, scene_pos)
        frame = item._view.frame_rect() if item._view is not None else QRectF()
        e = self.MOVE_EDGE_PX
        if item.region is not None and item.region.plot is not None:
            return False
        return (point.x() < e or point.y() < e or point.x() > frame.width() - e
                or point.y() > frame.height() - e)

    # -- a plot that has been double-clicked into (SMath's behaviour) -------------
    #
    # Until then a plot is a markup like any other: the wheel scrolls the page
    # and dragging moves it. Double-clicked into (or just made), dragging inside
    # it pans the graph — or zooms it, with the Maths panel's Scale tool — its
    # corner resizes it, and the wheel zooms it (Ctrl: x only, Shift: y only),
    # until a click outside or Esc. WebSMath's worksheet_view, one to one.
    def _in_plot(self, item, scene_pos: QPointF) -> bool:
        view = getattr(item, "_view", None)
        return bool(item is not None and item.region is not None
                    and item.region.plot is not None and view is not None
                    and view.plot_rect().contains(self._region_point(item, scene_pos)))

    def _start_plot_drag(self, item, scene_pos: QPointF) -> bool:
        if not self._in_plot(item, scene_pos):
            return False
        state = item.region.plot
        local = self._region_point(item, scene_pos)
        if local.x() > state.width - 8 and local.y() > state.height - 8:
            self._plot_drag = ("resize", QPointF(scene_pos), item, (state.width, state.height))
        else:
            self._plot_drag = ("pan", QPointF(scene_pos), item,
                               (state.pan_x, state.pan_y, state.ppu_x, state.ppu_y))
        return True

    def _drag_the_plot(self, scene_pos: QPointF) -> None:
        kind, start, item, orig = self._plot_drag
        moved = (scene_pos - start) * PX_PER_PT
        state = item.region.plot
        if kind == "pan" and self.plot_tool == "scale":
            factor = 1.01 ** (moved.x() - moved.y())      # up and right zooms in
            state.ppu_x, state.ppu_y = orig[2] * factor, orig[3] * factor
        elif kind == "pan":
            state.pan_x, state.pan_y = orig[0] + moved.x(), orig[1] + moved.y()
        else:
            state.width = max(60.0, snap_px(orig[0] + moved.x()))
            state.height = max(40.0, snap_px(orig[1] + moved.y()))
        item._view._plot_cache = None
        item.relayout()
        item.update()

    def wheel(self, event, scene_pos: QPointF) -> bool:
        """The wheel over a plot that has been double-clicked into zooms it."""
        item = self.item
        if not self.editing() or not self._in_plot(item, scene_pos):
            return False
        steps = event.angleDelta().y() / 120.0
        if not steps:
            return False
        local = self._region_point(item, scene_pos)
        mods = event.modifiers()
        only_x = bool(mods & Qt.ControlModifier)
        only_y = bool(mods & Qt.ShiftModifier)
        item.region.plot.zoom(1.1 ** steps, local.x(), local.y(), x=not only_y, y=not only_x)
        item._view._plot_cache = None
        item.update()
        event.accept()
        return True

    def mouse_move(self, event, scene_pos: QPointF) -> bool:
        if self._plot_drag is not None:
            self._drag_the_plot(scene_pos)
            return True
        if self._select_drag is None or self.item is None:
            return False
        row, first = self._select_drag
        item = self.item
        hit = item._view.slot_at(self._region_point(item, scene_pos))
        if hit and hit[0] is row and hit[1] != first:
            item.region.editor.set_cursor(row, hit[1])
            item.region.editor.selection = (row, min(first, hit[1]), max(first, hit[1]))
            item.update()
        return True

    def mouse_release(self, event, scene_pos: QPointF) -> bool:
        """After the canvas has had the release: a click (not a drag) on an
        equation puts the cursor in it."""
        if self._plot_drag is not None:
            self._plot_drag = None
            return True
        if self._select_drag is not None:
            self._select_drag = None
            return True
        pressed, self._pressed_on = self._pressed_on, None
        if pressed is None or event.button() != Qt.LeftButton:
            return False
        item, where = pressed
        if item.scene() is None or event.modifiers() & (Qt.ShiftModifier | Qt.ControlModifier):
            return False
        moved = self.view.mapFromScene(scene_pos) - self.view.mapFromScene(where)
        if moved.manhattanLength() >= QApplication.startDragDistance():
            return False
        if not self.view.editable(item):
            return False
        if item.region is not None and item.region.plot is not None:
            return False          # a plot is double-clicked into; one click picks it up
        self.focus(item, scene_pos)
        return True

    def _region_point(self, item: CalcItem, scene_pos: QPointF) -> QPointF:
        local = item.mapFromScene(scene_pos)
        return QPointF(local.x() * PX_PER_PT, local.y() * PX_PER_PT)

    def _place_cursor(self, item: CalcItem, scene_pos: QPointF):
        view = item._view
        if view is None:
            return None
        point = self._region_point(item, scene_pos)
        view.place_cursor(point)
        item.relayout()
        return view.slot_at(point)

    def _shift_click(self, item: CalcItem, scene_pos: QPointF) -> None:
        """Shift+click extends the selection to the click, as in a word processor."""
        editor = item.region.editor
        row, start = editor.row, editor.pos
        hit = item._view.slot_at(self._region_point(item, scene_pos))
        if hit and hit[0] is row and hit[1] != start:
            editor.set_cursor(row, hit[1])
            editor.selection = (row, min(start, hit[1]), max(start, hit[1]))
            item.update()

    # -- keys --------------------------------------------------------------------------
    def key_press(self, event) -> bool:
        """True when the key was the equation's (or started one)."""
        if self.editing():
            return self._key_while_editing(event)
        if self.calc_mode() and self.view.idle_on_canvas():
            return self._key_on_paper(event)
        return False

    def _key_on_paper(self, event) -> bool:
        """Calc mode: typing on the page starts an equation (decision 5)."""
        key, text = event.key(), event.text()
        mods = event.modifiers()
        if mods & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier):
            return False
        if self.view.scene().selectedItems() and key in (
                Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down, Qt.Key_Delete, Qt.Key_Backspace):
            return False                     # nudging or deleting the selection
        if self.cross is not None and key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down,
                                              Qt.Key_Return, Qt.Key_Enter):
            step = {Qt.Key_Left: (-GRID_PT, 0), Qt.Key_Right: (GRID_PT, 0), Qt.Key_Up: (0, -GRID_PT),
                    Qt.Key_Down: (0, GRID_PT), Qt.Key_Return: (0, GRID_PT),
                    Qt.Key_Enter: (0, GRID_PT)}[key]
            frame, point = self.cross
            self.place_cross(frame, QPointF(max(0.0, point.x() + step[0]), max(0.0, point.y() + step[1])))
            return True
        if not text or not text.isprintable() or key == Qt.Key_Space and self.cross is None:
            return False
        frame, point = self._where_typing_starts()
        if frame is None:
            return False
        if text == " ":
            self.place_cross(frame, QPointF(point.x() + GRID_PT, point.y()))
            return True
        # the Calc-mode typing keys are bindings like any other: " for
        # Calculation text and @ for a plot by default
        from .shortcuts import CALC, INSERT
        binding = self.window.shortcuts.match_typed(text, mods, CALC)
        if binding is not None and binding.kind == INSERT:
            self.insert(binding.payload, frame, point)
            return True
        item = self.start(frame, point)
        self._type(item, text)
        return True

    def insert(self, what: str, frame, point: QPointF) -> None:
        """Start an equation, a plot or Calculation text at *point*."""
        if what == "plot":
            self.start_plot(frame, point)
            self._after_edit(self.item)
        elif what == "calc_text":
            self.start_calc_text(frame, point)
        else:
            self.start(frame, point)

    def start_calc_text(self, frame, point: QPointF, text: str = "", replacing=None):
        """New Calculation text at *point*, with the caret in it (in place of
        the equation *replacing*, in the same undo step)."""
        from ..items.calc import CalcTextItem

        self.leave()
        view = self.view
        if view.editing_item() is not None:
            view.end_item_edit()
        view.begin_snapshot([frame])
        if replacing is not None and replacing.scene() is not None:
            frame.remove_markup(replacing)
        item = CalcTextItem(text)
        item.author = self.window.document.settings.default_author or self.window.document.author
        item.set_local_rect(QRectF(0, 0, 180, 4 * GRID_PT))
        frame.add_markup(item, QPointF(snap(point.x()), snap(point.y())))
        view.scene().clearSelection()
        item.setSelected(True)
        view.commit_snapshot("Add Calculation text")
        self.clear_cross()
        view.begin_item_edit(item)
        editor = getattr(item, "_editor", None)
        if editor is not None:
            cursor = editor.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            editor.setTextCursor(cursor)
        return item

    def _where_typing_starts(self):
        if self.cross is not None and self.cross[0].scene() is not None:
            return self.cross
        frame = self.view.typing_frame()
        if frame is None:
            return None, None
        return frame, self.view.typing_position()

    def _key_while_editing(self, event) -> bool:
        item = self.item
        editor = item.region.editor
        key, mods = event.key(), event.modifiers()
        ctrl = bool(mods & Qt.ControlModifier)
        if self.suggestions.isVisible() and self._suggestion_key(key):
            return True
        if key == Qt.Key_Escape:
            self.leave()
            return True
        if ctrl and key in (Qt.Key_Z, Qt.Key_Y):
            # one history: the window takes back the keystrokes first, then
            # the document's own steps (MainWindow.undo_something)
            redo = key == Qt.Key_Y or bool(mods & Qt.ShiftModifier)
            (self.window.redo_something if redo else self.window.undo_something)()
            return True
        if ctrl and key in (Qt.Key_B, Qt.Key_I, Qt.Key_U) and not mods & Qt.AltModifier:
            # MarkForge's formatting keys, reaching the equation (decision 6)
            {Qt.Key_B: self.window.toggle_bold, Qt.Key_I: self.window.toggle_italic,
             Qt.Key_U: self.window.toggle_underline}[key]()
            return True
        if (ctrl or mods & Qt.AltModifier) and self._smath_key(event):
            return True
        if key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Home, Qt.Key_End):
            name = _selection_key_name(key, mods)
            if name is not None:
                if self._block_for_clash(item):
                    return True
                editor.key(name)
                self._after_edit(item)
                return True
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self._enter(bool(mods & Qt.ShiftModifier))
            return True
        if key in (Qt.Key_Tab, Qt.Key_Backtab):
            self._tab(backwards=key == Qt.Key_Backtab or bool(mods & Qt.ShiftModifier))
            return True
        named = {Qt.Key_Left: "LEFT", Qt.Key_Right: "RIGHT", Qt.Key_Up: "UP", Qt.Key_Down: "DOWN",
                 Qt.Key_Home: "HOME", Qt.Key_End: "END", Qt.Key_Backspace: "BACK",
                 Qt.Key_Delete: "DELETE"}.get(key)
        if named:
            self._named_key(named)
            return True
        text = event.text()
        if text and not ctrl and not mods & Qt.AltModifier and text.isprintable():
            self._type(item, text)
            return True
        if ctrl or mods & Qt.AltModifier:
            return self._pass_to_window(event)
        return True                           # every other key belongs to the equation

    def _smath_key(self, event) -> bool:
        """A key from the SMath section of the shortcut manager (decision 6)."""
        from .shortcuts import EQUATION, TYPING
        sequence = QKeySequence(event.keyCombination())
        binding = self.window.shortcuts.binding_for(sequence, scopes=(EQUATION, TYPING))
        if binding is None:
            return False
        if binding.kind == "symbol":
            return self.insert_symbol(binding.payload)
        self.run_smath(binding.payload)
        return True

    def run_smath(self, payload: str) -> None:
        item = self.item
        what, _, arg = payload.partition(":")
        if what == "type" and item is not None:
            self._type(item, arg)
        elif what == "box" and item is not None:
            item.region.editor.insert_structure(arg)
            self._after_edit(item)
        elif what == "command":
            getattr(self.window, arg)()

    # MarkForge's symbol keys, with their meaning in an equation (the answer
    # to the symbol-keys question): what gets typed into the editor.
    SYMBOL_MEANINGS = {
        "×": "*", "÷": "/", "^": "^", "√(": "\\", "²": "^2", "³": "^3", "±": "±",
        "≤": "≤", "≥": "≥", "≠": "≠", "π": "π", "°": "'°", "Δ": "Δ", "Σ": "Σ",
        "⌀": "⌀", "µ": "μ", "φ": "φ", "σ": "σ", "α": "α", "β": "β", "γ": "γ",
        "θ": "θ", "λ": "λ", "ρ": "ρ", "ε": "ε", "ω": "ω",
    }

    def insert_symbol(self, symbol: str) -> bool:
        """A symbol key while an equation has the cursor; False if none has."""
        item = self.item if self.editing() else None
        if item is None:
            return False
        typed = self.SYMBOL_MEANINGS.get(symbol, symbol)
        if symbol in ("²", "³"):
            self._type(item, typed)
            item.region.editor.key("RIGHT")          # out of the exponent again
            self._after_edit(item)
            return True
        self._type(item, typed)
        return True

    def _pass_to_window(self, event) -> bool:
        """A Ctrl key SMath has no use for: the window's own command (save, zoom…)."""
        wanted = QKeySequence(event.keyCombination())
        for action in self.window.findChildren(QAction):
            if action.isEnabled() and any(s.matches(wanted) == QKeySequence.ExactMatch
                                          for s in action.shortcuts()):
                action.trigger()
                return True
        return True

    def _named_key(self, name: str) -> None:
        item = self.item
        if name in ("LEFT", "RIGHT", "UP", "DOWN") and self._block_for_clash(item):
            return
        if name in ("UP", "DOWN") and item.region.kind != "text":
            # Up/Down move to the previous/next region (observed on SMath Cloud)
            self._step_region(-1 if name == "UP" else 1)
            return
        item.region.editor.key(name)
        self._after_edit(item, typed=name in ("BACK", "DELETE"))

    def _type(self, item: CalcItem, text: str) -> None:
        if text and not _word_char(text[0]) and self._block_for_clash(item):
            return                            # m is a variable and a unit: pick one first
        for ch in text:
            item.region.editor.key(ch)
            if item.region.editor.kind == "text" and item.region.plot is None:
                # SMath: a lone word and a space make a text region; here that
                # is Calculation text (decision 22, and the word-space answer)
                self._becomes_calc_text(item)
                return
        self._after_edit(item, typed=True)

    def _becomes_calc_text(self, item: CalcItem) -> None:
        """Turn the equation just typed into Calculation text with the same
        words; one Ctrl+Z (after the typing) turns it back, as in SMath."""
        editor = item.region.editor
        words = editor.text
        editor.undo()                         # the equation as it was: the lone word
        frame, point = item.parentItem(), QPointF(item.pos())
        self.leave()                          # one undo step: the equation
        self.start_calc_text(frame, point, words, replacing=item)

    def _ordered_items(self) -> list:
        sheet = self.item._sheet if self.item is not None else None
        if sheet is None:
            return []
        items = getattr(sheet, "items", {})
        return [items[r.id] for r in sheet.worksheet.ordered() if r.id in items]

    def _step_region(self, step: int) -> None:
        order = self._ordered_items()
        if self.item not in order:
            return
        k = order.index(self.item) + step
        if 0 <= k < len(order):
            self.focus(order[k])

    def _tab(self, backwards: bool = False) -> None:
        """Tab moves to the next region in reading order (observed)."""
        if self._block_for_clash(self.item):
            return
        order = self._ordered_items()
        if not order:
            return
        k = order.index(self.item) if self.item in order else -1
        nxt = order[(k + (-1 if backwards else 1)) % len(order)]
        self.focus(nxt)                       # itself, when it is the only one
        editor = nxt.region.editor
        if nxt.region.kind == "math":
            editor.set_cursor(editor.root, len(editor.expression_items()))
        nxt.relayout()

    def _enter(self, shift: bool) -> None:
        item = self.item
        if self._block_for_clash(item):
            return
        if item.region.kind == "text" and not shift:
            item.region.editor.key("ENTER")
            self._after_edit(item)
            return
        self.leave(cross_below=True)

    def _after_edit(self, item: CalcItem, typed: bool = False) -> None:
        """As SMath Studio desktop: while an equation is being edited its
        result shows the empty box until it is left; plots follow live."""
        region = item.region
        if region.plot is not None:
            if item._sheet.worksheet.auto_calculation:
                item._sheet.worksheet.calculate_region(region)
        else:
            region.pending = True
        item.relayout()
        self.view.documentEdited.emit()
        # scroll first: the list is placed on the screen, so it goes where
        # the equation is once the view has moved to keep it in sight
        self.view.follow_off_screen(item.sceneBoundingRect())
        if typed and region.kind == "math":
            self.update_suggestions(item)
        else:
            self.hide_suggestions()

    def undo(self) -> bool:
        """Ctrl+Z inside an equation takes back the last keystroke first."""
        item = self.item
        if item is not None and item.region.editor.undo():
            self._after_edit(item)
            return True
        return False

    def redo(self) -> bool:
        item = self.item
        if item is not None and item.region.editor.redo():
            self._after_edit(item)
            return True
        return False

    # -- autocomplete ------------------------------------------------------------------
    def update_suggestions(self, item: CalcItem, force: bool = False) -> None:
        if not self.dynamic_assistance and not force:
            return
        editor = item.region.editor
        start, word = editor.current_word()
        if not word or word[0].isdigit() or word[0] == ".":
            self.hide_suggestions()
            return
        if editor.in_unit:
            entries = unit_box_entries(word)
        else:
            ctx = item._sheet.worksheet._context_before(item.region)
            entries = suggestion_entries(word, ctx.names(), ctx.function_arities())
        if not entries:
            self.hide_suggestions()
            return
        clash = self._clash(item)
        if clash is not None:
            for e in entries:
                if e.text == clash and e.origin == 3 and e.kind == "operand":
                    e.description = f"<strong>{clash}</strong> - variable defined on this worksheet"
        s = self.suggestions
        s.start = start
        s.word = word
        s.fill(entries, selected_index(entries, word))
        self._place_suggestions(item)
        rows = min(s.count(), 8)
        s.setMaximumHeight(16 * 8 + 4)
        s.resize(max(90, s.sizeHintForColumn(0) + 22), s.sizeHintForRow(0) * rows + 4)
        s.show()
        s.show_tooltip()

    def _follow_the_view(self) -> None:
        if self.suggestions.isVisible() and self.item is not None:
            self._place_suggestions(self.item)

    def _place_suggestions(self, item: CalcItem) -> None:
        view_point = self.view.mapFromScene(self._cursor_scene_pos(item))
        self.suggestions.move(self.view.viewport().mapToGlobal(view_point) + QPoint(-2, 1))

    def _cursor_scene_pos(self, item: CalcItem) -> QPointF:
        # WebSMath's drawing puts itself at the region's worksheet position
        # (setPos(region.x, region.y)), which in CalcForge has the page folded
        # into y; the page item places it, so only the cursor's place inside
        # the region counts here — otherwise the list lands that far away.
        view = item._view
        at = view.cursor_scene_pos() - view.pos()      # region pixels, from its corner
        return item.mapToScene(QPointF(at.x() * PT_PER_PX, at.y() * PT_PER_PX))

    def hide_suggestions(self) -> None:
        self.suggestions.hide()

    def _suggestion_key(self, key) -> bool:
        """Keys the open list takes: Esc closes it, Tab applies the selected
        entry, Enter only once the list has been moved through, Up/Down move."""
        s = self.suggestions
        if key == Qt.Key_Escape or s.count() < 1:
            self.hide_suggestions()
            return key == Qt.Key_Escape
        if key == Qt.Key_Tab or (key in (Qt.Key_Return, Qt.Key_Enter) and s.activated):
            it = s.currentItem()
            if it is not None and s.currentRow() >= 0:
                self._apply_suggestion(it)
            return True
        if key in (Qt.Key_Down, Qt.Key_Up):
            row = s.currentRow()
            if row < 0:
                row = 0 if key == Qt.Key_Down else s.count() - 1
            else:
                row = max(0, min(s.count() - 1, row + (1 if key == Qt.Key_Down else -1)))
            s.activated = True
            s.setCurrentRow(row)
            return True
        return False

    def _apply_suggestion(self, it) -> None:
        item = self.item
        if item is None:
            return
        editor = item.region.editor
        e = it.data(Qt.UserRole)
        name = e.name.split(" ")[0]              # "sum (4)" inserts sum(
        if e.kind == "unit":
            back = {v: k for k, v in SMATH_LABEL.items()}
            name = "'" + back.get(name[1:], name[1:])
        elif e.origin == 3 and e.kind == "operand":
            editor.confirmed_words.add(name)     # the variable, over a unit of that name
        start, _ = editor.current_word()
        if e.kind == "function" and name in editor.STRUCTURE_WORDS:
            editor.replace_word(start, name)
            editor.key("(")
        else:
            editor.replace_word(start, name, call=(e.kind == "function" and name not in KEYWORDS))
        self.hide_suggestions()
        self._after_edit(item)

    # -- a name that is both a variable and a unit ---------------------------------
    def _clash(self, item: Optional[CalcItem]) -> Optional[str]:
        """The name at the cursor when it is both a worksheet variable and a
        unit (m:10 above, then m typed) and it has not been said which is meant."""
        if item is None or item.region is None or item.region.kind != "math":
            return None
        editor = item.region.editor
        if editor.in_unit:
            return None
        _, word = editor.current_word()
        if not word or word[0] in "'.0123456789" or word in editor.confirmed_words:
            return None
        if not is_unit(word):
            return None
        ctx = item._sheet.worksheet._context_before(item.region)
        if word not in ctx.names():
            return None
        return word

    def _block_for_clash(self, item: Optional[CalcItem]) -> bool:
        """A name that is both a worksheet variable and a unit (m:10 above,
        then m typed): the variable is meant — it was defined here — and the
        typing carries on. (WebSMath, after SMath Cloud, blocked every key
        until one was chosen from the list, so = and : could not be typed.)
        The unit is still one keystroke away: 'm."""
        word = self._clash(item)
        if word is None:
            return False
        item.region.editor.confirmed_words.add(word)
        self.view.statusMessage.emit(
            f"'{word}' is taken as your variable — for the unit, type '{word}")
        return False


# -- WebSMath's commands on the selected part of an equation ---------------------------------
#
# Its Calculation menu (Solve, Calculate, Invert, Determinant), its Insert >
# Operator list, and copying and pasting part of an equation — ported from its
# worksheet_view.py and mainwindow.py (phase 6, with its window's tests).

# Insert > Operator: WebSMath's list, by group.
OPERATORS = [
    ("Arithmetic", "+", "Addition", "+"), ("Arithmetic", "−", "Subtraction", "-"),
    ("Arithmetic", "·", "Multiplication", "*"), ("Arithmetic", "/", "Division", "/"),
    ("Arithmetic", "xʸ", "Power", "^"), ("Arithmetic", "√", "Square root", "\\"),
    ("Arithmetic", "ⁿ√", "N-th root", ("struct", "nthroot")), ("Arithmetic", "!", "Factorial", "!"),
    ("Arithmetic", "±", "Plus/minus", "±"), ("Arithmetic", "|x|", "Absolute value", "abs("),
    ("Definitions", "≔", "Definition", ":"), ("Definitions", "=", "Numeric evaluation", "="),
    ("Boolean", "=", "Boolean equality", "≡"), ("Boolean", "<", "Less than", "<"),
    ("Boolean", ">", "Greater than", ">"), ("Boolean", "≤", "Less than or equal", "≤"),
    ("Boolean", "≥", "Greater than or equal", "≥"), ("Boolean", "≠", "Not equal", "≠"),
    ("Boolean", "¬", "Not", "¬"), ("Boolean", "∧", "And", "&"), ("Boolean", "∨", "Or", "|"),
    ("Boolean", "⊕", "Exclusive or", "⊕"),
    ("Matrix and vector", "vᵢ", "Element", "["), ("Matrix and vector", "a..b", "Range", ("struct", "range")),
    ("Matrix and vector", "×", "Cross product", "†"), ("Matrix and vector", "Mᵀ", "Transpose", "transpose("),
    ("Matrix and vector", "|M|", "Determinant", "det("),
    ("Calculus", "Σ", "Summation", ("struct", "sum")), ("Calculus", "Π", "Product", ("struct", "product")),
    ("Calculus", "∫", "Definite integral", ("struct", "int")), ("Calculus", "d/dx", "Derivative", ("struct", "diff")),
]


def _selection_or_operand(calc):
    item = calc.item
    if not calc.editing() or item.region is None or item.region.kind != "math":
        return None, None
    ed = item.region.editor
    if ed.selection is None:
        r, a, b = ed.underline()
        if a == b:
            return item, None
        ed.selection = (r, a, b)
    return item, ed.selection


def invert_selection(calc) -> None:
    """Invert: the selection becomes (selection)^-1."""
    item, sel = _selection_or_operand(calc)
    if sel is None:
        return
    ed = item.region.editor
    ed._push_undo()
    ed._apply_to_selection("^")
    ed.type("-1")
    calc._after_edit(item)


def determinant_selection(calc) -> None:
    """Determinant: the selection becomes det(selection), drawn |M|."""
    from ..calc.engine.model import Paren, Row

    item, sel = _selection_or_operand(calc)
    if sel is None:
        return
    ed = item.region.editor
    ed._push_undo()
    r, a, b = sel
    inner = Row(r.items[a:b])
    del r.items[a:b]
    for k, ch in enumerate("det"):
        r.insert(a + k, ch)
    r.insert(a + 3, Paren(inner))
    ed._fix_parents(ed.root)
    ed.selection = None
    ed.set_cursor(r, a + 4)
    calc._after_edit(item)


def calculate_selection(calc) -> None:
    """Calculate: replace the selected part by its value."""
    from ..calc.docsheet import sheet_for
    from ..calc.engine.display import display_text, display_value, unit_text
    from ..calc.engine.errors import SMathError
    from ..calc.engine.model import Row
    from ..calc.engine.parser import ParseError, parse_row
    from ..calc.ui.suggest import _linear_unit

    item, sel = _selection_or_operand(calc)
    if sel is None:
        return
    worksheet = sheet_for(calc.window.document).worksheet
    r, a, b = sel
    part = Row()
    part.items = list(r.items[a:b])
    try:
        value = worksheet.evaluator.eval(parse_row(part), worksheet._context_before(item.region))
    except (SMathError, ParseError):
        item.region.editor.selection = None
        return
    d = display_value(value, worksheet.format)
    number = display_text(d).split(" ")[0].replace("·10^", "*10^")
    unit = unit_text(getattr(d, "unit", None))
    ed = item.region.editor
    ed._push_undo()
    del r.items[a:b]
    ed.set_cursor(r, a)
    ed.type(number + (("'" + _linear_unit(unit)) if unit else ""))
    calc._after_edit(item)


def _variable_and_part(calc):
    """(item, variable name, row, start, end) for Solve: the variable is the
    name the cursor is on; the expression is the selection, or else the whole
    expression (the right side of a definition, the part before "=")."""
    item = calc.item
    if not calc.editing() or item.region is None or item.region.kind != "math":
        return None
    ed = item.region.editor
    a, b = ed.token_span(ed.row, ed.pos)
    word = "".join(x for x in ed.row.items[a:b] if isinstance(x, str))
    if not word or not (word[0].isalpha()) or word.startswith("'"):
        calc.window.status_hint.setText(
            "Put the cursor on the variable first (e.g. on x in x^2+1).")
        return None
    if ed.selection is not None:
        row, s0, s1 = ed.selection
    else:
        row = ed.root
        items = row.items
        n = len(ed.expression_items())
        s0 = items.index("≔") + 1 if "≔" in items[:n] else 0
        s1 = n
    return item, word, row, s0, s1


def solve_selection(calc) -> None:
    """Solve for the variable under the cursor; the roots appear in a new
    equation below (SMath: Calculation > Solve)."""
    from ..calc.astitems import ast_to_items
    from ..calc.engine import ast as A
    from ..calc.engine.model import Row
    from ..calc.engine.parser import ParseError, parse_row

    got = _variable_and_part(calc)
    if got is None:
        return
    item, var, row, a, b = got
    part = Row()
    part.items = list(row.items[a:b])
    try:
        node = parse_row(part)
    except ParseError:
        calc.window.status_hint.setText("Syntax is incorrect.")
        return
    call = A.Call("solve", [node, A.Var(var)])
    frame = item.parentItem()
    below = QPointF(item.pos().x(), item.pos().y() + item.local_rect().height() + GRID_PT)
    new = calc.start(frame, below)
    ed = new.region.editor
    ed.root.items = ast_to_items(call) + ["="]
    type(ed)._fix_parents(ed.root)
    ed.evaluate = True
    ed.set_cursor(ed.root, len(ed.root.items) - 1)
    calc._after_edit(new)
    calc.leave()                          # the roots show straight away, as in SMath


def insert_operator(calc, how) -> None:
    """One of Insert > Operator's entries, into the equation."""
    window = calc.window
    if isinstance(how, (tuple, list)):
        window.insert_program(how[1])
    elif how:
        window.maths_type(how)


def clipboard(calc, action: str) -> bool:
    """Copy, cut or paste part of the equation being typed (WebSMath's
    copy/paste inside an equation). False when there is nothing of the
    equation's to do it to, so the window does its own."""
    from ..calc.engine.model import to_text

    item = calc.item
    if not calc.editing() or item.region is None or item.region.kind != "math":
        return False
    ed = item.region.editor
    board = QApplication.clipboard()
    if action in ("copy", "cut"):
        if not ed.selection:
            return False
        r, a, b = ed.selection
        calc._clip_items = [it.copy() if hasattr(it, "copy") else it for it in r.items[a:b]]
        part = r.__class__()
        part.items = list(r.items[a:b])
        calc._clip_text = to_text(part)
        board.setText(calc._clip_text)
        if action == "cut":
            ed._push_undo()
            ed._apply_to_selection("DELETE")
            calc._after_edit(item)
        return True
    ours = getattr(calc, "_clip_items", None)
    if ours and board.text() == getattr(calc, "_clip_text", None):
        ed._push_undo()
        if ed.selection:                   # pasting replaces the selection
            ed._apply_to_selection("DELETE")
        for it in ours:
            ed.row.insert(ed.pos, it.copy() if hasattr(it, "copy") else it)
            ed.cursor = type(ed.cursor)(ed.row, ed.pos + 1)
        ed._fix_parents(ed.root)
        calc._after_edit(item)
        return True
    text = board.text()
    if text and not text.lstrip().startswith("{"):
        for ch in text:
            if ch != "\n":
                ed.key(ch)
        calc._after_edit(item)
        return True
    return False
