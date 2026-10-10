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
from .table import (EXCEL_GREEN, HEADING_BG, HEADING_H, HEADING_ON, ROWNUM_W, TableItem)

BREAK_BLUE = QColor("#2f6fd6")
SCRATCH = QColor("#ececec")
PAGE_LABEL = QColor(150, 150, 150, 70)
DEFAULT_ROWS = 52


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
    area_drag = None       # [t, l, b, r] of a print area edge being dragged (screen only)

    def __init__(self):
        super().__init__(DEFAULT_ROWS, 1)
        self.paging = None
        self._tops: list = []           # each page's first y in the grid
        self._anchors: Optional[dict] = None
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        # told what part is being repainted: a long sheet draws only its rows on screen
        self.setFlag(QGraphicsItem.ItemUsesExtendedStyleOption, True)
        self.setZValue(-2)

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
        return (paging.slices[-1][1] + 1, paging.shown_cols)

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
        self.paging = paging = paginate(sheet, setup, len(frames))
        self.prepareGeometryChange()
        self._edges = None
        xs, ys = self.edges()
        self._tops = []
        width = xs[-1]
        for k, frame in enumerate(frames):
            if k < len(paging.slices):
                a, b = paging.slices[k]
                top, height = ys[a], ys[b + 1] - ys[a]
            else:
                top, height = ys[-1], 1.0
            self._tops.append(top)
            frame.set_sheet_rect(QRectF(0, 0, width, max(height, 1.0)))
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

    def _values_changed(self, keys: set) -> None:
        sheet = self.sheet
        if sheet is None:
            return
        if ("layout", sheet.id) in keys:
            self.relayout()
            return
        if any(k[0] == sheet.id for k in keys):
            self.update()

    def page_index_of_row(self, row: int) -> int:
        paging = self.paging
        if paging is None:
            return 0
        for k, (a, b) in enumerate(paging.slices):
            if a <= row <= b:
                return k
        return len(paging.slices) - 1

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
            k = min(self.page_index_of_row(row), len(frames) - 1)
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
        return self.chrome_rect().adjusted(-2, -2, 16, 4)

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
        self._paint_paper(painter, r0, r1)
        self._range = (r0, r1, 0, cols - 1)
        try:
            self.paint_visible(painter)
        finally:
            self._range = None
        painter.restore()
        painter.save()
        self._paint_breaks(painter)
        self._paint_marks(painter)
        painter.restore()
        painter.save()
        self._paint_headings(painter, r0, r1)
        if self.opened:
            self._paint_selection(painter)
            if self.overlay is not None:
                self.overlay(painter)
        painter.restore()

    def _paint_paper(self, painter: QPainter, r0: int, r1: int) -> None:
        """White where it prints, grey for the scratch area; "Page N"."""
        xs, ys = self.edges()
        paging = self.paging
        c0, c1 = self._printed_cols()
        area = paging.print_rows
        painter.fillRect(QRectF(0, ys[r0], xs[-1], ys[r1 + 1] - ys[r0]), SCRATCH)
        top = ys[area[0]] if area else 0.0
        bottom = ys[min(area[1] + 1, len(ys) - 1)] if area else ys[-1]
        printed = QRectF(xs[c0], top, xs[c1 + 1] - xs[c0], bottom - top)
        painter.fillRect(printed.intersected(QRectF(0, ys[r0], xs[-1], ys[r1 + 1] - ys[r0])),
                         QColor("white"))
        font = QFont(page_font("", 40.0, True))
        painter.setFont(font)
        painter.setPen(PAGE_LABEL)
        for k, (a, b) in enumerate(paging.slices):
            if b < r0 or a > r1:
                continue
            box = QRectF(xs[c0], ys[a], xs[c1 + 1] - xs[c0], ys[b + 1] - ys[a])
            painter.drawText(box, Qt.AlignCenter, f"Page {k + 1}")

    def _paint_breaks(self, painter: QPainter) -> None:
        """Excel's Page Break Preview lines: the printed area's edge, and a
        line where each page ends (dashed when it fell there by itself)."""
        xs, ys = self.edges()
        paging = self.paging
        c0, c1 = self._printed_cols()
        painter.setRenderHint(QPainter.Antialiasing, False)
        solid = QPen(BREAK_BLUE, 2.0)
        solid.setCosmetic(True)
        dashed = QPen(BREAK_BLUE, 2.0, Qt.DashLine)
        dashed.setCosmetic(True)
        area = paging.print_rows
        top = ys[area[0]] if area else 0.0
        bottom = ys[min(area[1] + 1, len(ys) - 1)] if area else ys[-1]
        painter.setPen(solid)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(xs[c0], top, xs[c1 + 1] - xs[c0], bottom - top))
        for k, (a, _b) in enumerate(paging.slices):
            if k == 0:
                continue
            painter.setPen(solid if a in paging.manual else dashed)
            painter.drawLine(QPointF(xs[c0], ys[a]), QPointF(xs[c1 + 1], ys[a]))
        if self.area_drag is not None:
            t, l, b, r = self.area_drag
            moving = QPen(BREAK_BLUE, 3.0)
            moving.setCosmetic(True)
            painter.setPen(moving)
            painter.drawRect(QRectF(xs[l], ys[t], xs[min(r + 1, len(xs) - 1)] - xs[l],
                                    ys[min(b + 1, len(ys) - 1)] - ys[t]))
        if self.break_drag is not None:
            moving = QPen(BREAK_BLUE, 3.0)
            moving.setCosmetic(True)
            painter.setPen(moving)
            painter.drawLine(QPointF(xs[c0], self.break_drag), QPointF(xs[c1 + 1], self.break_drag))

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
        for c in range(cols):
            cell = QRectF(xs[c], -HEADING_H, xs[c + 1] - xs[c], HEADING_H)
            if cell.width() <= 0:
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
                continue
            on = sel is not None and sel[0] <= r <= sel[2]
            painter.fillRect(cell, HEADING_ON if on else HEADING_BG)
            painter.setPen(grid)
            painter.drawRect(cell)
            painter.setPen(EXCEL_GREEN if on else QColor("#444444"))
            painter.drawText(cell, Qt.AlignCenter, str(r + 1))
        corner = QRectF(-ROWNUM_W, -HEADING_H, ROWNUM_W, HEADING_H)
        painter.fillRect(corner, HEADING_BG)
        painter.setPen(grid)
        painter.drawRect(corner)

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
        if k >= len(paging.slices):
            return None
        opts = options(self.sheet)
        a, b = paging.slices[k]
        if paging.print_rows:
            a, b = max(a, paging.print_rows[0]), min(b, paging.print_rows[1])
            if a > b:
                return None
        xs, ys = self.edges()
        c0, c1 = paging.first_col, paging.last_col
        scale = paging.scale
        left, top, width, height = paging.printable
        heads = bool(opts["print_headings"])
        hw = PRINT_HEADING_W if heads else 0.0
        hh = PRINT_HEADING_H if heads else 0.0
        titles = paging.titles
        title_rows = titles if titles and k > 0 and a > titles[1] else None
        th = (ys[title_rows[1] + 1] - ys[title_rows[0]]) if title_rows else 0.0
        w = xs[c1 + 1] - xs[c0]
        h = ys[b + 1] - ys[a]
        total_w = w * scale + hw
        total_h = (h + th) * scale + hh
        x0 = left + ((width + hw - total_w) / 2 if opts["center_h"] else 0.0)
        y0 = top + ((height + hh - total_h) / 2 if opts["center_v"] else 0.0)
        gx, gy = x0 + hw, y0 + hh
        blocks = []
        if title_rows:
            blocks.append((title_rows[0], title_rows[1], gy))
        blocks.append((a, b, gy + th * scale))
        for ra, rb, at in blocks:
            painter.save()
            painter.translate(gx, at)
            painter.scale(scale, scale)
            painter.translate(-xs[c0], -ys[ra])
            painter.setClipRect(QRectF(xs[c0], ys[ra], w, ys[rb + 1] - ys[ra]))
            self._range = (ra, rb, c0, c1)
            self._on_paper = True
            try:
                self.paint_content(painter)
            finally:
                self._range = None
                self._on_paper = False
            painter.restore()
            if heads:
                self._print_headings(painter, ra, rb, c0, c1, x0, at, scale, hw, hh,
                                     first=(at == gy))
        inner = QRectF(gx, gy + th * scale, w * scale, h * scale)
        source = QRectF(xs[c0], ys[a] - self._tops[k], w, h)
        return source, inner

    def _print_headings(self, painter, ra, rb, c0, c1, x0, at, scale, hw, hh, first) -> None:
        xs, ys = self.edges()
        painter.save()
        painter.setFont(page_font("", 7.0))
        pen = QPen(QColor("#808080"), 0.4)
        if first:
            for c in range(c0, c1 + 1):
                cell = QRectF(x0 + hw + (xs[c] - xs[c0]) * scale, at - hh,
                              (xs[c + 1] - xs[c]) * scale, hh)
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
