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

from pathlib import Path as _Path
import markforge.calc.ui as _calc_ui
PACKAGE_ICONS = _Path(_calc_ui.__file__).with_name("icons")
LEGACY_ICONS = _Path(__file__).with_name("icons")

import dataclasses
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QKeyEvent, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QGraphicsItem, QGraphicsScene, QGraphicsView, QLabel, QListWidget,
                               QListWidgetItem, QMenu)

from markforge.calc.engine.catalog import FUNCTIONS, UNIT_CATALOG
from markforge.calc.engine.evaluator import BUILTIN_CONSTANTS
from markforge.calc.engine.units import is_unit
from markforge.calc.worksheet import Region, Worksheet
from markforge.calc.ui.layout import Style
from markforge.calc.ui.region_item import RegionItem

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


@dataclass
class PageGeometry:
    """A worksheet's pages in worksheet units.  ``scale`` is SMath's print
    scale: when the widest region is wider than the printable area the
    printout is shrunk to fit it (observed on a 0.99 printout: a 749 px
    title block in a 720 px printable width printed at 96.2 %), so a page
    holds 1/scale more of the worksheet; the page is drawn that much larger
    here so screen and paper break at the same places."""

    W: float = PAGE_W
    H: float = PAGE_H
    ML: float = PAGE_MARGIN
    MR: float = PAGE_MARGIN
    MT: float = PAGE_MARGIN
    MB: float = PAGE_MARGIN
    GAP: float = PAGE_GAP
    scale: float = 1.0

    @property
    def STEP(self) -> float:
        return self.H + self.GAP

    @property
    def CW(self) -> float:
        return self.W - self.ML - self.MR

    @property
    def CH(self) -> float:
        return self.H - self.MT - self.MB

    @classmethod
    def of(cls, page, widest: float = 0.0) -> "PageGeometry":
        s = 1.0
        if widest > page.printable_w > 0:
            s = page.printable_w / widest
        return cls(page.paper_w / s, page.paper_h / s, page.margin_l / s, page.margin_r / s,
                   page.margin_t / s, page.margin_b / s, PAGE_GAP, s)


def background_rect(target: QRectF, img, mode: str) -> QRectF:
    """Where a background image goes in `target`: Stretch fills it, Fit keeps
    the proportions inside it, Fill keeps them and covers it (clipped),
    Original is the image's own size, centred."""
    iw, ih = max(1, img.width()), max(1, img.height())
    if mode == "stretch":
        return QRectF(target)
    if mode in ("fit", "fill"):
        k = (min if mode == "fit" else max)(target.width() / iw, target.height() / ih)
        w, h = iw * k, ih * k
    else:
        w, h = iw, ih
    r = QRectF(0, 0, w, h)
    r.moveCenter(target.center())
    return r


class WorksheetScene(QGraphicsScene):
    def __init__(self, worksheet: Worksheet, parent=None):
        super().__init__(parent)
        self.worksheet = worksheet
        self.cross = QPointF(18, 18)
        self.show_grid = True
        self.page_mode = "pages"  # "pages", "bounds" (printing bounds) or "none"
        self.printing = False
        self.rubber: Optional[QRectF] = None  # the selection box being dragged
        self.geo = PageGeometry.of(worksheet.page)
        self._images: dict = {}  # decoded background/header pictures
        self.setSceneRect(0, 0, PAGE_W + 40, PAGE_H * 3)

    # -- worksheet <-> scene coordinates ----------------------------------------------
    layer: Optional[str] = None  # "header"/"footer" while that layer is edited

    def layer_origin(self, kind: str, page: int = 0) -> QPointF:
        """Top-left of a header (page top, left margin) or footer (bottom
        margin) layer on a page, in scene coordinates."""
        g = self.geo
        top = page * g.STEP
        return QPointF(g.ML, top if kind == "header" else top + g.H - g.MB)

    def to_scene(self, x: float, y: float) -> QPointF:
        """Where worksheet point (x, y) is drawn."""
        if self.layer:
            o = self.layer_origin(self.layer)
            return QPointF(o.x() + x, o.y() + y)
        if self.page_mode != "pages":
            return QPointF(x, y)
        g = self.geo
        k = max(0, int(y // g.CH))
        return QPointF(x + g.ML, y - k * g.CH + k * g.STEP + g.MT)

    def to_sheet(self, pt: QPointF) -> QPointF:
        """The worksheet point under scene point pt (margins and gaps belong
        to the nearest printable area)."""
        if self.layer:
            o = self.layer_origin(self.layer)
            return QPointF(pt.x() - o.x(), pt.y() - o.y())
        if self.page_mode != "pages":
            return QPointF(pt)
        g = self.geo
        k = max(0, int(pt.y() // g.STEP))
        if pt.y() >= k * g.STEP + g.H:
            k += 1  # the gap below a page leads into the next one
        local = min(max(pt.y() - k * g.STEP - g.MT, 0.0), g.CH - 0.01)
        return QPointF(pt.x() - g.ML, k * g.CH + local)

    def page_count(self) -> int:
        from markforge.calc.ui.region_item import RegionItem

        bottom = max((it.region.y + it.frame_rect().height() for it in self.items() if isinstance(it, RegionItem)),
                     default=0.0)
        return max(1, int(bottom // self.geo.CH) + 1)

    def drawBackground(self, p: QPainter, rect: QRectF) -> None:
        if self.page_mode == "none" or (self.printing and self.page_mode != "pages"):
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
            g = self.geo
            p.drawLine(QPointF(g.CW + 0.5, rect.top()), QPointF(g.CW + 0.5, rect.bottom()))
            k = max(0, int(rect.top() // g.CH))
            while k * g.CH <= rect.bottom():
                if k > 0:
                    p.drawLine(QPointF(rect.left(), k * g.CH + 0.5), QPointF(rect.right(), k * g.CH + 0.5))
                k += 1
            return
        # pages view
        g = self.geo
        if not self.printing:
            p.fillRect(rect, DESK)
        count = self.page_count()
        k = max(0, int(rect.top() // g.STEP))
        while k * g.STEP <= rect.bottom():
            page = QRectF(0, k * g.STEP, g.W, g.H)
            k += 1
            if not page.intersects(rect):
                continue
            p.fillRect(page, Qt.white)
            area = page.adjusted(g.ML, g.MT, -g.MR, -g.MB)
            if self.show_grid and not self.printing:
                # grid lines at worksheet multiples of GRID: the page's first
                # worksheet row is (k-1)*CH
                off = ((k - 1) * g.CH) % GRID
                self._grid(p, area.intersected(rect), QPointF(area.left(), area.top() - off))
            if not self.printing and not self.worksheet.page.background:
                p.setPen(QPen(PRINTABLE_BORDER, 1))
                p.drawRect(area.adjusted(-0.5, -0.5, 0.5, 0.5))
            # the page background (a frame, a letterhead) lies over the grid
            self._paint_background(p, page, area)
            setup = self.worksheet.page
            for kind in ("header", "footer"):
                if self.layer == kind and k == 1:
                    continue  # being edited: its regions are on the page as items
                self._paint_layer(p, getattr(setup, kind), self.layer_origin(kind, k - 1), k, count)
            if not setup.header and not setup.footer:
                # SMath's Page Setup header/footer lines (files without header/footer layers)
                self._paint_page_text(p, page, setup, k, count)
            if not self.printing:
                p.setPen(QPen(PAGE_BORDER, 1))
                p.drawRect(page.adjusted(-0.5, -0.5, 0.5, 0.5))

    # -- page decoration: background image, header/footer layers ------------------------------
    def _image(self, key, data: bytes):
        from PySide6.QtGui import QImage

        img = self._images.get(key)
        if img is None:
            img = QImage()
            img.loadFromData(data)
            self._images[key] = img
        return img

    def _paint_background(self, p: QPainter, page: QRectF, area: QRectF) -> None:
        setup = self.worksheet.page
        if not setup.background or (self.printing and not setup.print_background):
            return
        img = self._image(("bg", id(setup.background)), setup.background)
        if img.isNull():
            return
        target = page if setup.background_full_page else area
        p.save()
        p.setClipRect(target)
        p.drawImage(background_rect(target, img, setup.background_size), img)
        p.restore()

    def _paint_page_text(self, p: QPainter, page: QRectF, setup, k: int, count: int) -> None:
        import re as _re

        from PySide6.QtGui import QFont, QFontMetricsF

        from markforge.calc.page import field_text
        from markforge.calc.ui.region_item import TEXT_FAMILIES
        from markforge.calc.ui.layout import _family

        g = self.geo
        for kind in ("header", "footer"):
            text = getattr(setup, f"{kind}_text")
            if not text:
                continue
            attrs = getattr(setup, f"{kind}_attrs") or {}
            text = _re.sub(r"&\[([A-Z]+)(?:\[([^\]]*)\])?\]", lambda m: field_text(
                "\\[" + m.group(1) + (f"[{m.group(2)}]" if m.group(2) else "") + "]\\", self.worksheet.metadata,
                k, count, getattr(self.worksheet, "filename", "")), text)
            f = QFont(_family(TEXT_FAMILIES))
            f.setPointSizeF(8)
            m = QFontMetricsF(f)
            p.setFont(f)
            p.setPen(QColor(attrs.get("color", "#a9a9a9")))
            band = QRectF(page.left() + g.ML, page.top(), g.CW, g.MT) if kind == "header" else \
                QRectF(page.left() + g.ML, page.bottom() - g.MB, g.CW, g.MB)
            align = {"Left": Qt.AlignLeft, "Right": Qt.AlignRight}.get(attrs.get("alignment", "Center"), Qt.AlignHCenter)
            p.drawText(band, align | Qt.AlignVCenter, text)

    def _paint_layer(self, p: QPainter, regions: list, origin: QPointF, page: int, count: int) -> None:
        """The header (or footer) regions of one page: pictures, text, and
        fields filled in for this page (page number, count, title...)."""
        if not regions:
            return
        from PySide6.QtGui import QFont, QFontMetricsF

        from markforge.calc.page import field_text
        from markforge.calc.ui.layout import MONO_FAMILIES, _family
        from markforge.calc.ui.region_item import PAD_TOP, PAD_X, TEXT_FAMILIES

        for r in regions:
            x, y = origin.x() + r.x, origin.y() + r.y
            if r.special == "picture":
                img = self._image(("pic", id(r.image)), r.image)
                if not img.isNull():
                    from markforge.calc.ui.region_item import draw_image

                    draw_image(p, QRectF(x, y, r.pic_w or img.width(), r.pic_h or img.height()), img,
                               self._images.setdefault(("scaled", id(r.image)), {}))
                continue
            if r.field_code:
                text = field_text(r.field_code, self.worksheet.metadata, page, count,
                                  getattr(self.worksheet, "filename", ""))
                f = QFont(_family(MONO_FAMILIES))
            elif r.kind == "text":
                text = r.editor.text
                f = QFont(r.font_family or _family(TEXT_FAMILIES))
            else:
                text = r.editor.root.text()
                f = QFont(_family(MONO_FAMILIES))
            f.setPointSizeF(r.font_size)
            m = QFontMetricsF(f)
            p.setFont(f)
            p.setPen(QColor(r.color or "#000000"))
            for i, line in enumerate(text.split("\n")):
                p.drawText(QPointF(x + PAD_X + (1 if r.field_code else 0), y + PAD_TOP + m.ascent()
                                   + i * m.lineSpacing()), line)

    _grid_brush = None

    def _grid(self, p: QPainter, rect: QRectF, origin: QPointF = QPointF(0, 0)) -> None:
        """The 9 px grid, filled from one tile (much faster than lines)."""
        if WorksheetScene._grid_brush is None:
            from PySide6.QtGui import QBrush, QPixmap

            tile = QPixmap(GRID, GRID)
            tile.fill(Qt.transparent)  # only the lines: a page background shows through
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
        if self.layer:
            # the edited layer's boundary and its tag, as SMath Studio
            g = self.geo
            y = g.MT if self.layer == "header" else g.H - g.MB
            pen = QPen(QColor("#808080"), 1, Qt.DashLine)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.drawLine(QPointF(0, y + 0.5), QPointF(g.W, y + 0.5))
            from PySide6.QtGui import QFont, QFontMetricsF

            f = QFont()
            f.setPixelSize(11)
            fm = QFontMetricsF(f)
            label = "Header" if self.layer == "header" else "Footer"
            w, h = fm.horizontalAdvance(label) + 12, fm.height() + 6
            tag = QRectF(g.W - g.MR - w, y + 3 if self.layer == "header" else y - h - 3, w, h)
            p.fillRect(tag, Qt.white)
            p.setPen(QPen(QColor("#808080"), 1))
            p.drawRect(tag.adjusted(0.5, 0.5, -0.5, -0.5))
            p.setFont(f)
            p.setPen(Qt.black)
            p.drawText(tag, Qt.AlignCenter, label)
        view = self.views()[0] if self.views() else None
        if view is not None and getattr(view, "focused_item", None) is not None:
            return
        c = self.to_scene(self.cross.x(), self.cross.y())
        p.setPen(QPen(CROSS_COLOR, 1))
        p.drawLine(QPointF(c.x() - 4, c.y() + 0.5), QPointF(c.x() + 5, c.y() + 0.5))
        p.drawLine(QPointF(c.x() + 0.5, c.y() - 4), QPointF(c.x() + 0.5, c.y() + 5))


from markforge.calc.ui.suggest import (  # noqa: E402  moved into the package
    SuggestionList, Suggestion, suggestion_entries, suggestion_list, unit_box_entries, unit_value_text, selected_index, smath_sort_key, _selection_key_name, _origin_icon, _linear_unit, SITE_HIDDEN_UNITS, SMATH_LABEL)
import markforge.calc.ui.suggest as _suggest  # noqa: E402


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
        from markforge.calc.engine.verify import double_check

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
        if self.scene_.layer:
            return  # the page layout belongs to the content, not the edited layer
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
        # SMath's print scale follows the widest region (header layer included)
        head = [r.x + (r.pic_w if r.special == "picture" else 0) for r in
                self.worksheet.page.header + self.worksheet.page.footer]
        geo = PageGeometry.of(self.worksheet.page, max([right] + head))
        if geo != self.scene_.geo:
            self.scene_.geo = geo
            for it in self.items.values():
                self.place(it)
            self.scene_.update()
        if self.scene_.page_mode == "pages":
            # whole pages: another page once the content reaches the last one
            g = self.scene_.geo
            pages = max(1, math.ceil((bottom + 1) / g.CH))
            w = max(g.W, right + g.ML + 40)
            rect = QRectF(-DESK_PAD, -DESK_PAD, w + 2 * DESK_PAD, pages * g.STEP + DESK_PAD)
        else:
            g = self.scene_.geo
            pages = max(1, math.ceil((bottom + 200) / g.CH))
            rect = QRectF(0, 0, max(g.CW + 40, right + 40), pages * g.CH)
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
            return max(1, int(top // self.scene_.geo.STEP) + 1)
        return max(1, int(top // self.scene_.geo.CH) + 1)

    # -- focus -------------------------------------------------------------------------
    def focus_item(self, item: Optional[RegionItem]) -> None:
        if item is not None and (item.region.special == "picture" or item.region.field_code):
            # a picture or a field has nothing to type into: it is selected instead
            self.focus_item(None)
            self.clear_selection()
            item.selected_region = True
            item.update()
            self.selected.append(item)
            return
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
            pm = QPixmap(str(PACKAGE_ICONS / "move.cur"))
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
        # only the desired-unit box can (a single click puts the cursor in it).
        # A double-click in a page's top or bottom margin edits the header or
        # footer (SMath Studio); one on the page body goes back to the content.
        if e is None or self.scene_.page_mode != "pages":
            return
        pt = self.mapToScene(e.position().toPoint())
        g = self.scene_.geo
        local = pt.y() - int(pt.y() // g.STEP) * g.STEP
        zone = "header" if local < g.MT else ("footer" if g.H - g.MB < local <= g.H else None)
        if self.scene_.layer and zone != self.scene_.layer:
            self.leave_layer()
        elif zone and not self.scene_.layer and self._item_at(pt) is None:
            self.edit_layer(zone)

    # -- header / footer layers (Insert > Header and Footer) ----------------------------------
    layer_changed = Signal(object)

    def edit_layer(self, kind: str) -> None:
        """Edit the header or footer: its regions come onto the first page
        as ordinary regions (typed, moved, deleted as usual) and the content
        is dimmed until the layer is left."""
        if self.scene_.layer == kind:
            return
        self.leave_layer()
        if self.scene_.page_mode != "pages":
            self.set_page_mode("pages")
        self.focus_item(None)
        self.clear_selection()
        content = self.worksheet
        layer = Worksheet()
        layer.regions = getattr(content.page, kind)
        layer.metadata = content.metadata
        layer.page = content.page
        for r in layer.regions:
            r.editor.is_defined = lambda name, nargs=None, reg=r: layer.is_defined_before(reg, name, nargs)
        self._content = (content, self.items, self.scene_.cross)
        for it in self.items.values():
            it.setOpacity(0.35)
            it.setAcceptedMouseButtons(Qt.NoButton)
        self.worksheet = layer
        self.items = {}
        self.scene_.layer = kind
        self.scene_.cross = QPointF(18, 18)
        for r in layer.regions:
            self._add_item(r)
        self.recalculate()
        self.scene_.update()
        o = self.scene_.layer_origin(kind)
        self.ensureVisible(QRectF(o.x(), o.y(), 10, 10), 20, 60)
        self.layer_changed.emit(kind)

    def leave_layer(self) -> None:
        if not self.scene_.layer:
            return
        self.focus_item(None)
        self.clear_selection()
        for it in self.items.values():
            self.scene_.removeItem(it)
        content, items, cross = self._content
        self.worksheet, self.items = content, items
        self.scene_.layer = None
        self.scene_.cross = cross
        for it in self.items.values():
            it.setOpacity(1.0)
            it.setAcceptedMouseButtons(Qt.AllButtons)
        self.modified.emit()
        self._grow_scene()
        self.scene_.update()
        self.layer_changed.emit(None)

    def refresh_fields(self) -> None:
        """Redraw what shows metadata (fields, header/footer) after File > Properties."""
        for it in self.items.values():
            if it.region.field_code:
                it.relayout()
        self.scene_.update()

    def page_setup_changed(self) -> None:
        """Paper, margins or background changed: pages and positions follow."""
        self.scene_.geo = PageGeometry()  # forces a fresh layout
        self._extent_n = -1
        self._grow_scene()
        for it in self.items.values():
            self.place(it)
        self.scene_.update()

    def insert_picture(self, data: bytes, fmt: str = "png") -> None:
        """Insert > Picture > From file: a picture region at the red cross,
        at the image's own size (at most the printable width)."""
        from PySide6.QtGui import QImage

        img = QImage()
        img.loadFromData(data)
        if img.isNull():
            return
        c = self.scene_.cross
        self.focus_item(None)
        r = self.worksheet.add_region(snap(c.x()), snap(c.y()))
        r.special = "picture"
        r.image, r.image_format = data, ("jpg" if fmt in ("jpg", "jpeg") else fmt)
        k = min(1.0, self.scene_.geo.CW / max(1, img.width()))
        r.pic_w, r.pic_h = round(img.width() * k), round(img.height() * k)
        self._add_item(r)
        self.scene_.cross = QPointF(c.x(), snap(c.y() + r.pic_h + GRID))
        self.modified.emit()
        self._grow_scene()

    def insert_field(self, code: str) -> None:
        """Insert > Field: a field region at the red cross (header, footer
        or content)."""
        c = self.scene_.cross
        self.focus_item(None)
        r = self.worksheet.add_region(snap(c.x()), snap(c.y()))
        r.field_code = code
        r.font_size = getattr(self, "default_font_size", 10.0)
        self._add_item(r)
        self.scene_.cross = QPointF(c.x(), c.y() + 2 * GRID)
        self.modified.emit()
        self.scene_.update()

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
            if self.scene_.layer and self.focused_item is None and not self.suggestions.isVisible():
                self.leave_layer()  # Esc leaves header/footer editing
                return
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
        if item is not None and item.region.plot is not None:
            st = item.region.plot
            m.addSeparator()
            m.addAction("Plot settings...", lambda: self.plot_settings(item))

            def toggle(attr):
                setattr(st, attr, not getattr(st, attr))
                item._plot_cache = None
                item.update()
                self.modified.emit()

            for title, attr in (("Grid", "grid"), ("Axes", "axes"), ("Graph by points", "points")):
                a = m.addAction(title, lambda attr=attr: toggle(attr))
                a.setCheckable(True)
                a.setChecked(getattr(st, attr))
            return m
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

    def plot_settings(self, item: RegionItem) -> None:
        """The plot's shown ranges, grid, axes and lines/points."""
        from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QRadioButton

        from markforge.calc.plot import fit_ranges

        st = item.region.plot
        d = QDialog(self)
        d.setWindowTitle("Plot settings")
        form = QFormLayout(d)
        (x0, x1), (y0, y1) = st.x_range(), st.y_range()
        boxes = []
        for label, v in (("x from", x0), ("x to", x1), ("y from", y0), ("y to", y1)):
            b = QDoubleSpinBox()
            b.setDecimals(4)
            b.setRange(-1e9, 1e9)
            b.setValue(v)
            form.addRow(label + ":", b)
            boxes.append(b)
        grid, axes = QCheckBox("Grid"), QCheckBox("Axes")
        grid.setChecked(st.grid)
        axes.setChecked(st.axes)
        lines, points = QRadioButton("Lines"), QRadioButton("Points")
        (points if st.points else lines).setChecked(True)
        for w in (grid, axes, lines, points):
            form.addRow(w)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        form.addRow(bb)
        if d.exec() != QDialog.Accepted:
            return
        try:
            fit_ranges(st, *(b.value() for b in boxes))
        except ValueError:
            self.status.emit("The range is empty: 'to' must be larger than 'from'.")
        st.grid, st.axes, st.points = grid.isChecked(), axes.isChecked(), points.isChecked()
        item._plot_cache = None
        item.update()
        self.modified.emit()

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

        from markforge.calc.engine.model import to_text
        from tests.calc.smfile import dumps
        from markforge.calc.worksheet import Worksheet

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

        from tests.calc.smfile import loads

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
        from markforge.calc.engine.model import Paren, Row

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
        from markforge.calc.engine.display import display_value, display_text, unit_text
        from markforge.calc.engine.errors import SMathError
        from markforge.calc.engine.model import Row
        from markforge.calc.engine.parser import ParseError, parse_row

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

    def solve_selection(self) -> None:
        """Solve the expression (= 0, or an equation with the bold equals)
        for the variable under the cursor; the roots appear in a new region
        below (SMath: Calculation > Solve)."""
        from markforge.calc.engine import ast as A
        from markforge.calc.engine.model import Row
        from markforge.calc.engine.parser import ParseError, parse_row
        from tests.calc.smfile import ast_to_items

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

        self.leave_layer()
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
            g = self.scene_.geo
            self.scene_.render(painter, target, QRectF(0, k * g.STEP, g.W, g.H))
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
