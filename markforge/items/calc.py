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
from PySide6.QtGui import QColor, QPainter, QPen, QPicture
from PySide6.QtWidgets import QGraphicsItem

from ..calc.docsheet import PT_PER_PX, PX_PER_PT, sheet_for
from ..calc.record import region_text, region_to_data
from ..calc.ui.region_item import PAD_X, RegionItem
from ..calc.ui.wrap import wrap
from .base import MarkupItem, register_item

def created_here(page) -> bool:
    """A page CalcForge made (File > New, an added or automatic page), rather
    than one that came in from a PDF or an image."""
    if getattr(page, "written_here", None) is not None:
        return bool(page.written_here)
    return page.pdf_key is None and page.background_key is None


def calc_area(frame) -> QRectF:
    """Where equations go on a page, and where the grid is drawn.

    On a page CalcForge made, the printable area inside its margins, as in
    SMath; on a drawing that came in from a PDF, the whole sheet — a check
    calc beside the title block is a thing people do.
    """
    page = frame.page
    if created_here(page):
        left, top, width, height = page.setup.content_rect_pt
        return QRectF(left, top, width, height)
    return frame.page_rect()


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
        self._turn_while_editing = None   # its rotation, while shown upright to type in
        # Why it wants looking at (partly under a redaction, partly cropped
        # off): an orange outline on the screen, never printed.
        self.warning = ""

    # -- the region ----------------------------------------------------------
    def source(self) -> dict:
        """The editable source, as the record keeps it."""
        if self.region is not None:
            return region_to_data(self.region)
        return dict(self._data)

    def text(self) -> str:
        return region_text(self.source()) or ""

    @property
    def editor(self):
        """The equation editor, while it is on a page."""
        return self.region.editor if self.region is not None else None

    def _page_frame(self):
        frame = self.parentItem()
        return frame if frame is not None and hasattr(frame, "page") \
            and hasattr(frame, "document") else None

    def _attach(self) -> None:
        frame = self._page_frame()
        if frame is None or self.region is not None:
            return
        from ..calc.ui.layout import Style as MathStyle

        self._sheet = sheet_for(frame.document)
        _connect(self._sheet, frame.scene())
        x, y = self.reading_position()
        self.region = self._sheet.add(self._data, frame.page.uid, x, y)
        # The size is about to change: Qt's index of where items are has to be
        # told first, or clicks on the rest of the equation find nothing.
        self.prepareGeometryChange()
        self._view = _PageRegionView(self.region, self._sheet.worksheet, MathStyle(self.region.font_size))
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
        self.warning = ""
        self._sheet.move(self.region, frame.page.uid, *self.reading_position())

    # -- turned pages (decision 15) ------------------------------------------------
    def page_turns(self) -> int:
        """How many quarter turns clockwise its page has had since it was
        written. An equation is never turned on its own, so its rotation says."""
        rotation = self._turn_while_editing if self._turn_while_editing is not None \
            else self.rotation()
        return int(round(rotation / 90.0)) % 4

    def reading_position(self) -> tuple:
        """Where it is for the reading order, in SMath pixels: its place on
        the page as the page was when it was written. Rotate page moves every
        item round the sheet; turning that back means rotating a page never
        changes a result (the answer to "which way is top-left")."""
        x, y = self.pos().x(), self.pos().y()
        frame = self._page_frame()
        if frame is not None:
            width, height = frame.page.width_pt, frame.page.height_pt
            for _ in range(self.page_turns()):
                # undo one clockwise turn: (x, y) -> (y, width - x)
                x, y = y, width - x
                width, height = height, width
        return x * PX_PER_PT, y * PX_PER_PT

    def snap_to_grid(self) -> None:
        """Onto SMath's grid, as regions always are once dropped — the grid of
        the page as it was written, so a turned page keeps its equations where
        they were."""
        frame = self._page_frame()
        if frame is None:
            return
        step = GRID_PX
        x, y = self.reading_position()
        sx, sy = round(x / step) * step, round(y / step) * step
        if (sx, sy) == (x, y):
            return
        # turn the snapped point forward again: (x, y) -> (height - y, x) per turn
        width, height = frame.page.width_pt, frame.page.height_pt
        turns = self.page_turns()
        if turns % 2:
            width, height = height, width          # the page as it was written
        px, py = sx * PT_PER_PX, sy * PT_PER_PX
        for _ in range(turns):
            px, py = height - py, px
            width, height = height, width
        self.setPos(QPointF(px, py))

    def show_upright(self, view_turn: float = 0.0) -> None:
        """While it is typed into it reads the right way up, whatever the page
        and the view have been turned to; leave_upright turns it back."""
        if self._turn_while_editing is None:
            self._turn_while_editing = self.rotation()
        self.setTransformOriginPoint(QPointF(0, 0))
        self.setRotation(-view_turn)

    def leave_upright(self) -> None:
        if self._turn_while_editing is None:
            return
        turn, self._turn_while_editing = self._turn_while_editing, None
        self.setRotation(turn)

    def itemChange(self, change, value):
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
        elif change in (QGraphicsItem.ItemPositionHasChanged,
                        QGraphicsItem.ItemRotationHasChanged):
            if self._turn_while_editing is None or change == QGraphicsItem.ItemPositionHasChanged:
                self._moved()
        return result

    # -- geometry and drawing ---------------------------------------------------
    def relayout(self) -> None:
        self.prepareGeometryChange()
        if self._view is not None:
            self._view.focused = self.focused
            frame = self._page_frame()
            if frame is not None:
                room = calc_area(frame).right() - self.pos().x()
                self._view.max_width = max(room, 0.0) * PX_PER_PT
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
        device = painter.device()
        picture = QPicture()
        if device is None or (device.logicalDpiX() == picture.logicalDpiX()
                              and device.logicalDpiY() == picture.logicalDpiY()):
            self._view.paint(painter, None)
        else:
            # SMath's layout sizes its fonts in points, and Qt turns points
            # into pixels by the device's resolution: drawn straight onto a
            # PDF writer or a printer the letters come out bigger than the
            # layout they were measured for (at 300 dpi they run into each
            # other). Recorded at the screen's resolution and played back, the
            # drawing — text still text — is scaled as one, exactly.
            recorder = QPainter(picture)
            recorder.setRenderHints(painter.renderHints())
            self._view.paint(recorder, None)
            recorder.end()
            painter.scale(picture.logicalDpiX() / device.logicalDpiX(),
                          picture.logicalDpiY() / device.logicalDpiY())
            painter.drawPicture(0, 0, picture)
        painter.restore()

    @property
    def too_wide(self) -> bool:
        """Wider than its page even broken onto more lines: it will not print
        in full (shown with an orange outline, never printed)."""
        return bool(self._view is not None and self._view.too_wide)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        frame = self._page_frame()
        printing = bool(getattr(frame, "print_mode", False))
        if self._view is not None:
            # selected, it looks as a selected region does in WebSMath: its
            # own drawing (RegionItem.selected_region), not a MarkForge frame
            self._view.selected_region = self.isSelected() and not self.focused and not printing
        self.paint_visible(painter)
        if self._view is not None:
            self._view.selected_region = False
        if printing:
            return
        if self.too_wide or self.warning:
            painter.save()
            pen = QPen(QColor("#ff8c00"))
            pen.setCosmetic(True)
            pen.setWidthF(1.5)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.local_rect())
            painter.restore()

    # -- the record --------------------------------------------------------------
    def serialize(self) -> dict:
        data = self.base_dict()
        if self._turn_while_editing is not None:
            data["rotation"] = self._turn_while_editing
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


class _PageRegionView(RegionItem):
    """WebSMath's drawing of a region, broken onto more lines when it is too
    wide for its page and not being typed into (calc/ui/wrap.py)."""

    max_width = 0.0
    too_wide = False

    def relayout(self) -> None:
        super().relayout()
        self.too_wide = False
        if self.focused or not self.max_width or self._size[0] <= self.max_width + 1e-6:
            return
        region = self.region
        if region.kind == "math" and region.plot is None and self._layout is not None \
                and region.show_input:
            broken = wrap(self._layout, self.editor.root, self.max_width, PAD_X)
            if broken is not None:
                self._layout = broken
                from ..calc.ui.region_item import MIN_H, PAD_BOTTOM
                height = max(MIN_H, self._baseline + broken.desc + PAD_BOTTOM)
                self._size = (broken.w + 2 * PAD_X, height)
                self.update()
                return
        self.too_wide = True


# -- an equation as line work (a snapshot's copy of it, decision 16) ------------

def line_work_svg(item: "CalcItem") -> str:
    """The equation as vector line work: drawn into a PDF, then read back by
    MuPDF as SVG with the letters as outlines — the same route a snapshot of
    a PDF's own text takes (io/pdfsnapshot.py)."""
    import pymupdf
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMarginsF, QSizeF
    from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter

    from ..io.pdfsnapshot import inline_glyphs

    rect = item.local_rect()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    writer = QPdfWriter(buffer)
    # At the screen's 96 dpi: the fonts are sized in points, and Qt turns
    # points into pixels by the device's resolution (io/pdfbase.py).
    writer.setResolution(96)
    writer.setPageLayout(QPageLayout(QPageSize(QSizeF(rect.width(), rect.height()), QPageSize.Point),
                                     QPageLayout.Portrait, QMarginsF(0, 0, 0, 0)))
    painter = QPainter(writer)
    painter.scale(96 / 72, 96 / 72)
    painter.translate(-rect.topLeft())
    focused, item.focused = item.focused, False
    try:
        if focused:
            item.relayout()
        item.paint_visible(painter)
    finally:
        item.focused = focused
        if focused:
            item.relayout()
        painter.end()
        buffer.close()
    document = pymupdf.open("pdf", bytes(data))
    try:
        return inline_glyphs(document[0].get_svg_image(text_as_path=True))
    finally:
        document.close()


@register_item
class CalcDrawingItem(MarkupItem):
    """An equation as it was drawn, kept as line work — what a snapshot holds
    of an equation it was taken over. It no longer calculates."""

    TYPE = "calc_drawing"
    NAME = "Equation drawing"
    RESIZABLE = False
    ROTATABLE = True

    def __init__(self, rect: Optional[QRectF] = None):
        super().__init__()
        self._rect = QRectF(rect) if rect else QRectF(0, 0, 10, 10)

    @classmethod
    def of(cls, item: CalcItem) -> "CalcDrawingItem":
        drawing = cls(item.local_rect())
        drawing.stamp_svg = line_work_svg(item)
        drawing.their_picture_box = tuple(item.local_rect().getRect())
        drawing.setPos(item.pos())
        drawing.setTransform(item.transform())
        drawing.setTransformOriginPoint(item.transformOriginPoint())
        drawing.setRotation(item._turn_while_editing if item._turn_while_editing is not None
                            else item.rotation())
        return drawing

    def local_rect(self) -> QRectF:
        return QRectF(self._rect)

    def set_local_rect(self, rect: QRectF) -> None:
        self.prepareGeometryChange()
        self._rect = QRectF(rect)

    def paint_content(self, painter: QPainter) -> None:
        pass                                    # it is all in its line work

    def serialize(self) -> dict:
        data = self.base_dict()
        data["rect"] = [self._rect.x(), self._rect.y(), self._rect.width(), self._rect.height()]
        return data

    def deserialize(self, data: dict) -> None:
        self._rect = QRectF(*data.get("rect", [0, 0, 10, 10]))
        self.load_base(data)


# -- Calculation text (decision 22) ---------------------------------------------------

from .text import TextItem  # noqa: E402  (after the equation classes on purpose)


@register_item
class CalcTextItem(TextItem):
    """Calculation text: SMath's text regions, as a MarkForge text box.

    A separate type from a text box, with a default style of its own — plain,
    as SMath writes text: no frame, no fill, Arial 10 pt in black — that the
    user can change and that keeps a border and fill if given one. It is saved
    as a text annotation like any other text box, never flattened, and it has
    no effect on the calculation. It never takes a callout leader, and it sits
    on the calculation grid.
    """

    TYPE = "calc_text"
    NAME = "Calculation text"
    CAN_LEAD = False

    def __init__(self, text: str = "", rect: Optional[QRectF] = None):
        super().__init__(text, rect)
        plain = default_calc_text_style()
        for field_name in ("stroke", "fill", "fill_opacity", "width", "text_color",
                           "font_family", "font_size", "padding"):
            setattr(self.style, field_name, getattr(plain, field_name))
        if hasattr(self, "apply_style"):
            self.apply_style()

    def add_leader(self, *args, **kwargs):          # never a callout
        return None


def default_calc_text_style():
    """The look new Calculation text gets (Preferences can change it, phase 5)."""
    from .base import Style
    return Style(stroke="", fill="", fill_opacity=0.0, width=0.0, text_color="#000000",
                 font_family="Arial", font_size=10.0, padding=2.0)
