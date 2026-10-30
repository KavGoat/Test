"""A spreadsheet page's headings kept in view (Excel's frozen headings).

Scrolled down a long sheet, its column letters stay along the top of the
canvas; scrolled across, its row numbers stay down the left — over the
sheet, as Excel's do, and they select a whole column or row when clicked.
Drawn as a small strip over the canvas (not on the page), so they never print
and never move with the scroll.
"""
from __future__ import annotations

import bisect
from typing import Optional

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QRegion
from PySide6.QtWidgets import QWidget

from ..items.table import EXCEL_GREEN, HEADING_BG, HEADING_H, HEADING_ON, ROWNUM_W
from ..sheet.refs import col_letters


class SheetHeadings(QWidget):
    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self._strips: list = []         # (run, "col"/"row", QRect in this widget)
        self._soon = QTimer(self)
        self._soon.setSingleShot(True)
        self._soon.setInterval(0)
        self._soon.timeout.connect(self.refresh)
        view.horizontalScrollBar().valueChanged.connect(lambda _v: self.refresh())
        view.verticalScrollBar().valueChanged.connect(lambda _v: self.refresh())
        view.zoomChanged.connect(lambda _z: self.refresh())
        # the pointer over the kept select-all corner lights it up (the strip
        # itself lets the mouse through to the canvas)
        self.corner_hot = False
        self._viewport = view.viewport()
        self._viewport.installEventFilter(self)
        self.hide()

    def eventFilter(self, watched, event) -> bool:
        from PySide6.QtCore import QEvent
        # (the type first, and the viewport as kept: nothing asked of a view
        # that is being taken down)
        if event.type() in (QEvent.MouseMove, QEvent.Leave) and watched is self._viewport:
            hot = event.type() == QEvent.MouseMove and any(
                kind == "corner" and QRectF(rect).contains(event.position())
                for _run, kind, rect in self._strips)
            if hot != self.corner_hot:
                self.corner_hot = hot
                self.update()
        return False

    def refresh_soon(self) -> None:
        self._soon.start()

    # -- where -------------------------------------------------------------------------------
    def _runs(self) -> list:
        scene = self.view.scene()
        if scene is None:
            return []
        from ..items.sheetpage import SheetRunItem
        out = []
        for frame in getattr(scene, "frames", []) or []:
            # a run's cells live on the first of its spreadsheet pages: a
            # drawing set's sheets have none, and looking through every
            # markup of all of them was a few milliseconds of every step of
            # a scroll (2026-10-19)
            if getattr(frame.page, "sheet", None) is None:
                continue
            for item in frame.markups():
                if isinstance(item, SheetRunItem) and item.sheet is not None and item.paging:
                    out.append(item)
        return out

    def _scale(self) -> float:
        return max(self.view.transform().m11(), 0.05)

    def refresh(self) -> None:
        """Work out which strips are needed now, and show them."""
        view = self.view
        viewport = view.viewport()
        self.setGeometry(viewport.geometry())
        strips = []
        k = self._scale()
        # the sheet's own heading sizes at the zoom: they never jump as they
        # come away from the grid (H2)
        import math
        head_h = max(1, math.ceil(HEADING_H * k - 0.01))
        num_w = max(1, math.ceil(ROWNUM_W * k - 0.01))
        for run in self._runs():
            grid = run.local_rect()
            top_left = view.mapFromScene(run.mapToScene(grid.topLeft()))
            bottom_right = view.mapFromScene(run.mapToScene(grid.bottomRight()))
            if bottom_right.y() <= 0 or top_left.y() >= viewport.height() or \
                    bottom_right.x() <= 0 or top_left.x() >= viewport.width():
                continue                       # not in view
            left = max(top_left.x(), 0)
            right = min(bottom_right.x(), viewport.width())
            # kept only once the sheet's own headings are (partly) out of view:
            # at the top of the window they are there to be used, their
            # column and row edges dragged (the workbook view's grid starts there)
            # (a sheet shown alone always has them: drawn here, every edge on
            # its grid line's pixel, scrolled or not)
            alone = getattr(run, "alone", False)
            if (alone or top_left.y() - HEADING_H * k < -0.5) and 0 < bottom_right.y():
                strips.append((run, "col", QRect(int(left), 0, int(right - left), head_h)))
            top = max(top_left.y(), 0)
            bottom = min(bottom_right.y(), viewport.height())
            if (alone or top_left.x() - ROWNUM_W * k < -0.5) and 0 < bottom_right.x():
                strips.append((run, "row", QRect(0, int(top), num_w, int(bottom - top))))
            kinds = [kind for owner, kind, _rect in strips if owner is run]
            if "col" in kinds and "row" in kinds:
                # where the kept headings meet: Excel's select-all corner
                strips.append((run, "corner", QRect(0, 0, num_w, head_h)))
            elif "col" in kinds and top_left.x() - ROWNUM_W * k >= -0.5:
                # the letters kept, the sheet's own row numbers in sight: the
                # corner over them, not a row's number showing through (H2)
                strips.append((run, "corner", QRect(int(top_left.x() - num_w), 0,
                                                    num_w, head_h)))
            elif "row" in kinds and top_left.y() - HEADING_H * k >= -0.5:
                strips.append((run, "corner", QRect(0, int(top_left.y() - head_h),
                                                    num_w, head_h)))
        self._strips = strips
        if not strips:
            self.hide()
            return
        region = QRegion()
        for _run, _kind, rect in strips:
            region = region.united(QRegion(rect))
        self.setMask(region)
        self.show()
        self.raise_()
        frozen = getattr(view, "_frozen_panes", None)
        if frozen is not None and frozen.isVisible():
            frozen.raise_()                # the frozen cells' own headings over these
        self.update()

    def hit(self, viewport_pos) -> Optional[tuple]:
        """(run, ("col", c)) or (run, ("row", r)) under a point of the canvas."""
        if not self.isVisible():
            return None
        self._drop_gone()
        point = QPointF(viewport_pos)
        for run, kind, rect in reversed(self._strips):     # (the corner over both)
            if not QRectF(rect).contains(point):
                continue
            if kind == "corner":
                return run, ("corner",)
            scene = self.view.mapToScene(point.toPoint())
            local = run.mapFromScene(scene)
            xs, ys = run.edges()
            # an edge, as on the sheet's own headings: dragged, it sizes (B2)
            tol = 3.0 / self._scale()
            if kind == "col":
                edge = _edge_at(xs, local.x(), tol)
                if edge is not None:
                    return run, ("col_edge", edge)
                c = max(0, min(bisect.bisect_right(xs, local.x()) - 1, len(xs) - 2))
                return run, ("col", c)
            edge = _edge_at(ys, local.y(), tol)
            if edge is not None:
                return run, ("row_edge", edge)
            r = max(0, min(bisect.bisect_right(ys, local.y()) - 1, len(ys) - 2))
            return run, ("row", r)
        return None

    # -- drawing -----------------------------------------------------------------------------
    def _drop_gone(self) -> None:
        """Strips of a sheet whose cells have gone (its pages rebuilt, undone)
        are dropped until the next refresh: drawing them read a freed item."""
        from shiboken6 import isValid
        scene = self.view.scene()
        kept = [strip for strip in self._strips if isValid(strip[0])
                and strip[0].scene() is scene]
        if len(kept) != len(self._strips):
            self._strips = kept
            self.refresh_soon()

    def _paint_as_the_grid(self, painter, run, kind, rect, local, grid, font) -> bool:
        """A strip drawn the way the grid beside it is: the grid comes from
        pictures of the sheet's rows, each drawn at the scale of its own
        whole pixels and put on whole pixels of the screen (SheetRunItem.
        _paint_bands), so the strip is too — the same picture scale, placed
        by the same rounding — and every heading's edge lands on its grid
        line's pixel. False when the grid is not drawn from pictures (so
        close in, or while a zoom glides): then it is drawn directly."""
        import math
        from PySide6.QtGui import QPixmap
        from ..ui.scene import _draw_on_the_pixel_grid, _painted_scale
        painter.save()
        painter.setTransform(local)
        scale = round(_painted_scale(painter), 4)
        device = painter.deviceTransform()
        painter.restore()
        xs, ys = run.edges()
        width = int(round(xs[-1] * scale))
        if width <= 0 or width > 8192 or abs(device.m12()) > 1e-9 or run._zoom_gliding():
            return False
        ratio = self.devicePixelRatioF()
        # (in this widget's own coordinates: what the painter paints into may
        # put it anywhere — the window's backing store, a grab of the window)
        inverse, ok = local.inverted()
        if not ok:
            return False
        seen = inverse.mapRect(QRectF(rect))
        # a tile is drawn once and kept until what it shows changes — the
        # headings' edges, the selection, the zoom — rather than afresh for
        # every frame of a scroll (the user, 2026-10-29: "make spreadsheets
        # faster: scrolling")
        tiles = self.__dict__.setdefault("_tiles", {})
        sel = tuple(run.selection) if run.opened and run.selection else None
        stamp = (id(run), scale, ratio, font.key(), sel, hash(tuple(xs)), len(ys))

        def kept(key, draw):
            got = tiles.get(key)
            if got is None or got[0] != stamp:
                if len(tiles) > 64:
                    tiles.clear()
                got = tiles[key] = (stamp, draw())
            return got[1]
        if kind == "col":
            # across: the bands' picture width
            high = max(1, math.ceil(rect.height() * ratio))
            first = max(0, bisect.bisect_right(xs, seen.left()) - 2)
            last = min(len(xs) - 2, bisect.bisect_right(xs, seen.right()) + 1)

            def across():
                tile = QPixmap(width, high)
                tile.fill(HEADING_BG)
                p = QPainter(tile)
                p.scale(width / xs[-1], high / HEADING_H)
                p.translate(0, HEADING_H)
                p.setRenderHint(QPainter.Antialiasing, False)
                p.setFont(font)
                _cells(p, run, "col", first, last, grid)
                p.end()
                return tile
            tile = kept(("col", first, last, high), across)
            # placed by the bands' own rule (the same left and right edges,
            # so the same stretch when a band's picture is a pixel off its place)
            top_at = inverse.map(QPointF(0, rect.top())).y()
            painter.save()
            painter.setTransform(local)
            _draw_on_the_pixel_grid(painter, QRectF(0, top_at, xs[-1], high / device.m22()), tile)
            painter.restore()
            return True
        # down: band by band, each as its band of rows is drawn and placed
        rows = len(ys) - 1
        band = run.BAND
        wide = max(1, math.ceil(rect.width() * ratio))
        r0 = max(0, bisect.bisect_right(ys, seen.top()) - 2)
        r1 = min(rows - 1, bisect.bisect_right(ys, seen.bottom()) + 1)
        for k in range(r0 // band, r1 // band + 1):
            a, b = k * band, min(rows - 1, k * band + band - 1)
            top, bottom = ys[a], ys[b + 1]
            high = int(round((bottom - top) * scale))
            if high <= 0:
                continue

            def down(a=a, b=b, top=top, bottom=bottom, high=high):
                tile = QPixmap(wide, high)
                tile.fill(HEADING_BG)
                p = QPainter(tile)
                p.scale(wide / ROWNUM_W, high / (bottom - top))
                p.translate(ROWNUM_W, -top)
                p.setRenderHint(QPainter.Antialiasing, False)
                p.setFont(font)
                _cells(p, run, "row", a, b, grid)
                p.end()
                return tile
            tile = kept(("row", a, b, wide, hash(tuple(ys[a:b + 2]))), down)
            left_at = inverse.map(QPointF(rect.left(), 0)).x()
            painter.save()
            painter.setTransform(local)
            _draw_on_the_pixel_grid(painter, QRectF(left_at, top, wide / device.m11(),
                                                    bottom - top), tile)
            painter.restore()
        return True

    def paintEvent(self, event) -> None:
        """Each strip drawn as the sheet draws its own headings — in the
        sheet's own coordinates, through the view's scale, pinned to the top
        (left) of the window: every edge where the grid's line is, at any
        zoom and screen scale (the user, 2026-10-22: zoomed in, "Excel top
        left is still not aligning correctly" — rounded to whole pixels and
        drawn a pixel in, the edges sat one or two pixels off the grid's)."""
        from PySide6.QtGui import QTransform
        from ..core.typography import page_font
        from ..items.sheetpage import paint_corner
        self._drop_gone()
        painter = QPainter(self)
        view = self.view
        grid = QPen(QColor("#bdbdbd"), 0)
        grid.setCosmetic(True)
        font = page_font("", 8.0)
        for run, kind, rect in self._strips:
            painter.save()
            painter.setClipRect(rect)
            # the sheet's own coordinates in this widget's
            # the very transform the view draws the sheet with (worked out
            # as it does, so an edge rounds to the grid's pixel), moved only
            # across the strip: the letters' strip down to the top of the
            # window, the numbers' strip across to its left
            local = run.deviceTransform(view.viewportTransform())
            kx, ky = local.m11(), local.m22()
            if kind == "corner":
                at = QPointF(rect.right() + 1, rect.bottom() + 1)
                painter.setTransform(QTransform(kx, 0, 0, ky, at.x(), at.y()))
                painter.setRenderHint(QPainter.Antialiasing, False)
                paint_corner(painter, run.corner_rect(), self.corner_hot,
                             run.everything_picked(), grid)
                painter.restore()
                continue
            if self._paint_as_the_grid(painter, run, kind, rect, local, grid, font):
                painter.restore()
                continue
            painter.fillRect(rect, HEADING_BG)
            painter.setTransform(local)
            if kind == "col":
                painter.translate(0, (rect.top() + HEADING_H * ky - local.dy()) / ky)
            else:
                painter.translate((rect.left() + ROWNUM_W * kx - local.dx()) / kx, 0)
            painter.setRenderHint(QPainter.Antialiasing, False)
            painter.setFont(font)
            painter.setBrush(Qt.NoBrush)
            xs, ys = run.edges()
            sel = run.selection if run.opened else None
            # only the columns or rows the strip shows (a sheet can have thousands)
            inverse, _ok = painter.transform().inverted()
            seen = inverse.mapRect(QRectF(rect))
            if kind == "col":
                first = max(0, bisect.bisect_right(xs, seen.left()) - 2)
                last = min(len(xs) - 1, bisect.bisect_right(xs, seen.right()) + 1)
                for c in range(first, last):
                    cell = QRectF(xs[c], -HEADING_H, xs[c + 1] - xs[c], HEADING_H)
                    if cell.width() <= 0:
                        continue
                    on = sel is not None and sel[1] <= c <= sel[3]
                    painter.fillRect(cell, HEADING_ON if on else HEADING_BG)
                    painter.setPen(grid)
                    _outline(painter, cell)
                    painter.setPen(EXCEL_GREEN if on else QColor("#444444"))
                    painter.drawText(cell, Qt.AlignCenter, col_letters(c))
            else:
                first = max(0, bisect.bisect_right(ys, seen.top()) - 2)
                last = min(len(ys) - 1, bisect.bisect_right(ys, seen.bottom()) + 1)
                for r in range(first, last):
                    cell = QRectF(-ROWNUM_W, ys[r], ROWNUM_W, ys[r + 1] - ys[r])
                    if cell.height() <= 0:
                        continue
                    on = sel is not None and sel[0] <= r <= sel[2]
                    painter.fillRect(cell, HEADING_ON if on else HEADING_BG)
                    painter.setPen(grid)
                    _outline(painter, cell)
                    painter.setPen(EXCEL_GREEN if on else QColor("#444444"))
                    painter.drawText(cell, Qt.AlignCenter, str(r + 1))
            painter.restore()
        painter.end()


def _cells(p: QPainter, run, kind: str, first: int, last: int, grid: QPen) -> None:
    """Headings *first* to *last* in the sheet's own coordinates, their
    edges drawn as the grid draws its lines."""
    xs, ys = run.edges()
    sel = run.selection if run.opened else None
    for i in range(first, last + 1):
        if kind == "col":
            cell = QRectF(xs[i], -HEADING_H, xs[i + 1] - xs[i], HEADING_H)
            if cell.width() <= 0:
                continue
            on = sel is not None and sel[1] <= i <= sel[3]
            text = col_letters(i)
        else:
            cell = QRectF(-ROWNUM_W, ys[i], ROWNUM_W, ys[i + 1] - ys[i])
            if cell.height() <= 0:
                continue
            on = sel is not None and sel[0] <= i <= sel[2]
            text = str(i + 1)
        p.fillRect(cell, HEADING_ON if on else HEADING_BG)
        p.setPen(grid)
        _outline(p, cell)
        p.setPen(EXCEL_GREEN if on else QColor("#444444"))
        p.drawText(cell, Qt.AlignCenter, text)


def _outline(painter: QPainter, cell: QRectF) -> None:
    """A heading's edges drawn as the grid draws its lines (drawLine, not
    drawRect, whose aliased edges round a pixel differently): on them."""
    painter.drawLine(cell.topLeft(), cell.topRight())
    painter.drawLine(cell.bottomLeft(), cell.bottomRight())
    painter.drawLine(cell.topLeft(), cell.bottomLeft())
    painter.drawLine(cell.topRight(), cell.bottomRight())


def _edge_at(edges: list, at: float, tol: float) -> Optional[int]:
    """The column (row) whose right (bottom) edge is within *tol* of *at*:
    tableedit's rule (hidden ones included), over the few edges near it."""
    from .tableedit import _edge_near
    k = bisect.bisect_left(edges, at - tol)
    first = max(0, k - 2)
    found = _edge_near(edges[first:k + 3], at, tol)
    return None if found is None else found + first
