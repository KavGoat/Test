"""Equations on the page: a WebSMath region as a page item.

An equation, a plot, a matrix or a program block is one region of the
document's worksheet (``calc/docsheet.py``). On the page it is this item: it
sits in page points like any markup, so it is selected, grouped, aligned,
snapped, locked and undone like one — and it draws itself with WebSMath's own
typesetting (``calc/ui``), so it looks exactly as SMath draws it: SMath's
fonts, blue units, red errors, at SMath's printed size (one SMath pixel is
0.75 pt).

It is not a markup in the PDF sense. It never becomes an annotation and it is
not in the Markups list; saving writes it into the page as drawing
(decision 3), and its source goes in the record.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem

from ..calc.docsheet import PT_PER_PX, PX_PER_PT, sheet_for
from ..calc.record import region_text, region_to_data
from .base import MarkupItem, register_item

EMPTY = {"root": []}
GRID_PX = 9.0                   # SMath's grid, in its 96-dpi pixels


@register_item
class CalcItem(MarkupItem):
    """One equation (or plot, matrix or program block) on a page."""

    TYPE = "calc"
    NAME = "Equation"
    RESIZABLE = False
    ROTATABLE = False
    HAS_TEXT = False
    # Not a PDF annotation, not in the Markups list, not recoloured: the
    # places that need to know ask this.
    IS_CALC = True

    def __init__(self, data: Optional[dict] = None):
        super().__init__()
        self._data = dict(data or EMPTY)
        self.region = None              # while on a page of a document
        self._view = None               # WebSMath's drawing of the region
        self._sheet = None
        self.focused = False

    # -- the region ----------------------------------------------------------
    def source(self) -> dict:
        """The editable source, as the record keeps it."""
        if self.region is not None:
            return region_to_data(self.region)
        return dict(self._data)

    def text(self) -> str:
        return region_text(self.source()) or ""

    def _page_frame(self):
        frame = self.parentItem()
        return frame if frame is not None and hasattr(frame, "page") \
            and hasattr(frame, "document") else None

    def _attach(self) -> None:
        frame = self._page_frame()
        if frame is None or self.region is not None:
            return
        from ..calc.ui.layout import Style as MathStyle
        from ..calc.ui.region_item import RegionItem

        self._sheet = sheet_for(frame.document)
        _connect(self._sheet, frame.scene())
        x, y = self.pos().x() * PX_PER_PT, self.pos().y() * PX_PER_PT
        self.region = self._sheet.add(self._data, frame.page.uid, x, y)
        # The size is about to change: Qt's index of where items are has to be
        # told first, or clicks on the rest of the equation find nothing.
        self.prepareGeometryChange()
        self._view = RegionItem(self.region, self._sheet.worksheet, MathStyle(self.region.font_size))
        self._sheet_items()[self.region.id] = self
        self.relayout()

    def _detach(self) -> None:
        if self.region is None:
            return
        self._data = region_to_data(self.region)
        self._sheet_items().pop(self.region.id, None)
        self._sheet.remove(self.region)
        self.prepareGeometryChange()
        self.region = None
        self._view = None
        self._sheet = None

    def _sheet_items(self) -> dict:
        items = getattr(self._sheet, "items", None)
        if items is None:
            items = self._sheet.items = {}
        return items

    def _moved(self) -> None:
        frame = self._page_frame()
        if self.region is None or frame is None:
            return
        self._sheet.move(self.region, frame.page.uid,
                         self.pos().x() * PX_PER_PT, self.pos().y() * PX_PER_PT)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and isinstance(value, QPointF):
            # SMath keeps every region on its grid, wherever it is dragged to
            step = GRID_PX * PT_PER_PX
            value = QPointF(round(value.x() / step) * step, round(value.y() / step) * step)
        result = super().itemChange(change, value)
        if change == QGraphicsItem.ItemParentHasChanged:
            if self._page_frame() is None:
                self._detach()
            elif self.region is None:
                self._attach()
            else:
                self._moved()           # onto another page
        elif change == QGraphicsItem.ItemSceneHasChanged and self.scene() is None:
            self._detach()
        elif change == QGraphicsItem.ItemPositionHasChanged:
            self._moved()
        return result

    # -- geometry and drawing ---------------------------------------------------
    def relayout(self) -> None:
        self.prepareGeometryChange()
        if self._view is not None:
            self._view.focused = self.focused
            self._view.relayout()
        self.geometryChanged.emit()
        self.update()

    def _frame_px(self) -> QRectF:
        if self._view is None:
            return QRectF(0, 0, 20, 24)
        return self._view.frame_rect()

    def local_rect(self) -> QRectF:
        r = self._frame_px()
        return QRectF(0, 0, r.width() * PT_PER_PX, r.height() * PT_PER_PX)

    def set_local_rect(self, rect: QRectF) -> None:
        pass                            # an equation is as big as what it says

    def boundingRect(self) -> QRectF:
        if self._view is None:
            return self.local_rect().adjusted(-2, -2, 2, 2)
        r = self._view.boundingRect()
        return QRectF(r.x() * PT_PER_PX, r.y() * PT_PER_PX,
                      r.width() * PT_PER_PX, r.height() * PT_PER_PX).adjusted(-2, -2, 2, 2)

    def shape(self):
        from PySide6.QtGui import QPainterPath
        path = QPainterPath()
        path.addRect(self.local_rect())
        return path

    def paint_visible(self, painter: QPainter) -> None:
        if self._view is None:
            return
        painter.save()
        painter.scale(PT_PER_PX, PT_PER_PX)
        self._view.paint(painter, None)
        painter.restore()

    def paint(self, painter: QPainter, option, widget=None) -> None:
        self.paint_visible(painter)
        frame = self._page_frame()
        if getattr(frame, "print_mode", False):
            return
        if self.isSelected() and not self.focused:
            painter.save()
            pen = QPen(QColor("#1971c2"))
            pen.setCosmetic(True)
            pen.setWidthF(1.0)
            pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.local_rect())
            painter.restore()

    # -- the record --------------------------------------------------------------
    def serialize(self) -> dict:
        data = self.base_dict()
        data["calc"] = self.source()
        return data

    def deserialize(self, data: dict) -> None:
        self.load_base(data)
        self._data = dict(data.get("calc") or EMPTY)

    def summary(self) -> str:
        return self.text()

    def display_name(self) -> str:
        return self.NAME


def _connect(sheet, scene) -> None:
    """Redraw the equations whose results a calculation changed."""
    if getattr(sheet, "_connected", False):
        return
    sheet._connected = True

    def changed(ids: set) -> None:
        items = getattr(sheet, "items", {})
        for region_id in ids or ():
            item = items.get(region_id)
            if item is not None:
                item.relayout()

    sheet.on_changed = changed

    # Moves are calculated once the gesture is over (docsheet.settle); a
    # move made any other way is settled on the next turn of the event loop.
    from PySide6.QtCore import QTimer

    def request() -> None:
        if getattr(sheet, "_settle_posted", False):
            return
        sheet._settle_posted = True

        def run() -> None:
            sheet._settle_posted = False
            sheet.settle()
        QTimer.singleShot(0, run)

    sheet.request_settle = request
