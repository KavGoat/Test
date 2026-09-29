"""The worksheet canvas: grid, red-cross insertion cursor, regions, keyboard.

Behaviour replicated from SMath Cloud:

* the page is a 9px grid; clicking empty space moves the red cross there
  (snapped to the grid) and typing starts a new math region at the cross;
* clicking inside a region focuses it and puts the cursor at the nearest
  position; Enter leaves the region and puts the cross just below it;
* every keystroke recalculates the worksheet (auto calculation), so results
  appear the moment ``=`` is typed and regions below update immediately;
* regions are evaluated in reading order, so dragging one above the
  definition it uses turns it into an error;
* while typing a name an autocomplete list shows matching units, functions,
  constants and variables (substring match, units first);
* double-clicking the result of an evaluation opens its unit for editing.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QPen
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QListWidget, QListWidgetItem

from ..engine.catalog import FUNCTIONS, UNIT_CATALOG
from ..engine.evaluator import BUILTIN_CONSTANTS
from ..worksheet import Region, Worksheet
from .layout import Style
from .region_item import RegionItem

GRID = 9
GRID_COLOR = QColor("#e8e8e8")
CROSS_COLOR = QColor("#ff0000")
KEYWORDS = ["break", "continue"]


def snap(v: float) -> float:
    return round(v / GRID) * GRID


class WorksheetScene(QGraphicsScene):
    def __init__(self, worksheet: Worksheet, parent=None):
        super().__init__(parent)
        self.worksheet = worksheet
        self.cross = QPointF(18, 18)
        self.show_grid = True
        self.setSceneRect(0, 0, 2000, 3000)

    def drawBackground(self, p: QPainter, rect: QRectF) -> None:
        p.fillRect(rect, Qt.white)
        if not self.show_grid:
            return
        p.setPen(QPen(GRID_COLOR, 1))
        x0 = int(rect.left() // GRID) * GRID
        y0 = int(rect.top() // GRID) * GRID
        x = x0
        while x < rect.right():
            p.drawLine(QPointF(x + 0.5, rect.top()), QPointF(x + 0.5, rect.bottom()))
            x += GRID
        y = y0
        while y < rect.bottom():
            p.drawLine(QPointF(rect.left(), y + 0.5), QPointF(rect.right(), y + 0.5))
            y += GRID

    def drawForeground(self, p: QPainter, rect: QRectF) -> None:
        view = self.views()[0] if self.views() else None
        if view is not None and getattr(view, "focused_item", None) is not None:
            return
        c = self.cross
        p.setPen(QPen(CROSS_COLOR, 1))
        p.drawLine(QPointF(c.x() - 4, c.y() + 0.5), QPointF(c.x() + 5, c.y() + 0.5))
        p.drawLine(QPointF(c.x() + 0.5, c.y() - 4), QPointF(c.x() + 0.5, c.y() + 5))


class SuggestionList(QListWidget):
    """SMath's autocomplete list: white, black border, 12px, selected item
    white on #9faab5."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowFlags(Qt.ToolTip)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet(
            "QListWidget{background:#fff;border:1px solid #000;font-size:12px;}"
            "QListWidget::item{padding:2px 2px 2px 17px;color:#000;}"
            "QListWidget::item:selected{color:#fff;background:#9faab5;}")
        self.setMinimumWidth(90)
        self.setMaximumHeight(92)
        self.start = 0

    def entries(self):
        return [self.item(i).data(Qt.UserRole) for i in range(self.count())]


class WorksheetView(QGraphicsView):
    status = Signal(str)
    modified = Signal()

    def __init__(self, worksheet: Optional[Worksheet] = None, parent=None):
        self.worksheet = worksheet or Worksheet()
        self.scene_ = WorksheetScene(self.worksheet)
        super().__init__(self.scene_, parent)
        self.style_ = Style()
        self.items: dict[int, RegionItem] = {}
        self.focused_item: Optional[RegionItem] = None
        self.selected: list[RegionItem] = []
        self._drag = None
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.TextAntialiasing)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.suggestions = SuggestionList(self)
        self.suggestions.hide()
        self.suggestions.itemDoubleClicked.connect(lambda it: self._apply_suggestion(it))
        self.clipboard: list = []
        for r in self.worksheet.regions:
            self._add_item(r)
        self.recalculate()

    # -- region management ---------------------------------------------------------
    def _add_item(self, region: Region) -> RegionItem:
        item = RegionItem(region, self.worksheet, self.style_)
        self.scene_.addItem(item)
        self.items[region.id] = item
        return item

    def new_region(self, x: float, y: float, text_region: bool = False) -> RegionItem:
        region = self.worksheet.add_region(snap(x), snap(y))
        if text_region:
            region.editor._to_text("")
        item = self._add_item(region)
        return item

    def new_plot(self, x: float, y: float) -> RegionItem:
        region = self.worksheet.add_plot(snap(x), snap(y))
        return self._add_item(region)

    def delete_region(self, item: RegionItem) -> None:
        if item is self.focused_item:
            self.focused_item = None
        self.worksheet.remove_region(item.region)
        self.scene_.removeItem(item)
        self.items.pop(item.region.id, None)

    def reload(self) -> None:
        for it in list(self.items.values()):
            self.scene_.removeItem(it)
        self.items.clear()
        self.focused_item = None
        self.selected = []
        for r in self.worksheet.regions:
            self._add_item(r)
        self.recalculate()

    def recalculate(self, force: bool = False) -> None:
        if self.worksheet.auto_calculation or force:
            self.worksheet.calculate()
        for it in self.items.values():
            it.relayout()
        self._grow_scene()
        self.scene_.update()

    def _grow_scene(self) -> None:
        r = self.scene_.itemsBoundingRect()
        w = max(2000, r.right() + 400)
        h = max(3000, r.bottom() + 600)
        self.scene_.setSceneRect(0, 0, w, h)

    # -- focus -------------------------------------------------------------------------
    def focus_item(self, item: Optional[RegionItem]) -> None:
        if self.focused_item is item:
            return
        old = self.focused_item
        if old is not None:
            old.focused = False
            old.editor.selection = None
            # an empty region disappears when it loses focus
            if old.region.kind == "math" and old.editor.root.is_empty() or (
                    old.region.kind == "text" and not old.editor.text.strip()):
                self.delete_region(old)
            else:
                old.relayout()
        self.focused_item = item
        if item is not None:
            item.focused = True
        self.hide_suggestions()
        self.recalculate()

    def clear_selection(self) -> None:
        for it in self.selected:
            it.selected_region = False
            it.update()
        self.selected = []

    # -- mouse -------------------------------------------------------------------------
    def _item_at(self, scene_pt: QPointF) -> Optional[RegionItem]:
        for it in self.items.values():
            if it.frame_rect().contains(it.mapFromScene(scene_pt)):
                return it
        return None

    def mousePressEvent(self, e) -> None:
        pt = self.mapToScene(e.position().toPoint())
        item = self._item_at(pt)
        self.clear_selection()
        if e.button() == Qt.RightButton:
            super().mousePressEvent(e)
            return
        if item is None:
            self.focus_item(None)
            self.scene_.cross = QPointF(snap(pt.x()), snap(pt.y()))
            self._drag = ("rubber", pt)
            self.scene_.update()
            return
        if item is self.focused_item and item.region.plot is not None and item.plot_rect().contains(item.mapFromScene(pt)):
            st = item.region.plot
            local = item.mapFromScene(pt)
            if local.x() > st.width - 8 and local.y() > st.height - 8:
                self._drag = ("resize", pt, item, (st.width, st.height))
            else:
                self._drag = ("pan", pt, item, (st.pan_x, st.pan_y))
            return
        if item is self.focused_item:
            # dragging inside the region being edited selects (as SMath Cloud)
            item.place_cursor(item.mapFromScene(pt))
            item.update()
            hit = item.slot_at(item.mapFromScene(pt)) if item.region.kind == "math" else None
            self._drag = ("select", pt, item, hit) if hit else None
            return
        local = item.mapFromScene(pt)
        if item.region.plot is not None and item.plot_rect().contains(local):
            self.focus_item(item)
            st = item.region.plot
            if local.x() > st.width - 8 and local.y() > st.height - 8:
                self._drag = ("resize", pt, item, (st.width, st.height))
            else:
                self._drag = ("pan", pt, item, (st.pan_x, st.pan_y))
            return
        self.focus_item(item)
        item.place_cursor(local)
        item.update()
        self._drag = ("maybe-move", pt, item, item.pos())

    def mouseMoveEvent(self, e) -> None:
        if not self._drag:
            return
        pt = self.mapToScene(e.position().toPoint())
        if self._drag[0] == "maybe-move":
            _, start, item, orig = self._drag
            if (pt - start).manhattanLength() > 6 and e.buttons() & Qt.LeftButton:
                self._drag = ("move", start, item, orig)
        if self._drag[0] in ("pan", "resize"):
            kind, start, item, orig = self._drag
            d = pt - start
            st = item.region.plot
            if kind == "pan":
                st.pan_x, st.pan_y = orig[0] + d.x(), orig[1] + d.y()
            else:
                st.width = max(60.0, snap(orig[0] + d.x()))
                st.height = max(40.0, snap(orig[1] + d.y()))
                item.relayout()
            item.update()
            return
        if self._drag[0] == "select":
            _, start, item, (row, k0) = self._drag
            hit = item.slot_at(item.mapFromScene(pt))
            if hit and hit[0] is row and hit[1] != k0:
                item.editor.set_cursor(row, hit[1])
                item.editor.selection = (row, min(k0, hit[1]), max(k0, hit[1]))
                item.update()
            return
        if self._drag[0] == "move":
            _, start, item, orig = self._drag
            d = pt - start
            item.setPos(snap(orig.x() + d.x()), snap(orig.y() + d.y()))
        elif self._drag[0] == "rubber":
            start = self._drag[1]
            rect = QRectF(start, pt).normalized()
            self.clear_selection()
            for it in self.items.values():
                if rect.intersects(it.mapRectToScene(it.frame_rect())):
                    it.selected_region = True
                    it.update()
                    self.selected.append(it)

    def wheelEvent(self, e) -> None:
        """Wheel over a plot zooms it (Ctrl: x only, Shift: y only)."""
        pt = self.mapToScene(e.position().toPoint())
        item = self._item_at(pt)
        if item is not None and item.region.plot is not None:
            local = item.mapFromScene(pt)
            if item.plot_rect().contains(local):
                steps = e.angleDelta().y() / 120.0
                mods = e.modifiers()
                only_x = bool(mods & Qt.ControlModifier)
                only_y = bool(mods & Qt.ShiftModifier)
                item.region.plot.zoom(1.1 ** steps, local.x(), local.y(), x=not only_y, y=not only_x)
                item.update()
                e.accept()
                return
        super().wheelEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        if self._drag and self._drag[0] == "move":
            item = self._drag[2]
            item.region.x, item.region.y = item.pos().x(), item.pos().y()
            self.recalculate()
            self.modified.emit()
        self._drag = None

    def mouseDoubleClickEvent(self, e) -> None:
        pt = self.mapToScene(e.position().toPoint())
        item = self._item_at(pt)
        if item is None or item.region.kind != "math":
            return
        local = item.mapFromScene(pt)
        if item.result_unit_hit(local):
            # double-click on the answer: edit its unit (the whole unit selected)
            ed = item.editor
            if ed.unit.is_empty() and item.region.display is not None:
                from ..engine.display import unit_text

                u = unit_text(getattr(item.region.display, "unit", None))
                if u:
                    ed.set_cursor(ed.unit, 0)
                    ed.type("'" + _linear_unit(u))
            ed.set_cursor(ed.unit, len(ed.unit))
            if len(ed.unit):
                ed.selection = (ed.unit, 0, len(ed.unit))
            self.recalculate()

    # -- keyboard ----------------------------------------------------------------------
    def focusNextPrevChild(self, next: bool) -> bool:
        return False  # keep Tab for moving between regions

    def keyPressEvent(self, e: QKeyEvent) -> None:
        key = e.key()
        mods = e.modifiers()
        ctrl = bool(mods & Qt.ControlModifier)
        if self.suggestions.isVisible() and self._suggestion_key(key):
            return
        if ctrl and key in (Qt.Key_Z, Qt.Key_Y):
            self.undo() if key == Qt.Key_Z else self.redo()
            return
        if ctrl and key == Qt.Key_Equal:
            self._key_to_region("≡")
            return
        if ctrl and key in (Qt.Key_3, Qt.Key_9, Qt.Key_0):
            self._key_to_region({Qt.Key_3: "≠", Qt.Key_9: "≤", Qt.Key_0: "≥"}[key])
            return
        if key == Qt.Key_Delete and self.selected and self.focused_item is None:
            for it in list(self.selected):
                self.delete_region(it)
            self.selected = []
            self.recalculate()
            return
        named = {
            Qt.Key_Left: "LEFT", Qt.Key_Right: "RIGHT", Qt.Key_Up: "UP", Qt.Key_Down: "DOWN",
            Qt.Key_Home: "HOME", Qt.Key_End: "END", Qt.Key_Backspace: "BACK",
            Qt.Key_Delete: "DELETE",
        }.get(key)
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self._enter(shift=bool(mods & Qt.ShiftModifier))
            return
        if key in (Qt.Key_Tab, Qt.Key_Backtab):
            self._tab(backwards=key == Qt.Key_Backtab)
            return
        if key == Qt.Key_Escape:
            self.hide_suggestions()
            return
        if named:
            self._named_key(named)
            return
        text = e.text()
        if text and (ctrl is False) and text.isprintable():
            self._key_to_region(text)
            return
        super().keyPressEvent(e)

    def _named_key(self, k: str) -> None:
        item = self.focused_item
        if item is None:
            step = {"LEFT": (-GRID, 0), "RIGHT": (GRID, 0), "UP": (0, -GRID), "DOWN": (0, GRID),
                    "BACK": (0, -GRID)}.get(k)
            if step:
                c = self.scene_.cross
                self.scene_.cross = QPointF(max(0, c.x() + step[0]), max(0, c.y() + step[1]))
                self.scene_.update()
            return
        item.editor.key(k)
        self._after_edit(item, typed=k in ("BACK", "DELETE"))

    def _key_to_region(self, text: str) -> None:
        item = self.focused_item
        if item is None and text == "@":
            # "@" inserts a 2-D plot, as in SMath
            c = self.scene_.cross
            item = self.new_plot(c.x(), c.y())
            self.focus_item(item)
            return
        if item is None:
            c = self.scene_.cross
            if text == " ":
                self.scene_.cross = QPointF(c.x() + GRID, c.y())
                self.scene_.update()
                return
            item = self.new_region(c.x(), c.y())
            self.focus_item(item)
        for ch in text:
            item.editor.key(ch)
        self._after_edit(item, typed=True)

    def _tab(self, backwards: bool = False) -> None:
        """Tab moves focus to the next region in reading order (observed)."""
        order = [self.items[r.id] for r in self.worksheet.ordered() if r.id in self.items]
        if not order:
            return
        cur = self.focused_item
        k = order.index(cur) if cur in order else -1
        nxt = order[(k + (-1 if backwards else 1)) % len(order)]
        self.focus_item(nxt)
        if nxt.region.kind == "math":
            nxt.editor.set_cursor(nxt.editor.root, len(nxt.editor.expression_items()))
        nxt.update()

    def _enter(self, shift: bool) -> None:
        item = self.focused_item
        if item is None:
            c = self.scene_.cross
            self.scene_.cross = QPointF(c.x(), c.y() + GRID)
            self.scene_.update()
            return
        if item.region.kind == "text" and not shift:
            item.editor.key("ENTER")
            self._after_edit(item)
            return
        r = item.mapRectToScene(item.frame_rect())
        self.focus_item(None)
        self.scene_.cross = QPointF(snap(r.left()), snap(r.bottom() + 5))
        self.recalculate()

    def _after_edit(self, item: RegionItem, typed: bool = False) -> None:
        # only the region being edited follows the keystrokes; the rest of the
        # worksheet is recalculated when the region is left (as SMath Cloud)
        if self.worksheet.auto_calculation:
            self.worksheet.calculate_region(item.region)
        item.relayout()
        self._grow_scene()
        self.modified.emit()
        if typed and item.region.kind == "math":
            self.update_suggestions(item)
        else:
            self.hide_suggestions()
        self.ensureVisible(item.mapRectToScene(item.frame_rect()), 20, 20)

    def undo(self) -> None:
        item = self.focused_item
        if item is not None and item.editor.undo():
            item.relayout()
            self.recalculate()

    def redo(self) -> None:
        item = self.focused_item
        if item is not None and item.editor.redo():
            self.recalculate()

    # -- autocomplete ---------------------------------------------------------------------
    def candidates(self, word: str, region: Region) -> list:
        """Substring, case-insensitive; units (with ') first, each group
        alphabetical ignoring case - as SMath Cloud lists them."""
        w = word.lower()
        unit_mode = w.startswith("'")
        needle = w[1:] if unit_mode else w
        units = [("'" + u, "unit") for u in UNIT_CATALOG if needle in u.lower()]
        units.sort(key=lambda x: x[0].lower())
        others = []
        seen = set()
        for name, nargs, cat, desc in FUNCTIONS:
            label = name if sum(1 for f in FUNCTIONS if f[0] == name) == 1 else f"{name} ({nargs})"
            if needle in name.lower() and label not in seen:
                seen.add(label)
                others.append((label, "function"))
        for c in list(BUILTIN_CONSTANTS) + KEYWORDS:
            if needle in c.lower():
                others.append((c, "constant"))
        ctx = self.worksheet._context_before(region)
        for n in sorted(ctx.names()):
            if needle in n.lower() and n not in seen and n != word:
                others.append((n, "variable"))
        others.sort(key=lambda x: x[0].lower())
        return units + others

    def update_suggestions(self, item: RegionItem) -> None:
        start, word = item.editor.current_word()
        if not word or word[0].isdigit():
            self.hide_suggestions()
            return
        cands = self.candidates(word, item.region)
        if not cands:
            self.hide_suggestions()
            return
        s = self.suggestions
        s.clear()
        for label, kind in cands:
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, (label, kind))
            s.addItem(it)
        s.start = start
        pos = self.mapFromScene(item.cursor_scene_pos())
        s.move(self.mapToGlobal(pos))
        s.resize(max(90, s.sizeHintForColumn(0) + 24), min(92, s.sizeHintForRow(0) * s.count() + 4))
        s.setCurrentRow(-1)
        s.show()

    def hide_suggestions(self) -> None:
        self.suggestions.hide()

    def _suggestion_key(self, key) -> bool:
        s = self.suggestions
        if key in (Qt.Key_Down, Qt.Key_Up):
            row = s.currentRow() + (1 if key == Qt.Key_Down else -1)
            s.setCurrentRow(max(0, min(s.count() - 1, row)))
            return True
        if key in (Qt.Key_Tab,) or (key in (Qt.Key_Return, Qt.Key_Enter) and s.currentRow() >= 0):
            it = s.currentItem() or s.item(0)
            if it is not None:
                self._apply_suggestion(it)
            return True
        if key == Qt.Key_Escape:
            self.hide_suggestions()
            return True
        return False

    def _apply_suggestion(self, it: QListWidgetItem) -> None:
        item = self.focused_item
        if item is None:
            return
        label, kind = it.data(Qt.UserRole)
        name = label.split(" (")[0]
        start, _ = item.editor.current_word()
        item.editor.replace_word(start, name, call=(kind == "function" and name not in KEYWORDS))
        self.hide_suggestions()
        self.recalculate()

    # -- clipboard / region commands ----------------------------------------------------------
    def select_all(self) -> None:
        self.focus_item(None)
        self.clear_selection()
        for it in self.items.values():
            it.selected_region = True
            it.update()
            self.selected.append(it)


def _linear_unit(u: str) -> str:
    """kg·m/s^2 -> kg*'m/'s^2 (typed form for the unit placeholder)."""
    out = u.replace("·", "*'").replace("/", "/'")
    return out
