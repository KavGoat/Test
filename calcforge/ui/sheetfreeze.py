"""Excel's Freeze Panes in the workbook view (docs/qa/excel_audit.md, J1).

View ▸ Spreadsheet ▸ Freeze Panes keeps the rows above and the columns left
of the active cell in sight as the sheet scrolls; Freeze Top Row and Freeze
First Column keep the first row or column; Unfreeze Panes lets them go.
Each is one undo step, kept with the sheet (its page options' ``freeze``,
[rows, columns]) and saved; an Excel file's frozen panes come in with it.
As in Excel, they are the Normal view's and Page Break Preview's: the
sheet's pages (its Page Layout view) print and show it whole.

The frozen cells are drawn over the scrolled ones at the top and left of
the window — the canvas's own drawing of those cells, so their selection,
borders and formula references are there too — with Excel's thin line
along the freeze. A click, a drag or the pointer over them is taken to be
on the cells drawn there; keys that move the active cell keep it in sight
below and right of the frozen cells.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

#: Excel's freeze line
FREEZE_LINE = QColor("#7f7f7f")


def frozen(item) -> tuple:
    """(rows, columns) frozen on *item*'s sheet, (0, 0) for none."""
    sheet = getattr(item, "sheet", None)
    page = getattr(sheet, "page", None) or {}
    got = page.get("freeze") or (0, 0)
    try:
        return max(0, int(got[0])), max(0, int(got[1]))
    except (TypeError, ValueError, IndexError):
        return (0, 0)


def _shown(view):
    """The sheet shown alone with panes frozen, or None."""
    from .sheetview import _item, run_shown
    window = getattr(view, "window", None)
    if window is None or getattr(window, "view", None) is not view:
        return None
    item = _item(window, run_shown(view.scene()))
    if item is None or item.paging is None or frozen(item) == (0, 0):
        return None
    return item


# -- the commands ---------------------------------------------------------------------------------
def _set(window, cells: Optional[tuple], label: str) -> None:
    from . import sheetlayout
    from .sheetview import _item, is_on, run_shown
    item = _item(window, run_shown(window.scene)) if is_on(window) else None
    tables = window.view.tables
    if item is None:
        item = tables.item if getattr(tables.item, "SHEET_RUN", False) else None
    if item is None or item.sheet is None:
        window.status_hint.setText("Freeze Panes is for a spreadsheet: open one first")
        return
    sheetlayout.change_options(window, item, label, freeze=list(cells) if cells else None)
    if cells:
        # from the top left, as Excel shows them once frozen at the top
        view = window.view
        corner = item.mapToScene(item.grid_rect().topLeft())
        view.bring_to(corner, QPointF(0, 0))
    refresh(window.view)
    window.status_hint.setText(_said(cells))


def _said(cells) -> str:
    if not cells:
        return "Panes unfrozen"
    rows, cols = cells
    parts = []
    if rows:
        parts.append(f"{rows} row{'s' * (rows != 1)}")
    if cols:
        parts.append(f"{cols} column{'s' * (cols != 1)}")
    return "Frozen: " + " and ".join(parts) + " stay in sight"


def freeze_panes(window) -> None:
    """Excel's Freeze Panes: the rows above and the columns left of the
    active cell (Unfreeze Panes when they are frozen already)."""
    tables = window.view.tables
    item = tables.item
    if item is not None and frozen(item) != (0, 0):
        _set(window, None, "Unfreeze Panes")
        return
    active = tables.active if item is not None and tables.active is not None else (1, 1)
    if active == (0, 0):
        active = (1, 1)            # Excel's at A1: the middle of the window; here, B2
    _set(window, active, "Freeze Panes")


def freeze_top_row(window) -> None:
    _set(window, (1, 0), "Freeze Top Row")


def freeze_first_column(window) -> None:
    _set(window, (0, 1), "Freeze First Column")


def unfreeze_panes(window) -> None:
    _set(window, None, "Unfreeze Panes")


# -- where the frozen cells are drawn -------------------------------------------------------------
def pieces(view, item) -> list:
    """(source rect in the sheet's own coordinates, target rect in the
    window) of each part drawn fixed: the frozen block, the frozen rows
    across, the frozen columns down, and their row numbers and letters."""
    from ..items.table import HEADING_H, ROWNUM_W
    rows, cols = frozen(item)
    xs, ys = item.edges()
    rows, cols = min(rows, len(ys) - 1), min(cols, len(xs) - 1)
    k = max(view.transform().m11(), 0.05)
    vp = view.viewport().rect()
    head, nums = HEADING_H * k, ROWNUM_W * k
    fh, fw = ys[rows] * k, xs[cols] * k

    def local(x, y):
        return item.mapFromScene(view.mapToScene(int(round(x)), int(round(y))))
    out = []
    if rows and cols:
        out.append((QRectF(0, 0, xs[cols], ys[rows]), QRectF(nums, head, fw, fh)))
    if rows:
        x0 = nums + fw
        a, b = local(x0, 0).x(), local(vp.width(), 0).x()
        if b > a:
            out.append((QRectF(a, 0, b - a, ys[rows]), QRectF(x0, head, (b - a) * k, fh)))
        out.append((QRectF(-ROWNUM_W, 0, ROWNUM_W, ys[rows]), QRectF(0, head, nums, fh)))
    if cols:
        y0 = head + fh
        a, b = local(0, y0).y(), local(0, vp.height()).y()
        if b > a:
            out.append((QRectF(0, a, xs[cols], b - a), QRectF(nums, y0, fw, (b - a) * k)))
        out.append((QRectF(0, -HEADING_H, xs[cols], HEADING_H), QRectF(nums, 0, fw, head)))
    return out


def shown_point(view, item, scene_point: QPointF) -> QPointF:
    """Where in the window a point of the canvas is seen: in the frozen
    part when it is a frozen cell's, else where the view puts it."""
    plain = QPointF(view.mapFromScene(scene_point))
    if _shown(view) is not item:
        return plain
    local = item.mapFromScene(scene_point)
    k = max(view.transform().m11(), 0.05)
    for source, target in pieces(view, item):
        if source.contains(local):
            return target.topLeft() + (local - source.topLeft()) * k
    return plain


def hidden_by(view, item) -> tuple:
    """(height, width) in the sheet's own units that the frozen rows and
    columns cover at the top and left of the window."""
    rows, cols = frozen(item)
    xs, ys = item.edges()
    return ys[min(rows, len(ys) - 1)], xs[min(cols, len(xs) - 1)]


def scroll_to_cell(view, item, cell) -> bool:
    """Keep *cell* in sight with panes frozen: a frozen row or column is
    always there; any other is kept below and right of them. True when
    handled (panes are frozen on the sheet shown)."""
    if _shown(view) is not item:
        return False
    from ..items.table import HEADING_H, ROWNUM_W
    rows, cols = frozen(item)
    rect = item.cell_rect(*cell)
    k = max(view.transform().m11(), 0.05)
    seen = item.mapRectFromScene(view.mapToScene(view.viewport().rect()).boundingRect())
    cover_h, cover_w = hidden_by(view, item)
    bar_v, bar_h = view.verticalScrollBar(), view.horizontalScrollBar()
    if cell[0] >= rows:
        top = seen.top() + HEADING_H + cover_h
        if rect.top() < top:
            bar_v.setValue(bar_v.value() - int(round((top - rect.top()) * k)) - 1)
        elif rect.bottom() > seen.bottom():
            bar_v.setValue(bar_v.value() + int(round((rect.bottom() - seen.bottom()) * k)) + 1)
    if cell[1] >= cols:
        left = seen.left() + ROWNUM_W + cover_w
        if rect.left() < left:
            bar_h.setValue(bar_h.value() - int(round((left - rect.left()) * k)) - 1)
        elif rect.right() > seen.right():
            bar_h.setValue(bar_h.value() + int(round((rect.right() - seen.right()) * k)) + 1)
    return True


def home_cell(item) -> tuple:
    """Ctrl+Home with panes frozen: the first cell below and right of them."""
    return frozen(item)


# -- drawing them ---------------------------------------------------------------------------------
class FrozenPanes(QWidget):
    """The frozen cells drawn over the view's window, and the mouse taken to
    the cells drawn there."""

    def __init__(self, view):
        super().__init__(view)            # over the viewport, beside the kept headings
        self.view = view
        self.setObjectName("frozenPanes")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self._viewport = view.viewport()
        self._viewport.installEventFilter(self)
        self._sending = False
        self._pieces: list = []
        self._item = None
        scene = view.scene()
        self._scene = None
        self._watch_scene(scene)
        for bar in (view.horizontalScrollBar(), view.verticalScrollBar()):
            bar.valueChanged.connect(lambda _v: self.refresh())
        view.zoomChanged.connect(lambda _z: self.refresh())
        self.hide()

    def _watch_scene(self, scene) -> None:
        if scene is self._scene:
            return
        self._scene = scene
        if scene is not None:
            scene.changed.connect(self._scene_changed)

    def _scene_changed(self, _rects=None) -> None:
        if self.isVisible():
            self.update()

    def refresh(self) -> None:
        from shiboken6 import isValid
        if not isValid(self) or not isValid(self.view):
            return
        self._watch_scene(self.view.scene())
        item = _shown(self.view)
        self._item = item
        self._pieces = pieces(self.view, item) if item is not None else []
        if not self._pieces:
            self.hide()
            return
        self.setGeometry(self._viewport.geometry())
        self.show()
        self.raise_()
        self.update()

    def paintEvent(self, event) -> None:
        item, scene = self._item, self.view.scene()
        if item is None or scene is None:
            return
        painter = QPainter(self)
        for source, target in self._pieces:
            painter.save()
            painter.setClipRect(target)
            scene.render(painter, target, item.mapRectToScene(source), Qt.IgnoreAspectRatio)
            painter.restore()
        # Excel's thin line along the freeze
        k = max(self.view.transform().m11(), 0.05)
        from ..items.table import HEADING_H, ROWNUM_W
        cover_h, cover_w = hidden_by(self.view, item)
        rows, cols = frozen(item)
        painter.setPen(QPen(FREEZE_LINE, 1))
        if rows:
            y = int(round(HEADING_H * k + cover_h * k))
            painter.drawLine(0, y, self.width(), y)
        if cols:
            x = int(round(ROWNUM_W * k + cover_w * k))
            painter.drawLine(x, 0, x, self.height())
        painter.end()

    # -- the mouse on the frozen cells: taken to the cells drawn there -----------------------
    def eventFilter(self, watched, event) -> bool:
        kind = event.type()
        if kind not in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseMove,
                        QEvent.MouseButtonDblClick) or watched is not self._viewport:
            return False
        if self._sending or not self._pieces or self._item is None:
            return False
        point = event.position()
        k = max(self.view.transform().m11(), 0.05)
        for source, target in self._pieces:
            if target.contains(point):
                local = source.topLeft() + (point - target.topLeft()) / k
                there = QPointF(self.view.mapFromScene(self._item.mapToScene(local)))
                moved = QMouseEvent(kind, there, event.globalPosition(), event.button(),
                                    event.buttons(), event.modifiers())
                self._sending = True
                try:
                    QApplication.sendEvent(self._viewport, moved)
                finally:
                    self._sending = False
                return True
        return False


def watch(view) -> FrozenPanes:
    """The view's frozen panes (made once)."""
    made = getattr(view, "_frozen_panes", None)
    if made is None:
        made = view._frozen_panes = FrozenPanes(view)
    return made


def refresh(view) -> None:
    made = getattr(view, "_frozen_panes", None)
    if made is None and _shown(view) is not None:
        made = watch(view)
    if made is not None:
        made.refresh()

