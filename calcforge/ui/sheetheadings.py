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
        self.hide()

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
        head_h = max(14, int(round(HEADING_H * k)))
        num_w = max(24, int(round(ROWNUM_W * k)))
        for run in self._runs():
            grid = run.local_rect()
            top_left = view.mapFromScene(run.mapToScene(grid.topLeft()))
            bottom_right = view.mapFromScene(run.mapToScene(grid.bottomRight()))
            if bottom_right.y() <= 0 or top_left.y() >= viewport.height() or \
                    bottom_right.x() <= 0 or top_left.x() >= viewport.width():
                continue                       # not in view
            left = max(top_left.x(), 0)
            right = min(bottom_right.x(), viewport.width())
            if top_left.y() - head_h < 0 < bottom_right.y():
                strips.append((run, "col", QRect(int(left), 0, int(right - left), head_h)))
            top = max(top_left.y(), 0)
            bottom = min(bottom_right.y(), viewport.height())
            if top_left.x() - num_w < 0 < bottom_right.x():
                strips.append((run, "row", QRect(0, int(top), num_w, int(bottom - top))))
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
        self.update()

    def hit(self, viewport_pos) -> Optional[tuple]:
        """(run, ("col", c)) or (run, ("row", r)) under a point of the canvas."""
        if not self.isVisible():
            return None
        point = QPointF(viewport_pos)
        for run, kind, rect in self._strips:
            if not QRectF(rect).contains(point):
                continue
            scene = self.view.mapToScene(point.toPoint())
            local = run.mapFromScene(scene)
            xs, ys = run.edges()
            if kind == "col":
                c = max(0, min(bisect.bisect_right(xs, local.x()) - 1, len(xs) - 2))
                return run, ("col", c)
            r = max(0, min(bisect.bisect_right(ys, local.y()) - 1, len(ys) - 2))
            return run, ("row", r)
        return None

    # -- drawing -----------------------------------------------------------------------------
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        view = self.view
        k = self._scale()
        font = QFont(self.font())
        font.setPixelSize(max(9, min(14, int(round(8 * k * 1.33)))))
        painter.setFont(font)
        grid = QPen(QColor("#bdbdbd"), 1)
        for run, kind, rect in self._strips:
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
