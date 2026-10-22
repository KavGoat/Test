"""A spreadsheet section: a run of pages that is one sheet of grid.

The user's choices (docs/SPREADSHEET_DESIGN.md, phase 4): consecutive sheet
pages are one sheet that grows a page at a time; the columns that fit inside
the page's margins print and everything to their right is the scratch area,
never printed; page breaks are Excel's Page Break Preview (dashed blue where
they fall by themselves, solid blue where the user put them); the row
numbers and column letters always show on screen and print only when asked.

The run's cells are one :class:`SheetRunItem`, kept on the run's first page
and drawn across all of them: each page of the run is a slice of its rows
(ui/scene.py sets each frame's shape from :meth:`SheetRunItem.relayout`) and
the pages sit edge to edge, so on screen it is one continuous grid. Markups
on a sheet page belong to the cells under them and move with them.
"""
from __future__ import annotations

import bisect
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem

from ..core.typography import page_font
from ..sheet.pagination import HEADING_H as PRINT_HEADING_H
from ..sheet.pagination import HEADING_W as PRINT_HEADING_W
from ..sheet.pagination import options, paginate
from ..sheet.refs import col_letters
from .base import register_item
from .table import (EXCEL_GREEN, HEADING_BG, HEADING_H, HEADING_ON, ROWNUM_W, TableItem,
                    hidden_mark)

BREAK_BLUE = QColor("#2f6fd6")
NORMAL_BREAK = QColor("#5f6670")         # the workbook view's page breaks (Excel's Normal)
SCRATCH = QColor("#ececec")
PAGE_LABEL = QColor(150, 150, 150, 70)
DEFAULT_ROWS = 52


def _frozen(v):
    if isinstance(v, dict):
        return tuple(sorted((k, _frozen(x)) for k, x in v.items()))
    if isinstance(v, (list, tuple)):
        return tuple(_frozen(x) for x in v)
    return v


def _looks_in(sheet, a: int, b: int, last_col: int) -> tuple:
    """What conditional formatting makes of the cells of rows a to b (only
    those a rule covers), as something to compare."""
    from ..sheet.condfmt import looks_for
    looks = looks_for(sheet)
    seen = set()
    out = []
    for rule in sheet.cond_rules:
        for t, l, bottom, r in rule.get("ranges", []):
            for row in range(max(t, a), min(bottom, b) + 1):
                for col in range(l, min(r, last_col) + 1):
                    if (row, col) in seen:
                        continue
                    seen.add((row, col))
                    got = looks.look(row, col)
                    if got:
                        out.append((row, col, _frozen(got)))
    return tuple(sorted(out))


#: Excel's select-all corner: its triangle, and the triangle under the pointer
CORNER_MARK = QColor("#b6b6b6")
CORNER_HOT = QColor("#5f5f5f")
CORNER_HOT_BG = QColor("#e2e2e2")


def paint_corner(painter: QPainter, box: QRectF, hot: bool = False, everything: bool = False,
                 edge: Optional[QPen] = None) -> None:
    """Excel's select-all box where the row and column headings meet: the
    headings' grey, their edge, and a small triangle in its bottom right
    corner pointing there — darker under the pointer, Excel's green when
    the whole sheet is picked."""
    from PySide6.QtGui import QPolygonF
    painter.save()
    painter.fillRect(box, CORNER_HOT_BG if hot else HEADING_BG)
    if edge is not None:
        painter.setPen(edge)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(box)
    side = min(box.width(), box.height()) * 0.62
    inset = min(box.width(), box.height()) * 0.14
    right, bottom = box.right() - inset, box.bottom() - inset
    triangle = QPolygonF([QPointF(right, bottom - side), QPointF(right, bottom),
                          QPointF(right - side, bottom)])
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(EXCEL_GREEN if everything else (CORNER_HOT if hot else CORNER_MARK))
    painter.drawPolygon(triangle)
    painter.restore()


def run_frames_from(frame) -> list:
    """The frames of the run *frame* is in, first to last."""
    scene = frame.scene() if frame is not None else None
    run = getattr(getattr(frame, "page", None), "sheet", None)
    if scene is None or run is None:
        return []
    frames = list(getattr(scene, "frames", []) or [])
    if frame not in frames:
        return [frame]
    i = j = frames.index(frame)
    while i > 0 and getattr(frames[i - 1].page, "sheet", None) == run:
        i -= 1
    while j + 1 < len(frames) and getattr(frames[j + 1].page, "sheet", None) == run:
        j += 1
    return frames[i:j + 1]


def run_item_for(frame) -> Optional["SheetRunItem"]:
    """The cells of the run a sheet page is a page of."""
    run = getattr(getattr(frame, "page", None), "sheet", None)
    if run is None:
        return None
    for other in run_frames_from(frame):
        for item in other.markups():
            if isinstance(item, SheetRunItem) and item.uid == run:
                return item
    return None


@register_item
class SheetRunItem(TableItem):
    """The cells of a run of spreadsheet pages."""

    TYPE = "sheet_run"
    NAME = "Spreadsheet"
    SHEET_KIND = "sheet"
    SHEET_RUN = True
    _hold = False          # pages being deleted: the layout waits for the new pages
    break_drag = None      # y of a page break being dragged (screen only)
    vbreak_drag = None     # x of a page break across being dragged (screen only)
    area_drag = None       # [t, l, b, r] of a print area edge being dragged (screen only)

    def __init__(self):
        super().__init__(DEFAULT_ROWS, 1)
        self.paging = None
        self._tops: list = []           # each page's first y in the grid
        self._lefts: list = []          # and its first x (pages across)
        self._anchors: Optional[dict] = None
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        # told what part is being repainted: a long sheet draws only its rows on screen
        self.setFlag(QGraphicsItem.ItemUsesExtendedStyleOption, True)
        self.setZValue(-2)
        self.setAcceptHoverEvents(True)      # (the select-all corner lights up)

    def set_locked(self, locked: bool) -> None:
        self.locked = bool(locked)       # never picked up: it is the pages' own grid

    def _start_empty(self, sheet) -> None:
        return                           # a fresh sheet: no borders, gridlines on screen

    # -- the run -----------------------------------------------------------------------------
    def run_frames(self) -> list:
        frame = self._page_frame()
        return run_frames_from(frame) if frame is not None else []

    def _attach(self) -> None:
        had = self.sheet is not None
        super()._attach()
        if self.sheet is not None and not had:
            self.sheet.on_shift.append(self._shifting)
            # its pages take their shape once everything is on the canvas
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._settle_soon)

    def _detach(self) -> None:
        if self.sheet is not None and self._shifting in self.sheet.on_shift:
            self.sheet.on_shift.remove(self._shifting)
        super()._detach()

    def _settle_soon(self) -> None:
        try:
            if self.scene() is None or self.sheet is None:
                return
        except RuntimeError:
            return                       # gone already
        self.relayout()

    @property
    def size(self) -> tuple:
        paging = self.paging
        if paging is None or not paging.slices:
            return (DEFAULT_ROWS, 24)
        rows, cols = paging.slices[-1][1] + 1, paging.shown_cols
        if self.alone:
            # shown alone (the workbook view): the grid goes on past its
            # pages as far as the window has been scrolled, as Excel's does
            extent = getattr(self.scene(), "sheet_extent", (0, 0))
            rows, cols = max(rows, extent[0]), max(cols, extent[1])
        return (rows, cols)

    @property
    def sheet_rows(self) -> int:
        """The rows the sheet has (its pages hold), whatever the grid shows."""
        paging = self.paging
        return paging.slices[-1][1] + 1 if paging is not None and paging.slices else DEFAULT_ROWS

    @property
    def alone(self) -> bool:
        """Whether this sheet is shown alone, filling the canvas (Excel's
        Normal view: ui/sheetview.py) rather than on its pages."""
        try:
            scene = self.scene()
        except RuntimeError:
            return False
        return scene is not None and getattr(scene, "sheet_view", None) == self.uid

    def grid_rect(self) -> QRectF:
        """The grid and its row and column headings, in its own coordinates."""
        return self.local_rect().adjusted(-ROWNUM_W, -HEADING_H, 0, 0)

    def relayout(self) -> bool:
        """Give each page of the run its slice; True when the sheet needs
        more pages than the run has (ui/sheetpages.py adds them)."""
        frames = self.run_frames()
        sheet = self.sheet
        if not frames or sheet is None or self._hold:
            return False
        anchors = self._anchors if self._anchors is not None else self.capture_anchors()
        self._anchors = None
        setup = frames[0].page.setup
        if (sheet.page or {}).get("rows") is None:
            # a sheet made before rows were counted: it has the rows its
            # pages hold now, and from here on its pages follow its rows
            from ..sheet.pagination import rows_of
            page = dict(sheet.page or {})
            page["rows"] = rows_of(sheet, setup, len(frames))
            sheet.page = page
        self.paging = paging = paginate(sheet, setup, len(frames))
        self.prepareGeometryChange()
        self._edges = None
        xs, ys = self.edges()
        self._tops = []
        self._lefts = []
        groups = paging.groups
        for k, frame in enumerate(frames):
            if k < paging.pages:
                # pages down, then over: each page across is a band of columns
                # beside the one before (the first from column A, the last to
                # the end of the scratch area)
                i, j = paging.page_of(k)
                a, b = paging.slices[i]
                c0, c1 = groups[j]
                top, height = ys[a], ys[b + 1] - ys[a]
                left = 0.0 if j == 0 else xs[c0]
                right = xs[-1] if j == len(groups) - 1 else xs[c1 + 1]
            else:
                top, height, left, right = ys[-1], 1.0, 0.0, xs[-1]
            self._tops.append(top)
            self._lefts.append(left)
            frame.sheet_offset = QPointF(left, top)
            frame.set_sheet_rect(QRectF(0, 0, max(right - left, 1.0), max(height, 1.0)))
        scene = self.scene()
        if scene is not None and hasattr(scene, "layout_pages"):
            scene.layout_pages()
        self.restore_anchors(anchors)
        self.update()
        if scene is not None:
            for view in scene.views():
                headings = getattr(view, "sheet_headings", None)
                if headings is not None:
                    headings.refresh_soon()
        return paging.pages > len(frames)

    def layout_changed(self) -> None:
        self.relayout()

    def _restored(self, laid_out: bool) -> None:
        # its pages take their slices again (what is typed decides how many
        # pages it needs); the markups were put back where they were
        # recorded, so they stay where they are
        self._anchors = {}
        self.relayout()
        if self._anchors == {}:
            self._anchors = None             # (not laid out yet: held for its pages)
        super()._restored(False)

    def _values_changed(self, keys: set) -> None:
        sheet = self.sheet
        if sheet is None:
            return
        if ("layout", sheet.id) in keys:
            self.relayout()
            return
        if any(k[0] == sheet.id for k in keys):
            self.update()

    def page_index_of_row(self, row: int, col: int = 0) -> int:
        """The run's page cell (row, col) is on (the last across for scratch)."""
        paging = self.paging
        if paging is None:
            return 0
        i = len(paging.slices) - 1
        for k, (a, b) in enumerate(paging.slices):
            if a <= row <= b:
                i = k
                break
        j = len(paging.groups) - 1
        for k, (c0, c1) in enumerate(paging.groups):
            if col <= c1:
                j = k
                break
        return paging.index_of(i, j)

    # -- markups move with their cells --------------------------------------------------------
    def _grid_cell(self, x: float, y: float) -> tuple:
        """(row, col) of a grid point from the sheet's sizes (no end to it)."""
        xs, ys = self.edges()
        if y < ys[-1]:
            row = max(0, bisect.bisect_right(ys, y) - 1)
            top = ys[row]
        else:
            row, top = len(ys) - 1, ys[-1]
        if x < xs[-1]:
            col = max(0, bisect.bisect_right(xs, x) - 1)
            left = xs[col]
        else:
            col, left = len(xs) - 1, xs[-1]
        return row, col, x - left, y - top

    def _cell_point(self, row: int, col: int) -> QPointF:
        xs, ys = self.edges()
        sheet = self.sheet
        y = ys[min(row, len(ys) - 1)] + sum(sheet.height(r) for r in range(len(ys) - 1, row))
        x = xs[min(col, len(xs) - 1)] + sum(sheet.width(c) for c in range(len(xs) - 1, col))
        return QPointF(x, y)

    def cell_rect(self, row: int, col: int, merged: bool = True) -> QRectF:
        rows, cols = self.size
        if row < rows and col < cols:
            return super().cell_rect(row, col, merged)
        # past the last page (where typing adds one)
        point = self._cell_point(row, col)
        return QRectF(point.x(), point.y(), self.sheet.width(col), self.sheet.height(row))

    def block_rect(self, top, left, bottom, right) -> QRectF:
        return self.cell_rect(top, left, False).united(self.cell_rect(bottom, right, False))

    def _markups(self) -> list:
        return [m for frame in self.run_frames() for m in frame.markups() if m is not self]

    def capture_anchors(self) -> dict:
        """Each markup on the run's pages: the cell its corner is in."""
        anchors = {}
        if self.paging is None:
            return anchors
        for item in self._markups():
            point = self.mapFromScene(item.scenePos())
            anchors[item] = list(self._grid_cell(point.x(), point.y()))
        return anchors

    def _shifting(self, axis: str, at: int, delta: int) -> None:
        """Rows or columns going in or out: the markups' cells move."""
        if self._anchors is None:
            self._anchors = self.capture_anchors()
        k = 0 if axis == "row" else 1
        for anchor in self._anchors.values():
            i = anchor[k]
            if delta > 0 and i >= at:
                anchor[k] = i + delta
            elif delta < 0:
                gone = -delta
                if at <= i < at + gone:
                    anchor[k] = at                    # its cells went: it stays where they were
                    anchor[k + 2] = 0.0
                elif i >= at + gone:
                    anchor[k] = i - gone

    def restore_anchors(self, anchors: dict) -> None:
        frames = self.run_frames()
        if not anchors or not frames:
            return
        from shiboken6 import isValid

        for item, (row, col, dx, dy) in anchors.items():
            if not isValid(item):
                continue
            point = self._cell_point(row, col) + QPointF(dx, dy)
            k = min(self.page_index_of_row(row, col), len(frames) - 1)
            frame = frames[k]
            target = frame.mapFromItem(self, point)
            if item.parentItem() is not frame:
                item.setParentItem(frame)
            if (target - item.pos()).manhattanLength() > 0.01:
                item.setPos(target)

    # -- on screen ------------------------------------------------------------------------------------
    def chrome_rect(self) -> QRectF:
        r = self.local_rect()
        return r.adjusted(-ROWNUM_W, -HEADING_H, 0, 0)

    def tab_rect(self) -> QRectF:
        return QRectF(0, 0, 0, 0)

    def shape(self):
        from PySide6.QtGui import QPainterPath
        path = QPainterPath()
        path.addRect(self.chrome_rect())
        return path

    def boundingRect(self) -> QRectF:
        # room above the headings for the sheet's name tag
        return self.chrome_rect().adjusted(-2, -14, 16, 4)

    _on_paper = False

    def _gridlines_shown(self, printing: bool) -> bool:
        if printing or self._on_paper:
            return bool(options(self.sheet)["print_gridlines"])
        return self.sheet.show_gridlines

    def _printed_cols(self) -> tuple:
        paging = self.paging
        return (paging.first_col, paging.last_col) if paging else (0, 0)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        frame = self._page_frame()
        if self.sheet is None or self.paging is None:
            return
        if getattr(frame, "print_mode", False):
            return                      # paper is drawn page by page (paint_page)
        xs, ys = self.edges()
        rows, cols = self.size
        exposed = option.exposedRect if option is not None else self.boundingRect()
        r0 = max(0, bisect.bisect_right(ys, exposed.top()) - 2)
        r1 = min(rows - 1, bisect.bisect_right(ys, exposed.bottom()) + 1)
        painter.save()
        if not self._paint_bands(painter, r0, r1):
            self._paint_rows(painter, r0, r1)
        painter.restore()
        painter.save()
        self._paint_breaks(painter)
        self._range = (r0, r1, 0, cols - 1)
        try:
            self._paint_marks(painter)
        finally:
            self._range = None
        painter.restore()
        painter.save()
        self._paint_headings(painter, r0, r1)
        from . import nametags
        if nametags.shown(self) and not self.alone:
            # the sheet's name, above its first page's top-left corner
            nametags.draw_tag(painter, QPointF(-ROWNUM_W, -HEADING_H - 0.8), self.name,
                              nametags.OUTER_PT, above=True)
        if self.opened:
            self._paint_selection(painter)
            if self.overlay is not None:
                self.overlay(painter)
        painter.restore()

    def _paint_rows(self, painter: QPainter, r0: int, r1: int) -> None:
        """The paper and the cells of rows r0 to r1, drawn afresh."""
        self._paint_paper(painter, r0, r1)
        self._range = (r0, r1, 0, self.size[1] - 1)
        try:
            self.paint_visible(painter)
        finally:
            self._range = None

    # -- bands: the cells drawn once, as pictures, until they change ----------------------------
    # Drawing a screenful of cells is a thousand formatted texts, fills and
    # borders, and with the view repainting whole (OpenGL) that was every
    # frame of a scroll or a pan: four frames a second on a 3000-row
    # workbook (2026-10-10). The paper and cells are kept as pictures of
    # BAND rows each, at the scale they are shown, and drawn again only when
    # what is in them changes — known by comparing what they were drawn from.
    BAND = 24
    BAND_PIXELS = 32_000_000          # all bands kept, together (about 128 MB)

    def _band_key(self, a: int, b: int) -> tuple:
        """Everything a band's picture is drawn from."""
        sheet = self.sheet
        xs, ys = self.edges()
        cells = sheet.cells
        content = []
        for r, c in sheet.positions_in(a, 0, b, self.size[1] - 1):
            cell = cells[(r, c)]
            content.append((r, c, cell.style, type(cell.value), cell.value))
        paging = self.paging
        opts = options(sheet)
        # what conditional formatting makes of the band's cells — not every
        # rule against every value change, which drew all the bands again
        # for any edit (the user's seismic workbook, 2026-10-19)
        rules = _looks_in(sheet, a, b, self.size[1] - 1) if sheet.cond_rules else None
        from .nametags import named_blocks, shown
        tags = (shown(self), tuple(named_blocks(sheet)), self.alone, self._page_numbers(),
                self.sheet_rows)
        return (tuple(xs), tuple(ys[a:b + 2]), content, [tuple(m) for m in sheet.merges], tags,
                paging.first_col, paging.last_col, paging.print_rows, tuple(paging.slices),
                tuple(paging.groups),
                sheet.show_gridlines, opts["print_gridlines"], self._on_paper, rules,
                len(sheet.workbook.styles))

    def _zoom_gliding(self) -> bool:
        """A wheel zoom is under way in a view of this sheet (view.py)."""
        scene = self.scene()
        if scene is None:
            return False
        for view in scene.views():
            timer = getattr(view, "_zoom_settled", None)
            if timer is not None and timer.isActive():
                return True
        return False

    def _paint_bands(self, painter: QPainter, r0: int, r1: int) -> bool:
        """Draw rows r0 to r1 from the bands' pictures; False when they
        should be drawn afresh instead (a turned page, or so close in that a
        picture would be too big to keep).

        The screen always shows the pictures, never a mix: text drawn into a
        picture lands a shade differently from text drawn straight onto the
        screen, and swapping one for the other after a zoom made everything
        jump (the user, 2026-10-11). While a wheel zoom glides, the pictures
        already drawn are stretched — as a PDF page's are — and drawn again
        sharp once it stops, instead of every cell being drawn afresh for
        every frame of the glide (the zoom's stutter)."""
        from collections import OrderedDict

        from ..ui.scene import _draw_on_the_pixel_grid, _painted_scale
        shape = painter.transform()
        if abs(shape.m12()) > 1e-9 or abs(shape.m21()) > 1e-9:
            return False
        scale = round(_painted_scale(painter), 4)
        xs, ys = self.edges()
        bands = self.__dict__.get("_bands")
        kept = self.__dict__.get("_bands_scale")
        stretch = bands is not None and kept is not None and kept != scale and \
            int(round(xs[-1] * kept)) <= 8192 and self._zoom_gliding()
        if not stretch:
            if int(round(xs[-1] * scale)) <= 0 or int(round(xs[-1] * scale)) > 8192:
                return False                       # so close in that few cells show
            if bands is None or kept != scale:
                bands = self._bands = OrderedDict()
                self._bands_scale = scale
        first, last = r0 // self.BAND, r1 // self.BAND
        for k in range(first, last + 1):
            entry = self._band(k)
            if entry is None:
                continue
            a, b = entry[2]
            where = QRectF(0, ys[a], xs[-1], ys[b + 1] - ys[a])
            if stretch:
                painter.save()
                painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
                painter.drawPixmap(where, entry[1], QRectF(entry[1].rect()))
                painter.restore()
            else:
                _draw_on_the_pixel_grid(painter, where, entry[1])
        used = sum(e[1].width() * e[1].height() for e in bands.values())
        while used > self.BAND_PIXELS and len(bands) > 1:
            _k, (_key, old, _rows) = bands.popitem(last=False)
            used -= old.width() * old.height()
        if stretch:
            return True                            # the sharp ones once the zoom stops
        # the bands just out of view, drawn while nothing else is happening
        self._ahead = [k for k in (last + 1, first - 1, last + 2) if k >= 0]
        if not self.__dict__.get("_ahead_queued"):
            self._ahead_queued = True
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._draw_ahead)
        return True

    def _band(self, k: int, keep_order: bool = True):
        """(key, picture, (first row, last row)) of band k at the bands'
        scale, drawn now if what it shows has changed; None past the end."""
        from PySide6.QtGui import QPixmap
        bands = self._bands
        scale = self._bands_scale
        xs, ys = self.edges()
        a, b = k * self.BAND, min(self.size[0] - 1, k * self.BAND + self.BAND - 1)
        if a > b:
            return None
        top, bottom = ys[a], ys[b + 1]
        width = int(round(xs[-1] * scale))
        height = int(round((bottom - top) * scale))
        if height <= 0 or width <= 0:
            return None
        key = self._band_key(a, b)
        entry = bands.get(k)
        if entry is None or entry[0] != key:
            picture = QPixmap(width, height)
            picture.fill(QColor("white"))
            p = QPainter(picture)
            p.scale(width / xs[-1], height / (bottom - top))
            p.translate(0, -top)
            p.setClipRect(QRectF(0, top, xs[-1], bottom - top))
            # a merged cell reaching into the band from above is drawn from its top
            start = min([a] + [m[0] for m in self.sheet.merges if m[0] < a <= m[2]])
            self._paint_rows(p, start, b)
            p.end()
            entry = (key, picture, (a, b))
        bands[k] = entry
        if keep_order:
            bands.move_to_end(k)
        return entry

    def _draw_ahead(self) -> None:
        self._ahead_queued = False
        try:
            if self.scene() is None or self.sheet is None or self.paging is None:
                return
        except RuntimeError:                   # gone with its page
            return
        bands = self.__dict__.get("_bands")
        if bands is None:
            return
        for k in self.__dict__.get("_ahead", []):
            if k in bands or self._band(k, keep_order=False) is None:
                continue                               # drawn already, or past the end
            bands.move_to_end(k, last=False)          # first to go if room is short
            return                                     # one a turn: the next paint asks again

    def _page_numbers(self) -> tuple:
        """Each of the run's pages: its number as printed (the pages that
        print counted, Document.printed_numbers), or 0 when it doesn't
        print (no "Page N" on it)."""
        frames = self.run_frames()
        document = getattr(frames[0], "document", None) if frames else None
        if document is None:
            return tuple(0 for _f in frames)
        numbers = document.printed_numbers()
        where = {id(page): k for k, page in enumerate(document.pages)}
        out = []
        for frame in frames:
            k = where.get(id(frame.page))
            out.append((numbers[k] or 0) if k is not None else 0)
        return tuple(out)

    def _paint_paper(self, painter: QPainter, r0: int, r1: int) -> None:
        """White where it prints, grey for the scratch area; "Page N", the
        page's number as printed (none on a page that doesn't print). Shown
        alone (the workbook view, Excel's Normal view) it is all white, the
        thin lines saying where the pages fall, and the numbers stay."""
        xs, ys = self.edges()
        paging = self.paging
        numbers = self._page_numbers()
        c0, c1 = self._printed_cols()
        area = paging.print_rows
        band = QRectF(0, ys[r0], xs[-1], ys[r1 + 1] - ys[r0])
        painter.fillRect(band, QColor("white") if self.alone else SCRATCH)
        top = ys[area[0]] if area else 0.0
        last = self.sheet_rows
        bottom = ys[min(area[1] + 1, len(ys) - 1)] if area else ys[min(last, len(ys) - 1)]
        printed = QRectF(xs[c0], top, xs[c1 + 1] - xs[c0], bottom - top)
        if not self.alone:
            painter.fillRect(printed.intersected(band), QColor("white"))
        font = QFont(page_font("", 40.0, True))
        painter.setFont(font)
        painter.setPen(PAGE_LABEL)
        for i, (a, b) in enumerate(paging.slices):
            if b < r0 or a > r1:
                continue
            for j, (g0, g1) in enumerate(paging.groups):
                if area:                     # the label in what prints of the page
                    a, b = max(a, area[0]), min(b, area[1])
                    if a > b:
                        continue
                box = QRectF(xs[g0], ys[a], xs[g1 + 1] - xs[g0], ys[b + 1] - ys[a])
                if box.height() < 52:
                    continue                 # a page of a row or two: no room to say so
                k = paging.index_of(i, j)
                number = numbers[k] if k < len(numbers) else 0
                if number:                   # (a page that doesn't print has none)
                    painter.drawText(box, Qt.AlignCenter, f"Page {number}")

    def _paint_breaks(self, painter: QPainter) -> None:
        """Excel's Page Break Preview lines: the printed area's edge, and a
        line where each page ends (dashed when it fell there by itself)."""
        xs, ys = self.edges()
        paging = self.paging
        c0, c1 = self._printed_cols()
        painter.setRenderHint(QPainter.Antialiasing, False)
        area = paging.print_rows
        if self.alone:
            # Excel's Normal view: a set print area outlined in a thin solid
            # line, the pages' breaks thin and dashed (one put there by
            # hand solid), never the Page Break Preview's blue
            solid = QPen(NORMAL_BREAK, 1.0)
            solid.setCosmetic(True)
            dashed = QPen(NORMAL_BREAK, 1.0, Qt.DashLine)
            dashed.setCosmetic(True)
            edge = solid if area or options(self.sheet)["print_area"] else dashed
        else:
            solid = QPen(BREAK_BLUE, 2.0)
            solid.setCosmetic(True)
            dashed = QPen(BREAK_BLUE, 2.0, Qt.DashLine)
            dashed.setCosmetic(True)
            edge = solid
        top = ys[area[0]] if area else 0.0
        bottom = ys[min(area[1] + 1, len(ys) - 1)] if area else \
            ys[min(self.sheet_rows, len(ys) - 1)]
        painter.setPen(edge)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(xs[c0], top, xs[c1 + 1] - xs[c0], bottom - top))
        for k, (a, _b) in enumerate(paging.slices):
            if k == 0:
                continue
            painter.setPen(solid if a in paging.manual else dashed)
            painter.drawLine(QPointF(xs[c0], ys[a]), QPointF(xs[c1 + 1], ys[a]))
        for g0, _g1 in paging.groups[1:]:
            painter.setPen(solid if g0 in paging.col_manual else dashed)
            painter.drawLine(QPointF(xs[g0], top), QPointF(xs[g0], bottom))
        if self.area_drag is not None:
            top, first, bottom, last = self.area_drag
            moving = QPen(BREAK_BLUE, 3.0)
            moving.setCosmetic(True)
            painter.setPen(moving)
            painter.drawRect(QRectF(xs[first], ys[top], xs[min(last + 1, len(xs) - 1)] - xs[first],
                                    ys[min(bottom + 1, len(ys) - 1)] - ys[top]))
        if self.break_drag is not None:
            moving = QPen(BREAK_BLUE, 3.0)
            moving.setCosmetic(True)
            painter.setPen(moving)
            painter.drawLine(QPointF(xs[c0], self.break_drag), QPointF(xs[c1 + 1], self.break_drag))
        if self.vbreak_drag is not None:
            moving = QPen(BREAK_BLUE, 3.0)
            moving.setCosmetic(True)
            painter.setPen(moving)
            painter.drawLine(QPointF(self.vbreak_drag, top), QPointF(self.vbreak_drag, bottom))

    def _paint_headings(self, painter: QPainter, r0: int, r1: int) -> None:
        """Row numbers and column letters, always (the user's choice)."""
        xs, ys = self.edges()
        rows, cols = self.size
        sel = self.selection if self.opened else None
        painter.setFont(page_font("", 8.0))
        painter.setRenderHint(QPainter.Antialiasing, False)
        grid = QPen(QColor("#bdbdbd"), 0)
        grid.setCosmetic(True)
        painter.setBrush(Qt.NoBrush)
        marks = []          # hidden columns and rows: drawn over their neighbours
        # only the columns in view: a workbook with a thousand hidden columns
        # past its last drew a thousand headings and marks a frame
        # (the user's seismic workbook, 2026-10-19)
        first, last = 0, cols - 1
        inverse, ok = painter.worldTransform().inverted()
        device = painter.device()
        if ok and device is not None and device.width() > 0:
            seen = inverse.mapRect(QRectF(0, 0, device.width(), device.height()))
            import bisect
            first = max(0, bisect.bisect_right(xs, seen.left()) - 2)
            last = min(cols - 1, bisect.bisect_right(xs, seen.right()) + 1)
        marked = set()
        for c in range(first, last + 1):
            cell = QRectF(xs[c], -HEADING_H, xs[c + 1] - xs[c], HEADING_H)
            if cell.width() <= 0:
                if ("col", xs[c]) not in marked:          # one mark where several are hidden
                    marked.add(("col", xs[c]))
                    marks.append((cell, "col"))       # Excel's double line
                continue
            on = sel is not None and sel[1] <= c <= sel[3]
            painter.fillRect(cell, HEADING_ON if on else HEADING_BG)
            painter.setPen(grid)
            painter.drawRect(cell)
            painter.setPen(EXCEL_GREEN if on else QColor("#444444"))
            painter.drawText(cell, Qt.AlignCenter, col_letters(c))
        for r in range(r0, r1 + 1):
            cell = QRectF(-ROWNUM_W, ys[r], ROWNUM_W, ys[r + 1] - ys[r])
            if cell.height() <= 0:
                if ("row", ys[r]) not in marked:
                    marked.add(("row", ys[r]))
                    marks.append((cell, "row"))
                continue
            on = sel is not None and sel[0] <= r <= sel[2]
            painter.fillRect(cell, HEADING_ON if on else HEADING_BG)
            painter.setPen(grid)
            painter.drawRect(cell)
            painter.setPen(EXCEL_GREEN if on else QColor("#444444"))
            painter.drawText(cell, Qt.AlignCenter, str(r + 1))
        for cell, axis in marks:
            hidden_mark(painter, cell, axis)
        paint_corner(painter, self.corner_rect(), self.corner_hot, self.everything_picked(),
                     grid)

    # -- Excel's select-all corner ------------------------------------------------------------
    corner_hot = False                   # the pointer over it (hover)

    def corner_rect(self) -> QRectF:
        return QRectF(-ROWNUM_W, -HEADING_H, ROWNUM_W, HEADING_H)

    def everything_picked(self) -> bool:
        sel = self.selection if self.opened else None
        rows, cols = self.size
        return sel is not None and tuple(sel) == (0, 0, rows - 1, cols - 1)

    def hoverMoveEvent(self, event) -> None:
        self._hover_corner(self.corner_rect().contains(event.pos()))
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self._hover_corner(False)
        super().hoverLeaveEvent(event)

    def _hover_corner(self, hot: bool) -> None:
        if hot != self.corner_hot:
            self.corner_hot = hot
            self.update(self.corner_rect())

    # -- on paper ------------------------------------------------------------------------------------
    def paint_page(self, painter: QPainter, frame) -> Optional[tuple]:
        """Draw *frame*'s slice of the grid onto its paper (painter in
        points on the paper). Returns (the slice in the frame's own
        coordinates, where it went on the paper) for the markups over it,
        or None when nothing of the sheet prints on this page."""
        frames = self.run_frames()
        paging = self.paging
        if paging is None or frame not in frames:
            return None
        k = frames.index(frame)
        if k >= paging.pages:
            return None
        opts = options(self.sheet)
        i, j = paging.page_of(k)
        a, b = paging.slices[i]
        if paging.print_rows:
            a, b = max(a, paging.print_rows[0]), min(b, paging.print_rows[1])
            if a > b:
                return None
        xs, ys = self.edges()
        c0, c1 = paging.groups[j]
        scale = paging.scale
        left, top, width, height = paging.printable
        heads = bool(opts["print_headings"])
        hw = PRINT_HEADING_W if heads else 0.0
        hh = PRINT_HEADING_H if heads else 0.0
        # Print Titles: rows to repeat on every page whose rows start below
        # them, columns to repeat at the left of a print area to their right
        titles = paging.titles
        title_rows = titles if titles and a > titles[1] else None
        th = (ys[title_rows[1] + 1] - ys[title_rows[0]]) if title_rows else 0.0
        tc = paging.title_cols if paging.title_cols and c0 > paging.title_cols[1] else None
        tw = (xs[tc[1] + 1] - xs[tc[0]]) if tc else 0.0
        w = xs[c1 + 1] - xs[c0]
        h = ys[b + 1] - ys[a]
        total_w = (w + tw) * scale + hw
        total_h = (h + th) * scale + hh
        x0 = left + ((width + hw - total_w) / 2 if opts["center_h"] else 0.0)
        y0 = top + ((height + hh - total_h) / 2 if opts["center_v"] else 0.0)
        gx, gy = x0 + hw, y0 + hh
        blocks = []
        if title_rows:
            blocks.append((title_rows[0], title_rows[1], gy))
        blocks.append((a, b, gy + th * scale))
        across = [(c0, c1, gx + tw * scale)]
        if tc:
            across.insert(0, (tc[0], tc[1], gx))
        for ra, rb, at in blocks:
            for ca, cb, left_at in across:
                painter.save()
                painter.translate(left_at, at)
                painter.scale(scale, scale)
                painter.translate(-xs[ca], -ys[ra])
                painter.setClipRect(QRectF(xs[ca], ys[ra], xs[cb + 1] - xs[ca], ys[rb + 1] - ys[ra]),
                                    Qt.IntersectClip)
                self._range = (ra, rb, ca, cb)
                self._on_paper = True
                try:
                    self.paint_content(painter)
                finally:
                    self._range = None
                    self._on_paper = False
                painter.restore()
            if heads:
                self._print_headings(painter, ra, rb, c0, c1, x0, at, scale, hw, hh,
                                     first=(at == gy), title_cols=tc)
        if k == 0:
            from . import nametags
            if nametags.shown(self):
                # the sheet's name above its first page's top-left corner
                nametags.draw_tag(painter, QPointF(x0, y0 - 0.8), self.name,
                                  nametags.OUTER_PT, above=True)
        inner = QRectF(gx + tw * scale, gy + th * scale, w * scale, h * scale)
        source = QRectF(xs[c0] - self._lefts[k], ys[a] - self._tops[k], w, h)
        return source, inner

    def _print_headings(self, painter, ra, rb, c0, c1, x0, at, scale, hw, hh, first,
                        title_cols=None) -> None:
        xs, ys = self.edges()
        painter.save()
        painter.setFont(page_font("", 7.0))
        pen = QPen(QColor("#808080"), 0.4)
        if first:
            # the repeated columns first, then the print area's, side by side
            shown = (list(range(title_cols[0], title_cols[1] + 1)) if title_cols else []) + \
                list(range(c0, c1 + 1))
            x = x0 + hw
            for c in shown:
                cell = QRectF(x, at - hh, (xs[c + 1] - xs[c]) * scale, hh)
                x += cell.width()
                if cell.width() <= 0:
                    continue
                painter.setPen(pen)
                painter.drawRect(cell)
                painter.setPen(QColor("#000000"))
                painter.drawText(cell, Qt.AlignCenter, col_letters(c))
        for r in range(ra, rb + 1):
            cell = QRectF(x0, at + (ys[r] - ys[ra]) * scale, hw, (ys[r + 1] - ys[r]) * scale)
            if cell.height() <= 0:
                continue
            painter.setPen(pen)
            painter.drawRect(cell)
            painter.setPen(QColor("#000000"))
            painter.drawText(cell, Qt.AlignCenter, str(r + 1))
        painter.restore()

    def summary(self) -> str:
        return f"{self.name} — {len(self.run_frames())} page(s)"
