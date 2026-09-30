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

import dataclasses
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QKeyEvent, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QGraphicsItem, QGraphicsScene, QGraphicsView, QLabel, QListWidget,
                               QListWidgetItem, QMenu)

from ..engine.catalog import FUNCTIONS, UNIT_CATALOG
from ..engine.evaluator import BUILTIN_CONSTANTS
from ..engine.units import is_unit
from ..worksheet import Region, Worksheet
from .layout import Style
from .region_item import RegionItem

GRID = 9
GRID_COLOR = QColor("#e8e8e8")
CROSS_COLOR = QColor("#ff0000")
KEYWORDS = ["break", "continue"]


def _word_char(ch: str) -> bool:
    return ch.isalnum() or ch in "._"


def snap(v: float) -> float:
    return round(v / GRID) * GRID


# Desktop SMath's Pages view (checked against screenshots of SMath Studio
# 0.99/1.x): A4 sheets (827 x 1169 hundredths of an inch = 794 x 1123 px at
# 96 dpi) with a 1 px #808080 border, stacked with a 20 px gap on a light
# blue-grey desk (#e7e9f0).  Each sheet has 39/100 in (37 px) margins; the
# printable area inside them has a faint #ebebeb frame and holds the grid,
# the margins stay plain white.  Worksheet coordinates run continuously
# through the printable areas: page k shows worksheet y from k*CONTENT_H to
# (k+1)*CONTENT_H, so on screen a region sits below its page's top margin.
# What lies right of the printable width is drawn on the desk (no page).
PAGE_W = 794.0
PAGE_H = 1123.0
PAGE_MARGIN = 37.0
PAGE_GAP = 20.0
PAGE_STEP = PAGE_H + PAGE_GAP
CONTENT_W = PAGE_W - 2 * PAGE_MARGIN  # 720
CONTENT_H = PAGE_H - 2 * PAGE_MARGIN  # 1049
DESK = QColor("#e7e9f0")
PAGE_BORDER = QColor("#808080")
PRINTABLE_BORDER = QColor("#ebebeb")
DESK_PAD = 10.0  # desk shown left of and above the first page


class WorksheetScene(QGraphicsScene):
    def __init__(self, worksheet: Worksheet, parent=None):
        super().__init__(parent)
        self.worksheet = worksheet
        self.cross = QPointF(18, 18)
        self.show_grid = True
        self.page_mode = "pages"  # "pages", "bounds" (printing bounds) or "none"
        self.printing = False
        self.rubber: Optional[QRectF] = None  # the selection box being dragged
        self.setSceneRect(0, 0, PAGE_W + 40, PAGE_H * 3)

    # -- worksheet <-> scene coordinates ----------------------------------------------
    def to_scene(self, x: float, y: float) -> QPointF:
        """Where worksheet point (x, y) is drawn."""
        if self.page_mode != "pages":
            return QPointF(x, y)
        k = max(0, int(y // CONTENT_H))
        return QPointF(x + PAGE_MARGIN, y - k * CONTENT_H + k * PAGE_STEP + PAGE_MARGIN)

    def to_sheet(self, pt: QPointF) -> QPointF:
        """The worksheet point under scene point pt (margins and gaps belong
        to the nearest printable area)."""
        if self.page_mode != "pages":
            return QPointF(pt)
        k = max(0, int(pt.y() // PAGE_STEP))
        if pt.y() >= k * PAGE_STEP + PAGE_H:
            k += 1  # the gap below a page leads into the next one
        local = min(max(pt.y() - k * PAGE_STEP - PAGE_MARGIN, 0.0), CONTENT_H - 0.01)
        return QPointF(pt.x() - PAGE_MARGIN, k * CONTENT_H + local)

    def page_count(self) -> int:
        from .region_item import RegionItem

        bottom = max((it.region.y + it.frame_rect().height() for it in self.items() if isinstance(it, RegionItem)),
                     default=0.0)
        return max(1, int(bottom // CONTENT_H) + 1)

    def drawBackground(self, p: QPainter, rect: QRectF) -> None:
        if self.printing or self.page_mode == "none":
            p.fillRect(rect, Qt.white)
            if self.show_grid and not self.printing:
                self._grid(p, rect)
            return
        if self.page_mode == "bounds":
            p.fillRect(rect, Qt.white)
            if self.show_grid:
                self._grid(p, rect)
            # printing bounds: dashed lines where pages end
            pen = QPen(QColor("#808080"), 1, Qt.DashLine)
            p.setPen(pen)
            p.drawLine(QPointF(CONTENT_W + 0.5, rect.top()), QPointF(CONTENT_W + 0.5, rect.bottom()))
            k = max(0, int(rect.top() // CONTENT_H))
            while k * CONTENT_H <= rect.bottom():
                if k > 0:
                    p.drawLine(QPointF(rect.left(), k * CONTENT_H + 0.5), QPointF(rect.right(), k * CONTENT_H + 0.5))
                k += 1
            return
        # pages view
        p.fillRect(rect, DESK)
        k = max(0, int(rect.top() // PAGE_STEP))
        while k * PAGE_STEP <= rect.bottom():
            page = QRectF(0, k * PAGE_STEP, PAGE_W, PAGE_H)
            k += 1
            if not page.intersects(rect):
                continue
            p.fillRect(page, Qt.white)
            area = page.adjusted(PAGE_MARGIN, PAGE_MARGIN, -PAGE_MARGIN, -PAGE_MARGIN)
            if self.show_grid:
                # grid lines at worksheet multiples of GRID: the page's first
                # worksheet row is (k-1)*CONTENT_H
                off = ((k - 1) * CONTENT_H) % GRID
                self._grid(p, area.intersected(rect), QPointF(area.left(), area.top() - off))
            p.setPen(QPen(PRINTABLE_BORDER, 1))
            p.drawRect(area.adjusted(-0.5, -0.5, 0.5, 0.5))
            p.setPen(QPen(PAGE_BORDER, 1))
            p.drawRect(page.adjusted(-0.5, -0.5, 0.5, 0.5))

    _grid_brush = None

    def _grid(self, p: QPainter, rect: QRectF, origin: QPointF = QPointF(0, 0)) -> None:
        """The 9 px grid, filled from one tile (much faster than lines)."""
        if WorksheetScene._grid_brush is None:
            from PySide6.QtGui import QBrush, QPixmap

            tile = QPixmap(GRID, GRID)
            tile.fill(Qt.white)
            tp = QPainter(tile)
            tp.setPen(QPen(GRID_COLOR, 1))
            tp.drawLine(0, 0, GRID - 1, 0)
            tp.drawLine(0, 0, 0, GRID - 1)
            tp.end()
            WorksheetScene._grid_brush = QBrush(tile)
        if rect.isEmpty():
            return
        p.save()
        p.setBrushOrigin(origin)
        p.fillRect(rect, WorksheetScene._grid_brush)
        p.restore()

    def drawForeground(self, p: QPainter, rect: QRectF) -> None:
        if self.printing:
            return
        if self.rubber is not None:
            # the selection box: blue frame, light blue fill
            p.save()
            p.fillRect(self.rubber, QColor(0, 120, 215, 40))
            pen = QPen(QColor("#0078d7"), 1)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.drawRect(self.rubber.adjusted(0.5, 0.5, -0.5, -0.5))
            p.restore()
        view = self.views()[0] if self.views() else None
        if view is not None and getattr(view, "focused_item", None) is not None:
            return
        c = self.to_scene(self.cross.x(), self.cross.y())
        p.setPen(QPen(CROSS_COLOR, 1))
        p.drawLine(QPointF(c.x() - 4, c.y() + 0.5), QPointF(c.x() + 5, c.y() + 0.5))
        p.drawLine(QPointF(c.x() + 0.5, c.y() - 4), QPointF(c.x() + 0.5, c.y() + 5))


class SuggestionList(QListWidget):
    """SMath Cloud's autocomplete list (#region-suggestions): white, 1px black
    border, 12px text, at least 90px wide and 90px high at most; each entry
    has a 12x12 icon for function / unit / operand coloured by origin (core,
    plugin, worksheet) and shows its name without the unit apostrophe; the
    selected entry is white on #9faab5.  The selected entry's description
    appears in a tooltip box to the right of the list."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowFlags(Qt.ToolTip)
        self.setFocusPolicy(Qt.NoFocus)
        self.setIconSize(QSize(11, 11))
        self.setSpacing(0)
        self.setUniformItemSizes(True)
        self.setStyleSheet(
            "QListWidget{background:#fff;border:1px solid #000;font-size:11px;outline:0;}"
            "QListWidget::item{padding:0px 2px 0px 2px;margin:0;color:#000;border:0;height:14px;}"
            "QListWidget::item:selected{color:#fff;background:#9faab5;}"
            "QListWidget::item:hover{color:#fff;background:#9faab5;}")
        self.setMinimumWidth(90)
        self.setMaximumHeight(92)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.start = 0
        self.word = ""
        self.activated = False  # the user moved through the list (Enter applies)
        self.tooltip = QLabel(parent)
        self.tooltip.setWindowFlags(Qt.ToolTip)
        self.tooltip.setTextFormat(Qt.RichText)
        self.tooltip.setWordWrap(True)
        self.tooltip.setMaximumWidth(206)
        self.tooltip.setStyleSheet("QLabel{background:#ffffe1;border:1px solid #000;font-size:12px;"
                                   "padding:0 3px;margin:0;color:#000;}")
        self.tooltip.hide()
        self.currentRowChanged.connect(lambda _r: self.show_tooltip())

    def entries(self):
        return [self.item(i).data(Qt.UserRole) for i in range(self.count())]

    def fill(self, entries, selected) -> None:
        self.clear()
        for e in entries:
            it = QListWidgetItem(_origin_icon(e.kind, e.origin), e.text)
            it.setData(Qt.UserRole, e)
            self.addItem(it)
        self.activated = False
        self.setCurrentRow(-1 if selected is None else selected)
        if selected is not None:
            self.scrollToItem(self.item(selected), QListWidget.PositionAtTop)

    def show_tooltip(self) -> None:
        it = self.currentItem()
        desc = it.data(Qt.UserRole).description if it is not None and self.isVisible() else ""
        if not desc:
            self.tooltip.hide()
            return
        self.tooltip.setText(desc)
        self.tooltip.adjustSize()
        self.tooltip.move(self.x() + self.width() + 2, self.y())
        self.tooltip.show()

    def hideEvent(self, e) -> None:
        self.tooltip.hide()
        super().hideEvent(e)


_ICONS: dict = {}


def _origin_icon(kind: str, origin: int) -> QIcon:
    """The site's img-origin-<kind>-<origin> icons (copied from its CSS)."""
    key = (kind, origin)
    if key not in _ICONS:
        from pathlib import Path

        path = Path(__file__).with_name("icons") / f"origin-{kind}-{origin}.png"
        _ICONS[key] = QIcon(str(path)) if path.exists() else QIcon()
    return _ICONS[key]


class WorksheetView(QGraphicsView):
    checked = Signal(object)  # Report of the last double-check
    status = Signal(str)
    modified = Signal()
    pages_changed = Signal(int, int)  # page in view, page count
    zoom_changed = Signal(float)

    def __init__(self, worksheet: Optional[Worksheet] = None, parent=None):
        self.worksheet = worksheet or Worksheet()
        self.scene_ = WorksheetScene(self.worksheet)
        super().__init__(self.scene_, parent)
        self.style_ = Style()
        self.items: dict[int, RegionItem] = {}
        self.focused_item: Optional[RegionItem] = None
        self.selected: list[RegionItem] = []
        self._drag = None
        self.plot_tool = "move"
        self.dynamic_assistance = True  # View > Dynamic assistance (autocomplete)
        self._clip_items = None  # part of an equation copied with Ctrl+C  # toolbox Plot: "move" (drag pans) or "scale" (drag zooms)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.TextAntialiasing)
        self.setAlignment(Qt.AlignHCenter | Qt.AlignTop)  # Pages view: the page column is centred
        self.setFocusPolicy(Qt.StrongFocus)
        self.setDragMode(QGraphicsView.NoDrag)
        # repaint only what changed (each region item knows its bounds; the red
        # cross asks for a full update when it moves)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.viewport().setMouseTracking(True)  # move cursor over region frames
        self.verticalScrollBar().valueChanged.connect(self._scrolled)
        self.suggestions = SuggestionList(self)
        self.suggestions.hide()
        self.suggestions.itemClicked.connect(lambda it: self._apply_suggestion(it))  # one click, as the site
        self.clipboard: list = []
        for r in self.worksheet.regions:
            self._add_item(r)
        self.recalculate()
        self._grow_scene()
        self._to_top()
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, self._to_top)  # again once the window has its size

    # -- region management ---------------------------------------------------------
    def _add_item(self, region: Region) -> RegionItem:
        item = RegionItem(region, self.worksheet, self.style_)
        # regions not being edited are painted once and reused until they change
        item.setCacheMode(QGraphicsItem.DeviceCoordinateCache)
        self.scene_.addItem(item)
        self.items[region.id] = item
        self.place(item)
        return item

    def place(self, item: RegionItem) -> None:
        """Put a region where its worksheet position is drawn (on its page)."""
        item.setPos(self.scene_.to_scene(item.region.x, item.region.y))

    def to_sheet(self, scene_pt: QPointF) -> QPointF:
        return self.scene_.to_sheet(scene_pt)

    def new_region(self, x: float, y: float, text_region: bool = False) -> RegionItem:
        region = self.worksheet.add_region(snap(x), snap(y))
        region.font_size = getattr(self, "default_font_size", 10.0)  # Tools > Options
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
        self.worksheet.region_removed(item.region)
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
        """Recalculate the whole page (F9, loading, settings) and redraw it."""
        if self.worksheet.auto_calculation or force:
            self.worksheet.calculate()
        self.worksheet.take_changed()
        for it in self.items.values():
            it.relayout()
        self._grow_scene()
        self.scene_.update()

    def refresh(self) -> None:
        """Redraw only the regions whose results changed."""
        for rid in self.worksheet.take_changed():
            it = self.items.get(rid)
            if it is not None:
                it.relayout()
        self._grow_scene()
        self.schedule_double_check()

    # -- double-check ----------------------------------------------------------------------
    double_check_enabled = True

    def schedule_double_check(self) -> None:
        """Run the independent double-check once typing pauses (0.4 s)."""
        if not self.double_check_enabled:
            return
        from PySide6.QtCore import QTimer

        if not hasattr(self, "_check_timer"):
            self._check_timer = QTimer(self)
            self._check_timer.setSingleShot(True)
            self._check_timer.timeout.connect(self.run_double_check)
        self._check_timer.start(400)

    def run_double_check(self):
        from ..engine.verify import double_check

        try:
            rep = double_check(self.worksheet)
        except Exception as e:  # the check must never break the page
            self.status.emit(f"Double-check could not run: {e}")
            return None
        bad = {r.id for r, *_ in rep.mismatches}
        for it in self.items.values():
            flag = it.region.id in bad
            if getattr(it.region, "check_failed", False) != flag:
                it.region.check_failed = flag
                it.update()
        self.last_check = rep
        self.checked.emit(rep)
        return rep

    def update_after(self, item: RegionItem) -> None:
        """A region was left (or moved): bring what depends on it up to date."""
        if self.worksheet.auto_calculation:
            self.worksheet.update_after_edit(item.region)
        self.refresh()

    def _grow_scene(self) -> None:
        """Whole pages: one more page appears when content nears the end of
        the last one (as the desktop's Pages view)."""
        import math

        # the content's extent: a full scan only when regions came or went,
        # otherwise the region being edited can only push it further out
        # (in worksheet coordinates)
        n = len(self.items)

        def extent(it):
            fr = it.frame_rect()
            return it.region.x + fr.width(), it.region.y + fr.height()

        if getattr(self, "_extent_n", -1) != n or self.focused_item is None:
            ex = [extent(it) for it in self.items.values()]
            self._extent = (max((e[0] for e in ex), default=0.0), max((e[1] for e in ex), default=0.0))
            self._extent_n = n
        else:
            fx, fy = extent(self.focused_item)
            self._extent = (max(self._extent[0], fx), max(self._extent[1], fy))
        right, bottom = self._extent
        bottom = max(bottom, self.scene_.cross.y())
        if self.scene_.page_mode == "pages":
            # whole pages: another page once the content reaches the last one
            pages = max(1, math.ceil((bottom + 1) / CONTENT_H))
            w = max(PAGE_W, right + PAGE_MARGIN + 40)
            rect = QRectF(-DESK_PAD, -DESK_PAD, w + 2 * DESK_PAD, pages * PAGE_STEP + DESK_PAD)
        else:
            pages = max(1, math.ceil((bottom + 200) / CONTENT_H))
            rect = QRectF(0, 0, max(CONTENT_W + 40, right + 40), pages * CONTENT_H)
        if rect != self.scene_.sceneRect():
            self.scene_.setSceneRect(rect)
            self.pages_changed.emit(self.page_at_view(), pages)

    zoom = 1.0

    def set_zoom(self, factor: float) -> None:
        """View zoom (status bar, Ctrl+wheel), 10% to 400%."""
        self.zoom = min(4.0, max(0.1, factor))
        self.resetTransform()
        self.scale(self.zoom, self.zoom)
        self.zoom_changed.emit(self.zoom)

    def set_page_mode(self, mode: str) -> None:
        self.scene_.page_mode = mode
        for it in self.items.values():
            self.place(it)
        self.setAlignment((Qt.AlignHCenter if mode == "pages" else Qt.AlignLeft) | Qt.AlignTop)
        self._grow_scene()
        self.scene_.update()

    def _to_top(self) -> None:
        """A page opens at its top-left corner."""
        try:
            self.verticalScrollBar().setValue(self.verticalScrollBar().minimum())
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().minimum())
        except RuntimeError:
            pass

    def _scrolled(self, _value=None) -> None:
        try:
            self.pages_changed.emit(self.page_at_view(), self.scene_.page_count())
        except RuntimeError:
            pass  # the window is closing

    def page_at_view(self) -> int:
        top = self.mapToScene(self.viewport().rect().center()).y()
        if self.scene_.page_mode == "pages":
            return max(1, int(top // PAGE_STEP) + 1)
        return max(1, int(top // CONTENT_H) + 1)

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
                self.update_after(old)
                old.relayout()
        self.focused_item = item
        if old is not None and old.scene() is not None:
            old.setCacheMode(QGraphicsItem.DeviceCoordinateCache)
        if item is not None:
            item.setCacheMode(QGraphicsItem.NoCache)  # repainted on every keystroke
            item.focused = True
            item.relayout()
        self.hide_suggestions()
        self.refresh()
        self.scene_.update()

    def clear_selection(self) -> None:
        for it in self.selected:
            it.selected_region = False
            it.update()
        self.selected = []

    # -- mouse -------------------------------------------------------------------------
    MOVE_EDGE = 4.0  # px band along a region's frame that drags the region

    def _on_handle(self, item: RegionItem, scene_pt: QPointF) -> bool:
        """True on the frame band of a region (SMath shows its move cursor
        there): dragging from it moves the region, even while it is being
        edited.  Areas and separators are dragged anywhere."""
        if item.region.special:
            return True
        local = item.mapFromScene(scene_pt)
        r = item.frame_rect()
        e = self.MOVE_EDGE
        if item.region.plot is not None and item.plot_rect().contains(local):
            return False
        return (local.x() < e or local.y() < e or local.x() > r.width() - e or local.y() > r.height() - e)

    def _move_cursor(self):
        from pathlib import Path

        from PySide6.QtGui import QCursor, QPixmap

        if not hasattr(self, "_move_cur"):
            pm = QPixmap(str(Path(__file__).with_name("icons") / "move.cur"))
            self._move_cur = QCursor(pm) if not pm.isNull() else QCursor(Qt.SizeAllCursor)
        return self._move_cur

    def _start_move(self, item: RegionItem, pt: QPointF) -> None:
        # a region that is part of a selection drags the whole selection
        group = list(self.selected) if item in self.selected else [item]
        self._drag = ("move", pt, item, item.pos(), [(it, QPointF(it.region.x, it.region.y)) for it in group])
        for it, o in self._drag[4]:
            it._sheet_pos = o
        self.viewport().setCursor(self._move_cursor())

    def _item_at(self, scene_pt: QPointF) -> Optional[RegionItem]:
        for it in self.scene_.items(scene_pt):
            if isinstance(it, RegionItem) and it.frame_rect().contains(it.mapFromScene(scene_pt)):
                return it
        for it in self.items.values():
            if it.frame_rect().contains(it.mapFromScene(scene_pt)):
                return it
        return None

    def mousePressEvent(self, e) -> None:
        pt = self.mapToScene(e.position().toPoint())
        item = self._item_at(pt)
        if (e.button() == Qt.LeftButton and item is not None and
                (self._on_handle(item, pt) or (item in self.selected and item is not self.focused_item))):
            self._start_move(item, pt)
            return
        self.clear_selection()
        if e.button() == Qt.RightButton:
            # the site focuses the region under the mouse, then shows the menu
            if item is not None and item is not self.focused_item and item.region.kind in ("math", "text"):
                self.focus_item(item)
            elif item is None:
                self.focus_item(None)
            self.show_context_menu(item, e.globalPosition().toPoint())
            return
        if item is None:
            self.focus_item(None)
            sp = self.to_sheet(pt)
            self.scene_.cross = QPointF(max(0.0, snap(sp.x())), max(0.0, snap(sp.y())))
            self._drag = ("rubber", pt)
            self.scene_.update()
            return
        if item.region.special == "area" and item.toggle_hit(item.mapFromScene(pt)):
            self.toggle_area(item)
            return
        if item is self.focused_item and item.region.plot is not None and item.plot_rect().contains(item.mapFromScene(pt)):
            st = item.region.plot
            local = item.mapFromScene(pt)
            if local.x() > st.width - 8 and local.y() > st.height - 8:
                self._drag = ("resize", pt, item, (st.width, st.height))
            else:
                self._drag = ("pan", pt, item, (st.pan_x, st.pan_y, st.ppu_x, st.ppu_y))
            return
        if item is self.focused_item and e.modifiers() & Qt.ShiftModifier and item.region.kind in ("math", "text"):
            # Shift+click extends the selection to the click, as in a word processor
            self._shift_click(item, item.mapFromScene(pt))
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
                self._drag = ("pan", pt, item, (st.pan_x, st.pan_y, st.ppu_x, st.ppu_y))
            return
        self.focus_item(item)
        item.place_cursor(local)
        item.update()
        self._drag = ("maybe-move", pt, item, item.pos())  # becomes a move after 6 px

    def mouseMoveEvent(self, e) -> None:
        pt = self.mapToScene(e.position().toPoint())
        if not self._drag:
            item = self._item_at(pt)
            if item is not None and self._on_handle(item, pt):
                self.viewport().setCursor(self._move_cursor())
            else:
                self.viewport().unsetCursor()
            return
        if self._drag[0] == "maybe-move":
            _, start, item, orig = self._drag
            if (pt - start).manhattanLength() > 6 and e.buttons() & Qt.LeftButton:
                self._start_move(item, start)
        if self._drag[0] in ("pan", "resize"):
            kind, start, item, orig = self._drag
            d = pt - start
            st = item.region.plot
            if kind == "pan" and self.plot_tool == "scale":
                # the Scale tool: drag up/right to zoom in
                f = 1.01 ** (d.x() - d.y())
                st.ppu_x, st.ppu_y = orig[2] * f, orig[3] * f
            elif kind == "pan":
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
            _, start, item, orig, group = self._drag
            # moved in worksheet coordinates (a drag can cross a page break)
            d = self.to_sheet(pt) - self.to_sheet(start)
            lead = next(o for it, o in group if it is item)
            dx, dy = snap(lead.x() + d.x()) - lead.x(), snap(lead.y() + d.y()) - lead.y()
            for it, o in group:
                it._sheet_pos = QPointF(max(0.0, o.x() + dx), max(0.0, o.y() + dy))
                it.setPos(self.scene_.to_scene(it._sheet_pos.x(), it._sheet_pos.y()))
        elif self._drag[0] == "rubber":
            start = self._drag[1]
            rect = QRectF(start, pt).normalized()
            old = self.scene_.rubber
            self.scene_.rubber = rect
            self.scene_.update(rect.united(old) if old is not None else rect)
            self.clear_selection()
            for it in self.items.values():
                if rect.intersects(it.mapRectToScene(it.frame_rect())):
                    it.selected_region = True
                    it.update()
                    self.selected.append(it)

    def wheelEvent(self, e) -> None:
        """Wheel over a plot zooms it (Ctrl: x only, Shift: y only); Ctrl+wheel
        elsewhere zooms the view, as on the desktop."""
        pt = self.mapToScene(e.position().toPoint())
        if e.modifiers() & Qt.ControlModifier and (self._item_at(pt) is None or self._item_at(pt).region.plot is None):
            # zoom around the point under the mouse
            before = pt
            self.set_zoom(self.zoom * (1.1 if e.angleDelta().y() > 0 else 1 / 1.1))
            after = self.mapToScene(e.position().toPoint())
            d = (after - before) * self.zoom
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))
            e.accept()
            return
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
        if e.modifiers() & Qt.ShiftModifier and e.angleDelta().x() == 0:
            # Shift+wheel scrolls sideways (pages wider than the window)
            bar = self.horizontalScrollBar()
            bar.setValue(bar.value() - e.angleDelta().y())
            e.accept()
            return
        super().wheelEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        if self._drag and self._drag[0] == "move":
            group = self._drag[4]
            moved = False
            for it, o in group:
                new = getattr(it, "_sheet_pos", o)
                if new != o:
                    it.region.x, it.region.y = new.x(), new.y()
                    moved = True
            if moved:
                # reading order may have changed: recalculate like SMath
                self.worksheet.invalidate_order()
                self.recalculate()
                self.modified.emit()
            elif len(group) == 1 and group[0][0] is not self.focused_item and not group[0][0].region.special:
                self.focus_item(group[0][0])  # a click on the frame focuses
            self.viewport().unsetCursor()
        if self.scene_.rubber is not None:
            self.scene_.update(self.scene_.rubber)
            self.scene_.rubber = None
        self._drag = None

    def mouseDoubleClickEvent(self, e) -> None:
        # the automatic unit of a result is SMath's own and cannot be edited;
        # only the desired-unit box can (a single click puts the cursor in it)
        return

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
            self.refresh()
            return
        if key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Home, Qt.Key_End) and self.focused_item is not None:
            name = _selection_key_name(key, mods)
            if name is not None:
                item = self.focused_item
                if self._block_for_clash(item):
                    return
                item.editor.key(name)
                self._after_edit(item)
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
        if k in ("LEFT", "RIGHT", "UP", "DOWN") and self._block_for_clash(item):
            return
        if item is None:
            step = {"LEFT": (-GRID, 0), "RIGHT": (GRID, 0), "UP": (0, -GRID), "DOWN": (0, GRID),
                    "BACK": (0, -GRID)}.get(k)
            if step:
                c = self.scene_.cross
                self.scene_.cross = QPointF(max(0, c.x() + step[0]), max(0, c.y() + step[1]))
                self.scene_.update()
            return
        if k in ("UP", "DOWN") and item.region.kind != "text":
            # Up/Down move to the previous/next region; its cursor is where it
            # was left (observed on SMath Cloud, also from inside fractions)
            self._step_region(-1 if k == "UP" else 1)
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
        if text and not _word_char(text[0]) and self._block_for_clash(item):
            return  # m is a variable and a unit: pick one from the list first
        for ch in text:
            item.editor.key(ch)
        self._after_edit(item, typed=True)

    def _step_region(self, step: int) -> None:
        order = [self.items[r.id] for r in self.worksheet.ordered() if r.id in self.items]
        cur = self.focused_item
        if cur not in order:
            return
        k = order.index(cur) + step
        if 0 <= k < len(order):
            self.focus_item(order[k])
            order[k].update()

    def _tab(self, backwards: bool = False) -> None:
        """Tab moves focus to the next region in reading order (observed)."""
        if self._block_for_clash(self.focused_item):
            return
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
        if self._block_for_clash(item):
            return
        if item is None:
            c = self.scene_.cross
            self.scene_.cross = QPointF(c.x(), c.y() + GRID)
            self.scene_.update()
            return
        if item.region.kind == "text" and not shift:
            item.editor.key("ENTER")
            self._after_edit(item)
            return
        reg, h = item.region, item.frame_rect().height()
        self.focus_item(None)
        self.scene_.cross = QPointF(snap(reg.x), snap(reg.y + h + 5))

    def _after_edit(self, item: RegionItem, typed: bool = False) -> None:
        # as SMath Studio desktop: while a region is being edited its result is
        # not recalculated - it shows the empty box until the region is left,
        # then it and whatever depends on it are brought up to date.  Plots
        # follow their input live.
        if item.region.plot is not None:
            if self.worksheet.auto_calculation:
                self.worksheet.calculate_region(item.region)
        else:
            item.region.pending = True
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
            self._after_edit(item)

    def redo(self) -> None:
        item = self.focused_item
        if item is not None and item.editor.redo():
            self._after_edit(item)

    # -- autocomplete ---------------------------------------------------------------------
    def candidates(self, word: str, region: Region) -> list:
        return suggestion_list(word, self.worksheet._context_before(region).names())

    def entries_for(self, word: str, region: Region) -> list:
        ctx = self.worksheet._context_before(region)
        return suggestion_entries(word, ctx.names(), ctx.function_arities())

    def update_suggestions(self, item: RegionItem, force: bool = False) -> None:
        if not self.dynamic_assistance and not force:
            return
        start, word = item.editor.current_word()
        if not word or word[0].isdigit() or word[0] == ".":
            self.hide_suggestions()
            return
        if item.editor.in_unit:
            # the desired-unit box lists units (and unit constants) that start
            # with what was typed, as SMath Studio desktop: k, K, kA, kat...
            entries = unit_box_entries(word)
        else:
            entries = self.entries_for(word, item.region)
        if not entries:
            self.hide_suggestions()
            return
        clash = self._clash(item)
        if clash is not None:
            # make the two meanings of the name plain in the list
            for e in entries:
                if e.text == clash and e.origin == 3 and e.kind == "operand":
                    e.description = f"<strong>{clash}</strong> - variable defined on this worksheet"
        s = self.suggestions
        s.start = start
        s.word = word
        s.fill(entries, selected_index(entries, word))
        # the list opens under the cursor, 2px to the left (site: offsetLeft + x - 2)
        pos = self.mapFromScene(item.cursor_scene_pos())
        s.move(self.mapToGlobal(pos) + QPoint(-2, 1))
        rows = min(s.count(), 8)
        s.setMaximumHeight(16 * 8 + 4)
        s.resize(max(90, s.sizeHintForColumn(0) + 22), s.sizeHintForRow(0) * rows + 4)
        s.show()
        s.show_tooltip()

    def hide_suggestions(self) -> None:
        self.suggestions.hide()

    def _suggestion_key(self, key) -> bool:
        """Keys the open list takes (site suggestionsListKeyDown): Esc closes
        it, Tab applies the selected entry, Enter only once the user has moved
        through the list, Up/Down move (from nothing: Down -> first, Up -> last)."""
        s = self.suggestions
        if key == Qt.Key_Escape or s.count() < 1:
            if self._clash(self.focused_item) and key != Qt.Key_Escape:
                return True
            self.hide_suggestions()
            return key == Qt.Key_Escape  # anything else (Delete, arrows...) still acts
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

    def _apply_suggestion(self, it: QListWidgetItem) -> None:
        item = self.focused_item
        if item is None:
            return
        e = it.data(Qt.UserRole)
        name = e.name.split(" ")[0]  # "sum (4)" inserts sum(
        if e.kind == "unit":
            back = {v: k for k, v in SMATH_LABEL.items()}
            name = "'" + back.get(name[1:], name[1:])
        elif e.origin == 3 and e.kind == "operand":
            # the user picked the worksheet variable over a unit of the same name
            item.editor.confirmed_words.add(name)
        start, _ = item.editor.current_word()
        if e.kind == "function" and name in item.editor.STRUCTURE_WORDS:
            # the site inserts "sqrt(" - which becomes the radical, as typed
            item.editor.replace_word(start, name)
            item.editor.key("(")
        else:
            item.editor.replace_word(start, name, call=(e.kind == "function" and name not in KEYWORDS))
        self.hide_suggestions()
        self._after_edit(item)

    # -- right-click menu (SMath Cloud's, item for item) ---------------------------------
    def context_menu(self, item: Optional[RegionItem]) -> QMenu:
        """The menu SMath Cloud shows (GET .../contextmenu): Cut, Copy, Paste,
        Delete, Select all for everything, and for a math region Display
        input data, Go to definition, Show description, Disable evaluation,
        Ignore units, Optimization, Decimal places, Exponential threshold,
        Fractions and Rounding.  The worksheet default is marked with *."""
        m = QMenu(self)
        m.addAction("Cut", self.cut).setShortcut("Ctrl+X")
        m.addAction("Copy", self.copy).setShortcut("Ctrl+C")
        m.addAction("Paste", self.paste).setShortcut("Ctrl+V")
        m.addSeparator()
        m.addAction("Delete", self.delete_selection).setShortcut("Del")
        m.addSeparator()
        m.addAction("Select all", self.select_all).setShortcut("Ctrl+A")
        if item is None or item.region.kind != "math":
            return m
        r = item.region
        fmt = r.fmt or self.worksheet.format
        base = self.worksheet.format

        def check(menu, title, on, slot, enabled=True):
            a = menu.addAction(title)
            a.setCheckable(True)
            a.setChecked(on)
            a.setEnabled(enabled)
            a.triggered.connect(lambda _=False: (slot(), self._region_option_changed(item)))
            return a

        m.addSeparator()
        check(m, "Display input data", r.show_input, lambda: setattr(r, "show_input", not r.show_input))
        m.addSeparator()
        m.addAction("Go to definition", lambda: self.go_to_definition(item))
        a = m.addAction("Show description")
        a.setEnabled(False)  # region descriptions are not supported yet
        check(m, "Disable evaluation", not r.enabled, lambda: setattr(r, "enabled", not r.enabled))
        m.addSeparator()
        check(m, "Ignore units", r.ignore_units, lambda: setattr(r, "ignore_units", not r.ignore_units))
        m.addSeparator()
        opt = m.addMenu("Optimization")
        current = r.optimization or ("numeric" if item.editor.evaluate else "symbolic")
        for key, title in (("symbolic", "Symbolic"), ("numeric", "Numeric"), ("none", "None")):
            check(opt, title, current == key, lambda k=key: setattr(r, "optimization", k))

        def set_fmt(**kw):
            f = dataclasses.replace(r.fmt or self.worksheet.format, **kw)
            r.fmt = None if f == self.worksheet.format else f

        dp = m.addMenu("Decimal places")
        check(dp, "Trailing zeros", fmt.trailing_zeros, lambda: set_fmt(trailing_zeros=not fmt.trailing_zeros))
        dp.addSeparator()
        check(dp, "Significant figures mode", fmt.significant, lambda: set_fmt(significant=not fmt.significant))
        dp.addSeparator()
        for n in range(16):
            check(dp, f"{n} *" if n == base.decimals else str(n), fmt.decimals == n,
                  lambda n=n: set_fmt(decimals=n))
        et = m.addMenu("Exponential threshold")
        for n in range(16):
            check(et, f"{n} *" if n == base.threshold else str(n), fmt.threshold == n,
                  lambda n=n: set_fmt(threshold=n))
        fr = m.addMenu("Fractions")
        for key, title in (("decimal", "Decimal"), ("fraction", "Fraction"), ("auto", "Auto")):
            check(fr, title, fmt.fractions == key, lambda k=key: set_fmt(fractions=k))
        check(fr, "Default", r.fmt is None, lambda: setattr(r, "fmt", None))
        fr.addSeparator()
        check(fr, "Use mixed numbers", fmt.mixed, lambda: set_fmt(mixed=not fmt.mixed),
              enabled=fmt.fractions != "decimal")
        rd = m.addMenu("Rounding")
        check(rd, "Half to even", fmt.half_even, lambda: set_fmt(half_even=True))
        check(rd, "Away from zero", not fmt.half_even, lambda: set_fmt(half_even=False))
        return m

    def show_context_menu(self, item: Optional[RegionItem], global_pos) -> None:
        self.hide_suggestions()
        self.context_menu(item).exec(global_pos)

    def _region_option_changed(self, item: RegionItem) -> None:
        # options change what the region shows and, for Disable evaluation or
        # Ignore units, what it defines: recalculate like leaving the region
        self.worksheet.update_after_edit(item.region)
        self.refresh()
        self.modified.emit()

    def go_to_definition(self, item: RegionItem) -> None:
        """Focus the region that defines the name at the cursor (or the first
        name the region uses)."""
        _, word = item.editor.current_word()
        names = [word] if word else sorted(item.region.uses)
        for name in names:
            for other in sorted(self.worksheet.regions, key=lambda r: r.key, reverse=True):
                if other.key < item.region.key and (name in other.defined_vars or
                                                    any(n == name for n, _ in other.defined_funcs)):
                    target = self.items.get(other.id)
                    if target is not None:
                        self.focus_item(target)
                        self.ensureVisible(target.mapRectToScene(target.frame_rect()), 20, 20)
                        return

    # -- variable / unit name clashes -----------------------------------------------------
    def _clash(self, item: Optional[RegionItem]) -> Optional[str]:
        """The name at the cursor when it is both a worksheet variable and a
        unit (m:10 above, then m typed) and the user has not yet said which
        one is meant.  SMath Cloud silently takes the variable; here the
        choice has to be made in the list."""
        if item is None or item.region.kind != "math" or item.editor.in_unit:
            return None
        _, word = item.editor.current_word()
        if not word or word[0] in "'.0123456789" or word in item.editor.confirmed_words:
            return None
        if not is_unit(word):
            return None
        ctx = self.worksheet._context_before(item.region)
        if word not in ctx.names():
            return None
        return word

    def _block_for_clash(self, item: RegionItem) -> bool:
        word = self._clash(item)
        if word is None:
            return False
        if not self.suggestions.isVisible():
            self.update_suggestions(item, force=True)
        QApplication.beep()
        self.status.emit(f"'{word}' is both a variable and a unit - choose which one from the list "
                         "(Up/Down, then Tab or Enter).")
        return True

    # -- clipboard / region commands ----------------------------------------------------------
    def _selected_items(self) -> list:
        if self.selected:
            return list(self.selected)
        if self.focused_item is not None and self.focused_item.editor.selection is None:
            return [self.focused_item]
        return []

    def copy(self) -> None:
        """Ctrl+C: the selected part of an equation, or whole regions."""
        from PySide6.QtCore import QMimeData
        from PySide6.QtWidgets import QApplication

        from ..engine.model import to_text
        from ..io.smfile import dumps
        from ..worksheet import Worksheet

        item = self.focused_item
        mime = QMimeData()
        if item is not None and item.region.kind == "text" and item.editor.text_selection():
            a, b = item.editor.text_selection()
            self._clip_items = None
            mime.setText(item.editor.text[a:b])
            QApplication.clipboard().setMimeData(mime)
            return
        if item is not None and item.region.kind == "math" and item.editor.selection:
            r, a, b = item.editor.selection
            self._clip_items = [it.copy() if hasattr(it, "copy") else it for it in r.items[a:b]]
            part = r.__class__()
            part.items = list(r.items[a:b])
            mime.setText(to_text(part))
            QApplication.clipboard().setMimeData(mime)
            return
        items = self._selected_items()
        if not items:
            return
        self._clip_items = None
        top = min(it.region.y for it in items)
        left = min(it.region.x for it in items)
        ws = Worksheet()
        for it in items:
            src = it.region
            ws.regions.append(src)
        xml = dumps(ws, calculate=False)
        ws.regions.clear()
        mime.setData("application/x-websmath", xml.encode("utf-8"))
        mime.setData("application/x-websmath-origin", f"{left},{top}".encode())
        mime.setText("\n".join(it.editor.text if it.region.kind == "text" else it.editor.root.text()
                               for it in items))
        QApplication.clipboard().setMimeData(mime)

    def cut(self) -> None:
        item = self.focused_item
        self.copy()
        if item is not None and item.region.kind == "text" and item.editor.text_selection():
            item.editor.key("DELETE")
            self._after_edit(item)
            return
        if item is not None and item.region.kind == "math" and item.editor.selection:
            item.editor._push_undo()
            item.editor._apply_to_selection("BACK")
            self._after_edit(item)
            return
        self.delete_selection()

    def paste(self) -> None:
        """Ctrl+V: into the equation being edited, or as regions at the cross."""
        from PySide6.QtWidgets import QApplication

        from ..io.smfile import loads

        item = self.focused_item
        mime = QApplication.clipboard().mimeData()
        if item is not None and item.region.kind == "math" and self._clip_items:
            ed = item.editor
            ed._push_undo()
            if ed.selection:  # pasting replaces the selection
                ed._apply_to_selection("DELETE")
            for it in self._clip_items:
                ed.row.insert(ed.pos, it.copy() if hasattr(it, "copy") else it)
                ed.cursor = type(ed.cursor)(ed.row, ed.pos + 1)
            ed._fix_parents(ed.root)
            self._after_edit(item)
            return
        if item is not None and item.region.kind in ("math", "text") and not mime.hasFormat("application/x-websmath"):
            for ch in mime.text():
                if ch != "\n":
                    item.editor.key(ch)
            self._after_edit(item)
            return
        if not mime.hasFormat("application/x-websmath"):
            return
        src = loads(bytes(mime.data("application/x-websmath")).decode("utf-8"))
        ox, oy = (float(v) for v in bytes(mime.data("application/x-websmath-origin")).decode().split(","))
        self.focus_item(None)
        cx, cy = self.scene_.cross.x(), self.scene_.cross.y()
        self.clear_selection()
        for r in src.regions:
            r.x, r.y = snap(r.x - ox + cx), snap(r.y - oy + cy)
            r.editor.is_defined = lambda name, nargs=None, reg=r: self.worksheet.is_defined_before(reg, name, nargs)
            self.worksheet.regions.append(r)
            self.worksheet.invalidate_order()
            it = self._add_item(r)
            it.selected_region = True
            self.selected.append(it)
        self.recalculate()
        self.modified.emit()

    def _shift_click(self, item, local) -> None:
        ed = item.editor
        if item.region.kind == "text":
            anchor = ed.text_pos if ed.text_anchor is None else ed.text_anchor
            item.place_cursor(local)
            ed.text_anchor = anchor if anchor != ed.text_pos else None
        else:
            hit = item.slot_at(local)
            if hit is None:
                return
            r, k = hit
            sel = ed.selection
            if sel and sel[0] is r and ed.pos in (sel[1], sel[2]):
                anchor = sel[1] if ed.pos == sel[2] else sel[2]
            elif ed.row is r:
                anchor = ed.pos
            else:
                item.place_cursor(local)
                item.relayout()
                return
            ed.cursor = type(ed.cursor)(r, k)
            ed.selection = (r, min(anchor, k), max(anchor, k)) if anchor != k else None
        item.update()

    def delete_selection(self) -> None:
        item = self.focused_item
        if item is not None and not self.selected:
            # the Edit menu's Delete (the Del key) while an equation or text is
            # being edited: delete in it, right of the cursor
            self._named_key("DELETE")
            return
        if item is not None and item.editor.selection:
            item.editor._push_undo()
            item.editor._apply_to_selection("DELETE")
            self._after_edit(item)
            return
        for it in list(self.selected):
            self.delete_region(it)
        self.selected = []
        self.refresh()

    # -- Calculation menu on the selected part of an equation ------------------------------
    def _selection_or_operand(self):
        item = self.focused_item
        if item is None or item.region.kind != "math":
            return None, None
        ed = item.editor
        if ed.selection is None:
            r, a, b = ed.underline()
            if a == b:
                return item, None
            ed.selection = (r, a, b)
        return item, ed.selection

    def invert_selection(self) -> None:
        """Invert: the selection becomes (selection)^-1."""
        item, sel = self._selection_or_operand()
        if sel is None:
            return
        ed = item.editor
        ed._push_undo()
        ed._apply_to_selection("^")
        ed.type("-1")
        self._after_edit(item)

    def determinant_selection(self) -> None:
        """Determinant: the selection becomes det(selection), drawn |M|."""
        from ..engine.model import Paren, Row

        item, sel = self._selection_or_operand()
        if sel is None:
            return
        ed = item.editor
        ed._push_undo()
        r, a, b = sel
        inner = Row(r.items[a:b])
        del r.items[a:b]
        for k, ch in enumerate("det"):
            r.insert(a + k, ch)
        box = Paren(inner)
        r.insert(a + 3, box)
        ed._fix_parents(ed.root)
        ed.selection = None
        ed.set_cursor(r, a + 4)
        self._after_edit(item)

    def calculate_selection(self) -> None:
        """Calculate: replace the selected part by its value."""
        from ..engine.display import display_value, display_text, unit_text
        from ..engine.errors import SMathError
        from ..engine.model import Row
        from ..engine.parser import ParseError, parse_row

        item, sel = self._selection_or_operand()
        if sel is None:
            return
        r, a, b = sel
        part = Row()
        part.items = list(r.items[a:b])
        try:
            value = self.worksheet.evaluator.eval(parse_row(part), self.worksheet._context_before(item.region))
        except (SMathError, ParseError):
            item.editor.selection = None
            return
        d = display_value(value, self.worksheet.format)
        number = display_text(d).split(" ")[0].replace("·10^", "*10^")
        unit = unit_text(getattr(d, "unit", None))
        ed = item.editor
        ed._push_undo()
        del r.items[a:b]
        ed.set_cursor(r, a)
        ed.type(number + (("'" + _linear_unit(unit)) if unit else ""))
        self._after_edit(item)

    # -- Calculation > Differentiate / Solve ----------------------------------------------------
    def _variable_and_part(self):
        """(item, variable name, row, start, end) for Differentiate / Solve:
        the variable is the name the cursor is on; the expression is the
        selection, or else the whole expression (the right side of a
        definition, the part before "=" of an evaluation)."""
        item = self.focused_item
        if item is None or item.region.kind != "math":
            return None
        ed = item.editor
        a, b = ed.token_span(ed.row, ed.pos)
        word = "".join(x for x in ed.row.items[a:b] if isinstance(x, str))
        if not word or not (word[0].isalpha()) or word.startswith("'"):
            self.status.emit("Put the cursor on the variable first (e.g. on x in x^2+1).")
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

    def differentiate_selection(self) -> None:
        """Replace the expression by its derivative with respect to the
        variable under the cursor (SMath: Calculation > Differentiate)."""
        from ..engine import symbolic as S
        from ..engine.model import Row
        from ..engine.parser import ParseError, parse_row
        from ..io.smfile import ast_to_items

        got = self._variable_and_part()
        if got is None:
            return
        item, var, row, a, b = got
        part = Row()
        part.items = list(row.items[a:b])
        try:
            ctx = self.worksheet._context_before(item.region)
            d = S.derivative(S.expand(parse_row(part), ctx), var)
        except (ParseError, S.NotSymbolic):
            self.status.emit("This expression cannot be differentiated.")
            return
        ed = item.editor
        ed._push_undo()
        new = ast_to_items(d)
        row.items[a:b] = new
        type(ed)._fix_parents(ed.root)
        ed.selection = None
        ed.node = None
        ed.set_cursor(row, a + len(new))
        self._after_edit(item)

    def solve_selection(self) -> None:
        """Solve the expression (= 0, or an equation with the bold equals)
        for the variable under the cursor; the roots appear in a new region
        below (SMath: Calculation > Solve)."""
        from ..engine import ast as A
        from ..engine.model import Row
        from ..engine.parser import ParseError, parse_row
        from ..io.smfile import ast_to_items

        got = self._variable_and_part()
        if got is None:
            return
        item, var, row, a, b = got
        part = Row()
        part.items = list(row.items[a:b])
        try:
            node = parse_row(part)
        except ParseError:
            self.status.emit("Syntax is incorrect.")
            return
        call = A.Call("solve", [node, A.Var(var)])
        reg, h = item.region, item.frame_rect().height()
        self.focus_item(None)
        new = self.new_region(reg.x, reg.y + h + GRID)
        ed = new.editor
        ed.root.items = ast_to_items(call) + ["="]
        type(ed)._fix_parents(ed.root)
        ed.evaluate = True
        ed.set_cursor(ed.root, len(ed.root.items) - 1)
        self.focus_item(new)
        self._after_edit(new)
        self.focus_item(None)

    # -- formatting ------------------------------------------------------------------------------
    def format_selection(self, toggle: str = None, **values) -> None:
        """Apply formatting to the selected regions (or the one being edited)."""
        items = list(self.selected) or ([self.focused_item] if self.focused_item else [])
        for it in items:
            reg = it.region
            if toggle:
                setattr(reg, toggle, not getattr(reg, toggle))
            for k, v in values.items():
                setattr(reg, k, v)
            it.relayout()
        if items:
            self.modified.emit()

    # -- separators and areas ----------------------------------------------------------------------
    def insert_separator(self, y: float) -> None:
        r = self.worksheet.add_special("separator", snap(y))
        self._add_item(r)
        self.scene_.cross = QPointF(self.scene_.cross.x(), snap(y) + 18)
        self.scene_.update()

    def insert_area(self, y: float, height: float = 90.0) -> None:
        r = self.worksheet.add_special("area", snap(y), height)
        self._add_item(r).setZValue(-1)
        self.scene_.cross = QPointF(self.scene_.cross.x(), snap(y) + 18)
        self.scene_.update()

    def toggle_area(self, item: RegionItem) -> None:
        """Collapse/expand an area: the regions inside are hidden (and still
        evaluated, as in SMath)."""
        reg = item.region
        reg.collapsed = not reg.collapsed
        top, bottom = reg.y, reg.y + reg.area_height
        for it in self.items.values():
            if it is not item and top < it.region.y < bottom:
                it.setVisible(not reg.collapsed)
        item.relayout()

    # -- printing --------------------------------------------------------------------------------
    def render_pages(self, device) -> None:
        """Print or export the worksheet page by page (A4-width pages)."""
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QPainter

        self.focus_item(None)
        self.clear_selection()
        grid = self.scene_.show_grid
        self.scene_.show_grid = False
        self.scene_.printing = True
        mode = self.scene_.page_mode
        self.set_page_mode("pages")  # print exactly the pages of Pages view
        pages = self.scene_.page_count()
        painter = QPainter(device)
        target = QRectF(0, 0, device.width(), device.height())
        for k in range(pages):
            if k:
                device.newPage()
            self.scene_.render(painter, target, QRectF(0, k * PAGE_STEP, PAGE_W, PAGE_H))
        painter.end()
        self.set_page_mode(mode)
        self.scene_.show_grid = grid
        self.scene_.printing = False
    def select_all(self) -> None:
        self.focus_item(None)
        self.clear_selection()
        for it in self.items.values():
            it.selected_region = True
            it.update()
            self.selected.append(it)


# Spellings SMath Cloud leaves out of its list when another unit differs only
# in case (observed: kN is hidden behind the knot kn, Pa behind pa, A behind
# are a...).  They still work when typed, so the replica lists them anyway -
# an engineer looking for kN or Pa must find it.  Kept for the site tests.
SITE_HIDDEN_UNITS = {"A", "C", "g", "H", "K", "S", "T", "mg", "mJ", "mN", "mW", "mohm", "mΩ",
                     "Pa", "kN", "mS", "pc", "pS", "μS"}


# arc minute/second are listed under SMath's escaped names
SMATH_LABEL = {"'": "\\0027\\", '"': "\\0022\\"}


_SYMBOL_ORDER = "\\%‰°¤∞"


def smath_sort_key(label: str):
    """Order SMath Cloud lists suggestions in (.NET culture sorting): symbols
    first (\\ % ‰ ° ¤), then digits, then letters ignoring case and accents
    (Å with a), Greek after Latin; ties: lower case, then unaccented first."""
    import unicodedata

    primary, ties = [], []
    for ch in label.lstrip("'"):
        base = unicodedata.normalize("NFD", ch)[0]
        if ch.isalpha():
            primary.append((3, base.lower()))
        elif ch.isdigit():
            primary.append((2, ch))
        elif ch in _SYMBOL_ORDER:
            primary.append((1, str(_SYMBOL_ORDER.index(ch))))
        else:
            primary.append((0, ch))
        ties.append((base != ch, not ch.islower()))
    return primary, ties


@dataclass
class Suggestion:
    """One autocomplete entry, as SMath Cloud sends it."""

    name: str  # what is inserted: 'm, sum (4), x
    text: str  # what the list shows: m, sum (4), x
    kind: str  # function / unit / operand (picks the icon)
    origin: int  # 1 SMath core, 2 plugin, 3 this worksheet
    args: int
    description: str  # HTML shown in the tooltip ("" = no tooltip)


def suggestion_entries(word: str, defined_names, user_functions=None) -> list:
    """suggestion_list with each entry's icon kind, origin and description."""
    from ..engine.suggest_meta import SUGGESTION_META

    user_functions = user_functions or {}
    out = []
    for label, _kind in suggestion_list(word, defined_names):
        meta = SUGGESTION_META.get(label)
        if meta is not None and label not in user_functions:
            origin, args, desc = meta
        elif label.startswith("'"):
            # a unit the site hides (kN, Pa...): its title from the catalogue
            origin, args, desc = 1, 0, UNIT_CATALOG.get(label[1:], ("", ""))[1]
        else:
            origin, args, desc = 3, user_functions.get(label, 0), ""
        kind = "function" if args > 0 else ("unit" if label.startswith("'") else "operand")
        text = label[1:] if label.startswith("'") else label
        out.append(Suggestion(label, text, kind, origin, args, desc))
    return out


def unit_value_text(name: str) -> str:
    """'k -> "k = 1.380650424·10^-23 kg m^2/K s^2" (SI base units)."""
    from ..engine.display import DUnit, display_text, display_value, unit_text
    from ..engine.numformat import NumberFormat
    from ..engine.units import base_unit_parts, unit_quantity

    q = unit_quantity(name)
    num = display_text(display_value(q, NumberFormat(decimals=10, engineering=False), show_unit=False))
    u = unit_text(DUnit(*base_unit_parts(q.dims))) if any(q.dims) else ""
    return f"{name} = {num} {u}".rstrip()


def unit_box_entries(word: str) -> list:
    """Entries for the desired-unit box: every unit whose name starts with the
    typed text (any case), in SMath's order, each described by its name,
    category and value in SI units."""
    import html

    w = word[1:] if word.startswith("'") else word
    names = [u for u in UNIT_CATALOG if u.lower().startswith(w.lower())]
    names.sort(key=lambda u: smath_sort_key("'" + u))
    out = []
    for u in names:
        category, title = UNIT_CATALOG.get(u, ("", u))
        desc = (f"{html.escape(title)} ({html.escape(category)})<br>"
                f"<span style='font-family:Courier New'>{html.escape(unit_value_text(u))}</span>")
        label = "'" + SMATH_LABEL.get(u, u)
        out.append(Suggestion(label, label[1:], "unit", 1, 0, desc))
    return out


def _selection_key_name(key, mods) -> Optional[str]:
    """Editor key for Shift/Ctrl (Option/Cmd on a Mac) + arrow, Home, End:
    SHIFT+LEFT, WORD+RIGHT, SHIFT+WORD+LEFT, ...  None for plain keys."""
    import sys

    mac = sys.platform == "darwin"
    shift = bool(mods & Qt.ShiftModifier)
    word = bool(mods & (Qt.AltModifier if mac else Qt.ControlModifier))
    base = {Qt.Key_Left: "LEFT", Qt.Key_Right: "RIGHT", Qt.Key_Home: "HOME", Qt.Key_End: "END"}[key]
    if mac and mods & Qt.ControlModifier and base in ("LEFT", "RIGHT"):
        base = "HOME" if base == "LEFT" else "END"  # Cmd+arrow: start/end of the line
        word = False
    if word and base in ("HOME", "END"):
        word = False  # Ctrl+Home/End: start/end
    if not shift and not word:
        return None if base in ("LEFT", "RIGHT") and not (mac and mods & Qt.ControlModifier) else base
    return ("SHIFT+" if shift else "") + ("WORD+" if word else "") + base


def selected_index(entries: list, word: str) -> Optional[int]:
    """The entry SMath Cloud highlights when the list opens: the first whose
    name starts with the typed text (case-sensitive first, observed: M ->
    MB, m -> m, q -> qq), else ignoring case (Si -> sign), else none."""
    key = (lambda e: e.name) if word.startswith("'") else (lambda e: e.text)
    for fold in (False, True):
        w = word.lower() if fold else word
        for k, e in enumerate(entries):
            t = key(e).lower() if fold else key(e)
            if t.startswith(w):
                return k
    return None


# False: variables, units, constants, functions (asked for); True: SMath Cloud's order
SMATH_ORDER = False


def _is_constant_unit(label: str) -> bool:
    from ..engine.unitdata import INFO

    name = label[1:] if label.startswith("'") else label
    return INFO.get(name, ("",))[0] == "constant"


_UNITS_SORTED = None


def _sorted_units() -> list:
    """[(label, lower-case name)] of every unit in SMath's order (sorted once)."""
    global _UNITS_SORTED
    if _UNITS_SORTED is None or len(_UNITS_SORTED) != len(UNIT_CATALOG):
        _UNITS_SORTED = sorted((("'" + SMATH_LABEL.get(u, u), u.lower()) for u in UNIT_CATALOG),
                               key=lambda x: smath_sort_key(x[0]))
    return _UNITS_SORTED


_CATALOG_SORTED = None


def _sorted_catalog() -> list:
    """[(label, kind, lower-case name)] of functions, constants and keywords
    in SMath's order, built once (overloads listed as "sum (1)", "sum (4)")."""
    global _CATALOG_SORTED
    if _CATALOG_SORTED is None:
        counts, entries = {}, {}
        for name, nargs, _, _ in FUNCTIONS:
            counts[name] = counts.get(name, 0) + 1
        for name, nargs, _, _ in FUNCTIONS:
            entries.setdefault(name if counts[name] == 1 else f"{name} ({nargs})", ("function", name.lower()))
        for c in list(BUILTIN_CONSTANTS) + KEYWORDS + ["lastError"]:
            entries.setdefault(c, ("constant", c.lower()))
        _CATALOG_SORTED = sorted(((k, kind, low) for k, (kind, low) in entries.items()),
                                 key=lambda x: smath_sort_key(x[0]))
    return _CATALOG_SORTED


def suggestion_list(word: str, defined_names) -> list:
    """The autocomplete list for a partial word: case-insensitive substring
    matches over units, functions, constants, keywords, lastError and the
    worksheet's names defined above.  Order: the worksheet's names, units,
    constants, unit constants, functions and keywords (SMATH_ORDER: SMath
    Cloud's own order - units first, the rest mixed).  Catalogues are sorted
    once, so a keystroke only filters them."""
    w = word.lower()
    needle = w[1:] if w.startswith("'") else w
    # every unit is listed, also those SMath Cloud hides behind a case
    # variant (kN behind kn, Pa behind pa; see SITE_HIDDEN_UNITS)
    units = [(label, "unit") for label, low in _sorted_units() if needle in low]
    catalog = [(k, kind) for k, kind, low in _sorted_catalog() if needle in low]
    known = {k for k, _ in catalog}
    variables = sorted(((n, "variable") for n in defined_names if needle in n.lower() and n not in known),
                       key=lambda x: smath_sort_key(x[0]))
    if SMATH_ORDER:
        rest = sorted(catalog + variables, key=lambda x: smath_sort_key(x[0]))
        return units + rest
    consts = [(k, v) for k, v in catalog if v == "constant" and k not in KEYWORDS]
    funcs = [(k, v) for k, v in catalog if v == "function" or k in KEYWORDS]
    unit_consts = [u for u in units if _is_constant_unit(u[0])]
    plain_units = [u for u in units if not _is_constant_unit(u[0])]
    return variables + plain_units + consts + unit_consts + funcs


def _linear_unit(u: str) -> str:
    """kg·m/s^2 -> kg*'m/'s^2 (typed form for the unit placeholder)."""
    out = u.replace("·", "*'").replace("/", "/'")
    return out
