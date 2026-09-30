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
    going_ids = {item.region.id for item in going if getattr(item, "region", None) is not None}
    lost, kept = set(), set()
    for region in sheet.worksheet.regions:
        names = set(region.defined_vars) | {name for name, _ in region.defined_funcs}
        (lost if region.id in going_ids else kept).update(names)
    return sorted(lost - kept)


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
        self.dynamic_assistance = True
        self._select_drag = None                    # (row, first slot) while dragging a selection
        self._overflow: list = []                   # equations past the bottom of their page
        self._pressed_on: Optional[tuple] = None    # (item, scene point) of a click on an equation

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
        region.font_size = getattr(self, "default_font_size", 10.0)
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

    # -- mouse -----------------------------------------------------------------------
    def calc_item_at(self, scene_pos: QPointF) -> Optional[CalcItem]:
        for item in self.view.scene().items(scene_pos):
            if isinstance(item, CalcItem) and item.local_rect().contains(item.mapFromScene(scene_pos)):
                return item
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

    def mouse_move(self, event, scene_pos: QPointF) -> bool:
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
        if text == "@":
            self.start_plot(frame, point)
            self._after_edit(self.item)
            return True
        item = self.start(frame, point)
        self._type(item, text)
        return True

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
        if ctrl and key == Qt.Key_Equal:
            self._type(item, "≡")
            return True
        if ctrl and key in (Qt.Key_3, Qt.Key_9, Qt.Key_0):
            self._type(item, {Qt.Key_3: "≠", Qt.Key_9: "≤", Qt.Key_0: "≥"}[key])
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
        self._after_edit(item, typed=True)

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
        if typed and region.kind == "math":
            self.update_suggestions(item)
        else:
            self.hide_suggestions()
        self.view.follow_off_screen(item.sceneBoundingRect())

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
        view_point = self.view.mapFromScene(self._cursor_scene_pos(item))
        s.move(self.view.viewport().mapToGlobal(view_point) + QPoint(-2, 1))
        rows = min(s.count(), 8)
        s.setMaximumHeight(16 * 8 + 4)
        s.resize(max(90, s.sizeHintForColumn(0) + 22), s.sizeHintForRow(0) * rows + 4)
        s.show()
        s.show_tooltip()

    def _cursor_scene_pos(self, item: CalcItem) -> QPointF:
        at = item._view.cursor_scene_pos()      # off the scene: region pixels
        return item.mapToScene(QPointF(at.x() * PT_PER_PX, at.y() * PT_PER_PX))

    def hide_suggestions(self) -> None:
        self.suggestions.hide()

    def _suggestion_key(self, key) -> bool:
        """Keys the open list takes: Esc closes it, Tab applies the selected
        entry, Enter only once the list has been moved through, Up/Down move."""
        s = self.suggestions
        if key == Qt.Key_Escape or s.count() < 1:
            if self._clash(self.item) and key != Qt.Key_Escape:
                return True
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
        word = self._clash(item)
        if word is None:
            return False
        if not self.suggestions.isVisible():
            self.update_suggestions(item, force=True)
        QApplication.beep()
        self.view.statusMessage.emit(
            f"'{word}' is both a variable and a unit - choose which one from the list "
            "(Up/Down, then Tab or Enter).")
        return True
