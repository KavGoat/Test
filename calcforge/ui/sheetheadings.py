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
        head_h = max(1, int(round(HEADING_H * k)))
        num_w = max(1, int(round(ROWNUM_W * k)))
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
            if top_left.y() - HEADING_H * k < -0.5 and 0 < bottom_right.y():
                strips.append((run, "col", QRect(int(left), 0, int(right - left), head_h)))
            top = max(top_left.y(), 0)
            bottom = min(bottom_right.y(), viewport.height())
            if top_left.x() - ROWNUM_W * k < -0.5 and 0 < bottom_right.x():
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

    def paintEvent(self, event) -> None:
        self._drop_gone()
        painter = QPainter(self)
        view = self.view
        k = self._scale()
        font = QFont(self.font())
        font.setPixelSize(max(1, int(round(8 * k * 96 / 72))))   # the sheet's own
        painter.setFont(font)
        grid = QPen(QColor("#bdbdbd"), 1)
        for run, kind, rect in self._strips:
            if kind == "corner":
                from ..items.sheetpage import paint_corner
                paint_corner(painter, QRectF(rect).adjusted(0, 0, -1, -1), self.corner_hot,
                             run.everything_picked(), grid)
                continue
            painter.save()
            painter.setClipRect(rect)
            painter.fillRect(rect, HEADING_BG)
            xs, ys = run.edges()
            sel = run.selection if run.opened else None
            # only the columns or rows the strip shows (a sheet can have thousands)
            corners = [run.mapFromScene(view.mapToScene(p)) for p in
                       (rect.topLeft(), rect.topRight(), rect.bottomLeft(), rect.bottomRight())]
            if kind == "col":
                lo = min(p.x() for p in corners)
                hi = max(p.x() for p in corners)
                first = max(0, bisect.bisect_right(xs, lo) - 2)
                last = min(len(xs) - 1, bisect.bisect_right(xs, hi) + 1)
                for c in range(first, last):
                    a = view.mapFromScene(run.mapToScene(QPointF(xs[c], 0))).x()
                    b = view.mapFromScene(run.mapToScene(QPointF(xs[c + 1], 0))).x()
                    if b < rect.left() or a > rect.right() or b - a < 1:
                        continue
                    cell = QRect(int(a), rect.top(), int(b - a), rect.height())
                    on = sel is not None and sel[1] <= c <= sel[3]
                    painter.fillRect(cell, HEADING_ON if on else HEADING_BG)
                    painter.setPen(grid)
                    painter.drawRect(cell.adjusted(0, 0, -1, -1))
                    painter.setPen(EXCEL_GREEN if on else QColor("#444444"))
                    painter.drawText(cell, Qt.AlignCenter, col_letters(c))
            else:
                lo = min(p.y() for p in corners)
                hi = max(p.y() for p in corners)
                first = max(0, bisect.bisect_right(ys, lo) - 2)
                last = min(len(ys) - 1, bisect.bisect_right(ys, hi) + 1)
                for r in range(first, last):
                    a = view.mapFromScene(run.mapToScene(QPointF(0, ys[r]))).y()
                    b = view.mapFromScene(run.mapToScene(QPointF(0, ys[r + 1]))).y()
                    if b < rect.top() or a > rect.bottom() or b - a < 1:
                        continue
                    cell = QRect(rect.left(), int(a), rect.width(), int(b - a))
                    on = sel is not None and sel[0] <= r <= sel[2]
                    painter.fillRect(cell, HEADING_ON if on else HEADING_BG)
                    painter.setPen(grid)
                    painter.drawRect(cell.adjusted(0, 0, -1, -1))
                    painter.setPen(EXCEL_GREEN if on else QColor("#444444"))
                    painter.drawText(cell, Qt.AlignCenter, str(r + 1))
            painter.restore()
        painter.end()


def _edge_at(edges: list, at: float, tol: float) -> Optional[int]:
    """The column (row) whose right (bottom) edge is within *tol* of *at*:
    tableedit's rule (hidden ones included), over the few edges near it."""
    from .tableedit import _edge_near
    k = bisect.bisect_left(edges, at - tol)
    first = max(0, k - 2)
    found = _edge_near(edges[first:k + 3], at, tol)
    return None if found is None else found + first
