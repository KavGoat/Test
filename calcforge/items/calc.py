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
        self._preview = None
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
    # conditional formatting (calc/condformat.py): its own rules, or a preset
    cond_rules: list = None
    cond_preset: str = ""

    def _settings(self):
        frame = self._page_frame()
        document = getattr(frame, "document", None)
        return getattr(document, "settings", None)

    def _looking(self):
        from ..calc.condformat import looking
        return looking(self, self._settings())

    def relayout(self) -> None:
        self.prepareGeometryChange()
        if self._view is not None:
            self._view.focused = self.focused
            frame = self._page_frame()
            if frame is not None:
                room = calc_area(frame).right() - self.pos().x()
                self._view.max_width = max(room, 0.0) * PX_PER_PT
            with self._looking():
                self._view.relayout()
            from ..calc.condformat import look_for
            self._last_look = look_for(self, self._settings())
        self.geometryChanged.emit()
        self.update()

    def _frame_px(self) -> QRectF:
        view = self._view or self._preview_view()
        if view is None:
            return QRectF(0, 0, 20, 24)
        return view.frame_rect()

    def _preview_view(self):
        """Off any page (a tool held from a tool set, before it is put down):
        WebSMath's drawing of what it says, as typed and not yet calculated —
        it calculates once it is down, where it lands."""
        if self.region is not None:
            return None
        cached = getattr(self, "_preview", None)
        if cached is not None:
            return cached
        try:
            from ..calc.record import add_region_from_data
            from ..calc.ui.layout import Style as MathStyle
            from ..calc.worksheet import Worksheet
            scratch = Worksheet()
            region = add_region_from_data(scratch, 0, 0, self._data)
            region.pending = True
            view = _PageRegionView(region, scratch, MathStyle(region.font_size))
            view.relayout()
        except Exception:                       # noqa: BLE001  (a preview only)
            view = None
        self._preview = view
        return view

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
        view = self._view or self._preview_view()
        if view is None:
            return
        with self._looking():
            self._paint_view(painter, view)

    def _paint_view(self, painter: QPainter, view) -> None:
        painter.save()
        painter.scale(PT_PER_PX, PT_PER_PX)
        device = painter.device()
        picture = QPicture()
        if device is None or (device.logicalDpiX() == picture.logicalDpiX()
                              and device.logicalDpiY() == picture.logicalDpiY()):
            view.paint(painter, None)
        else:
            # SMath's layout sizes its fonts in points, and Qt turns points
            # into pixels by the device's resolution: drawn straight onto a
            # PDF writer or a printer the letters come out bigger than the
            # layout they were measured for (at 300 dpi they run into each
            # other). Recorded at the screen's resolution and played back, the
            # drawing — text still text — is scaled as one, exactly.
            recorder = QPainter(picture)
            recorder.setRenderHints(painter.renderHints())
            view.paint(recorder, None)
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
        if self.cond_rules:
            data["cond_rules"] = [dict(r) for r in self.cond_rules]
        if self.cond_preset:
            data["cond_preset"] = self.cond_preset
        return data

    def deserialize(self, data: dict) -> None:
        self.load_base(data)
        self.cond_rules = [dict(r) for r in data.get("cond_rules", [])] or None
        self.cond_preset = str(data.get("cond_preset", "") or "")
        self._data = dict(data.get("calc") or EMPTY)
        self._preview = None

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
        done = set()
        for region_id in ids or ():
            item = items.get(region_id)
            if item is not None:
                item.relayout()
                done.add(region_id)
        # conditional formatting: an equation whose rules now give another
        # look is drawn again (a definition shows no result to say so)
        settings = getattr(sheet.document, "settings", None)
        store = getattr(settings, "calc_rules", None) or {}
        if store.get("by_name") or any(i.cond_rules or i.cond_preset for i in items.values()):
            from ..calc.condformat import look_for
            for region_id, item in list(items.items()):
                look = look_for(item, settings)
                if look != getattr(item, "_last_look", {}):
                    item._last_look = look
                    if region_id not in done:
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

    def _paint_cursor(self, p: QPainter) -> None:
        """WebSMath's caret everywhere but on an empty slot. There WebSMath
        puts the bar a fixed 7 px in, through the placeholder square's right
        edge, with the underline starting before the square — on screen the
        square looked boxed in white (the user, 2026-10-01). Here the
        underline runs exactly under the square and the bar stands just
        clear of it, measured from the square itself, at any size."""
        ed = self.editor
        info = self._row_info(ed.row)
        if info is None or ed.row.items:
            super()._paint_cursor(p)
            return
        from ..calc.ui.layout import Layouter
        lay = Layouter(self.style)
        square = lay.placeholder()
        # an empty row is a line of text tall: its size against a full-size
        # line says how small it is (an exponent, a fraction's part)
        line = lay.text("H", self.style.font(1.0))
        scale = min(1.0, info.asc / max(line.asc, 1e-6))
        left, width = square.box[0] * scale, square.box[1] * scale
        x0 = info.x + left
        bar = x0 + width + 1.5          # just clear of it: no sliver, no merging
        underline_y = info.base + info.desc + 0.5
        p.setPen(QPen(Qt.black, 1))
        p.drawLine(QPointF(x0, underline_y), QPointF(bar, underline_y))
        p.drawLine(QPointF(bar, info.base - info.asc), QPointF(bar, underline_y))

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


# -- Calculation blocks (phase 7) ----------------------------------------------------

def unturned_px(frame, x: float, y: float, turns: int) -> tuple:
    """A point on a page turned *turns* quarter turns clockwise since it was
    written, back where it was on the page as written, in SMath pixels."""
    width, height = frame.page.width_pt, frame.page.height_pt
    for _ in range(turns):
        # undo one clockwise turn: (x, y) -> (y, width - x)
        x, y = y, width - x
        width, height = height, width
    return x * PX_PER_PT, y * PX_PER_PT


def default_block_style():
    """A block's frame: a thin grey line, no fill."""
    from .base import Style
    return Style(stroke="#8c8c8c", fill="", fill_opacity=0.0, width=0.75)


@register_item
class CalcBlockItem(MarkupItem):
    """A calculation block: a markup of its own that holds equations.

    The equations whose top-left is inside it are its members: they calculate
    exactly as any other equation does, and move, copy and delete with the
    block. With Self-contained on, what they define stays inside the block —
    the block still reads everything defined above it, but nothing after it
    sees its names (the same design check twice on one sheet, with the same
    names). Like an equation it is page drawing, never an annotation, and it
    always prints.
    """

    TYPE = "calc_block"
    NAME = "Calculation block"
    ROTATABLE = False
    IS_CALC = True
    region = None                       # it is not an equation itself
    _turn_while_editing = None
    focused = False
    warning = ""
    # Like a text box: closed, one click anywhere on it picks it up (with its
    # equations); double-clicked, it is open and what is in it is edited,
    # until a click outside it or Esc. Not part of the record.
    opened = False

    def __init__(self, rect: Optional[QRectF] = None):
        super().__init__()
        self._rect = QRectF(rect) if rect else QRectF(0, 0, 36 * GRID_PX * PT_PER_PX,
                                                      12 * GRID_PX * PT_PER_PX)
        self.self_contained = False
        self.style = default_block_style()
        self._sheet = None
        # Its box (scene) and rect at the end of the last gesture: what it held
        # then is what it holds — equations aren't dragged in or out of a
        # block (the user: it is like a little page of its own).
        self._settled_box = None
        self._settled_rect = None
        # Behind the equations in it, so a click on one finds the equation.
        self.setZValue(-1)

    # -- where it is --------------------------------------------------------------
    def _page_frame(self):
        frame = self.parentItem()
        return frame if frame is not None and hasattr(frame, "page") \
            and hasattr(frame, "document") else None

    def page_turns(self) -> int:
        return int(round(self.rotation() / 90.0)) % 4

    def reading_rect_px(self, frame=None) -> tuple:
        """(left, top, right, bottom) on its page as written, in SMath pixels."""
        frame = frame or self._page_frame()
        r = self._rect.normalized()
        corners = [self.mapToParent(p) for p in (r.topLeft(), r.topRight(),
                                                 r.bottomRight(), r.bottomLeft())]
        points = [unturned_px(frame, c.x(), c.y(), self.page_turns()) for c in corners]
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        return min(xs), min(ys), max(xs), max(ys)

    def _tell_the_sheet(self) -> None:
        frame = self._page_frame()
        if frame is None or self.scene() is None:
            self._leave_the_sheet()
            return
        if self._sheet is None:
            self._sheet = sheet_for(frame.document)
            _connect(self._sheet, frame.scene())
        self._sheet.set_block(self.uid, frame.page.uid, self.reading_rect_px(frame),
                              self.self_contained)

    def _leave_the_sheet(self) -> None:
        if self._sheet is not None:
            self._sheet.remove_block(self.uid)
            self._sheet = None

    def itemChange(self, change, value):
        result = super().itemChange(change, value)
        if change in (QGraphicsItem.ItemParentHasChanged, QGraphicsItem.ItemSceneHasChanged,
                      QGraphicsItem.ItemPositionHasChanged,
                      QGraphicsItem.ItemRotationHasChanged):
            self._tell_the_sheet()
        if change in (QGraphicsItem.ItemParentHasChanged, QGraphicsItem.ItemSceneHasChanged):
            self.settle()
        return result

    def scene_box(self) -> QRectF:
        return self.mapRectToScene(self._rect.normalized())

    def settle(self) -> None:
        """What it holds now is what it holds (the end of a gesture)."""
        if self.scene() is not None:
            self._settled_box = self.scene_box()
            self._settled_rect = QRectF(self._rect)
            self._settled_pos = QPointF(self.pos())

    def set_self_contained(self, on: bool) -> None:
        self.self_contained = bool(on)
        self.touch()
        self.update()
        self._tell_the_sheet()

    def members(self) -> list:
        """The equations and Calculation text whose top-left is inside it."""
        frame = self._page_frame()
        if frame is None:
            return []
        box = self.mapRectToParent(self._rect.normalized())
        found = []
        for item in frame.markups():
            if item is self or not isinstance(item, (CalcItem, CalcTextItem)):
                continue
            if box.contains(item.pos()):
                found.append(item)
        return found

    # -- geometry and drawing ------------------------------------------------------
    def local_rect(self) -> QRectF:
        return QRectF(self._rect)

    def set_local_rect(self, rect: QRectF) -> None:
        self.prepareGeometryChange()
        self._rect = QRectF(rect).normalized()
        self.update()
        self._tell_the_sheet()

    def relayout(self) -> None:
        self.update()

    def set_opened(self, on: bool) -> None:
        if bool(on) == self.opened:
            return
        self.prepareGeometryChange()
        self.opened = bool(on)
        self.update()

    def shape(self):
        """Closed, all of it: a click anywhere on it is a click on the block.
        Open, its frame only: a click inside is a click on what is in it (or
        on the page there, to type a new equation)."""
        from PySide6.QtGui import QPainterPath
        rect = self._rect.normalized()
        grow = 4.0
        path = QPainterPath()
        path.addRect(rect.adjusted(-grow, -grow, grow, grow))
        if self.opened and rect.width() > 2 * grow and rect.height() > 2 * grow:
            inner = QPainterPath()
            inner.addRect(rect.adjusted(grow, grow, -grow, -grow))
            path = path.subtracted(inner)
        return path

    def paint_content(self, painter: QPainter) -> None:
        rect = self._rect.normalized()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(self.style.pen() if self.style.stroke else QPen(Qt.NoPen))
        painter.setBrush(self.style.brush())
        painter.drawRect(rect)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        super().paint(painter, option, widget)
        frame = self._page_frame()
        if getattr(frame, "print_mode", False):
            return
        if self.opened:
            # On the screen only: it is open for editing, as a text box shows
            painter.save()
            pen = QPen(QColor("#1c7ed6"), 0)
            pen.setStyle(Qt.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self._rect.normalized().adjusted(-3, -3, 3, 3))
            painter.restore()
        if not self.self_contained:
            return
        # On the screen only: say it keeps its names to itself.
        painter.save()
        font = painter.font()
        font.setPointSizeF(6.5)
        painter.setFont(font)
        painter.setPen(QColor("#8c8c8c"))
        rect = self._rect.normalized()
        painter.drawText(QRectF(rect.left(), rect.top() - 10, rect.width(), 10),
                         Qt.AlignRight | Qt.AlignBottom, "Self-contained")
        painter.restore()

    def boundingRect(self) -> QRectF:
        return super().boundingRect().united(
            self._rect.normalized().adjusted(-4, -11, 4, 4))

    def summary(self) -> str:
        return "Self-contained" if self.self_contained else ""

    # -- the record ---------------------------------------------------------------------
    def serialize(self) -> dict:
        data = self.base_dict()
        data["rect"] = [self._rect.x(), self._rect.y(), self._rect.width(), self._rect.height()]
        data["self_contained"] = self.self_contained
        return data

    def deserialize(self, data: dict) -> None:
        self._rect = QRectF(*data.get("rect", [0, 0, 100, 60]))
        self.self_contained = bool(data.get("self_contained", False))
        self.load_base(data)


def closed_block_of(item):
    """The closed calculation block *item* is in, or None: while its block is
    closed an equation is part of it, and a click on it is a click on the
    block (the smallest, when one block sits in another)."""
    if not isinstance(item, (CalcItem, CalcTextItem)):
        return None
    frame = item.parentItem()
    if frame is None or not hasattr(frame, "markups"):
        return None
    found = None
    for other in frame.markups():
        if isinstance(other, CalcBlockItem) and not other.opened \
                and item in other.members():
            if found is None or (other._rect.width() * other._rect.height()
                                 < found._rect.width() * found._rect.height()):
                found = other
    return found


def with_block_members(items: list) -> list:
    """*items*, and the members of every calculation block among them (a
    block moves, copies and deletes with what is in it)."""
    out = list(items)
    seen = {id(i) for i in out}
    for item in items:
        if isinstance(item, CalcBlockItem):
            for member in item.members():
                if id(member) not in seen:
                    seen.add(id(member))
                    out.append(member)
    return out


# -- a measurement as a variable (decision 24) -------------------------------------------

import re as _re  # noqa: E402

# a letter, then letters and digits, and at most one subscript after a dot (L.beam)
NAME_PATTERN = _re.compile(r"^[^\W\d_][^\W_]*(\.[^\W_]+)?$")


def smath_variable_name(name: str) -> str:
    """A name as SMath writes it: a subscript after a dot. L_beam (as other
    programs write it) becomes L.beam."""
    name = (name or "").strip()
    if "_" in name and "." not in name:
        name = name.replace("_", ".", 1)
    return name


def valid_variable_name(name: str) -> bool:
    """A name SMath would take as a variable: a letter first, then letters,
    digits, _ or . (a subscript)."""
    return bool(NAME_PATTERN.match(name or ""))


def _plain_number(value: float) -> str:
    """A number as typed digits: never 1e-05, which SMath would read as e."""
    from decimal import Decimal
    text = format(Decimal(repr(float(value))), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def measured_keys(name: str, quantity) -> Optional[str]:
    """The keystrokes that define *name* as *quantity* in SMath: the value in
    the measurement's own unit (6250 mm stays 6250'mm), an angle in degrees."""
    from ..core.units import unit_text

    if quantity is None:
        return None
    unit = unit_text(quantity.units, plain=False)
    if unit == "deg":
        unit = "°"
    number = _plain_number(quantity.magnitude)
    return f"{name}:{number}" + (f"'{unit}" if unit else "")


class MeasureVariable:
    """The region a named measurement defines its variable with.

    It is an ordinary region of the document's worksheet — typed as SMath
    would type ``L:6250'mm`` — at the top-left of the measurement's box, so it
    is read in the same order an equation there would be. It has no equation
    item on the page: the measurement is what the reader sees.
    """

    def __init__(self, measure):
        self.measure = measure
        self.region = None
        self._sheet = None
        self._keys = None

    def _frame(self):
        frame = self.measure.parentItem()
        return frame if frame is not None and hasattr(frame, "page") \
            and hasattr(frame, "document") else None

    def _position(self, frame) -> tuple:
        measure = self.measure
        box = measure.mapRectToParent(measure.local_rect().normalized())
        turns = int(round(measure.rotation() / 90.0)) % 4
        return unturned_px(frame, box.left(), box.top(), turns) if turns \
            else (box.left() * PX_PER_PT, box.top() * PX_PER_PT)

    def sync(self) -> None:
        measure = self.measure
        frame = self._frame()
        keys = None
        if measure.variable and valid_variable_name(measure.variable) \
                and frame is not None and measure.scene() is not None:
            keys = measured_keys(measure.variable, measure.value)
        if keys is None:
            self.drop()
            return
        x, y = self._position(frame)
        if self.region is not None and keys == self._keys:
            self._sheet.move(self.region, frame.page.uid, x, y)
            return
        self.drop()
        self._sheet = sheet_for(frame.document)
        _connect(self._sheet, frame.scene())
        self.region = self._sheet.add(_typed_region_data(keys), frame.page.uid, x, y)
        self.region.calcforge_source = "Measurement"
        self._keys = keys

    def drop(self) -> None:
        if self.region is not None and self._sheet is not None:
            self._sheet.remove(self.region)
        self.region = None
        self._keys = None


def _typed_region_data(keys: str) -> dict:
    """A region's record, as typing *keys* into SMath's editor makes it."""
    from ..calc.editor import MathEditor
    from ..calc.worksheet import Worksheet

    scratch = Worksheet()
    editor = MathEditor()
    region = scratch.add_region(0, 0, editor)
    for key in keys:
        editor.key(key)
    return region_to_data(region)



# -- keeping a block's equations its own ------------------------------------------------------

def _corner(item) -> QPointF:
    """Where an equation is, for which block holds it: its top-left on the scene."""
    parent = item.parentItem()
    return parent.mapToScene(item.pos()) if parent is not None else item.pos()


def _holder(blocks, point: QPointF, settled: bool):
    found, area = None, None
    for block in blocks:
        box = block._settled_box if settled else block.scene_box()
        if box is not None and box.contains(point):
            size = box.width() * box.height()
            if area is None or size < area:
                found, area = block, size
    return found


def blocks_holding(scene, moved: list) -> dict:
    """At the start of a drag: each equation being moved -> the block it is
    in, for the blocks not moving with it (they hold it while it moves)."""
    blocks = [i for i in scene.items() if isinstance(i, CalcBlockItem)]
    if not blocks:
        return {}
    moving = {id(item) for item, _ in moved}
    held = {}
    for item, _origin in moved:
        if isinstance(item, (CalcItem, CalcTextItem)) and item.parentItem() is not None:
            block = _holder(blocks, _corner(item), settled=True)
            if block is not None and id(block) not in moving:
                held[id(item)] = block
    return held


def stay_in_block(item, block) -> None:
    """Keep an equation inside its block while it is dragged: it stops at
    the edge rather than leaving and being put back when it is let go (the
    user, 2026-10-01)."""
    if block.scene() is None or item.parentItem() is None:
        return
    box = item.parentItem().mapRectFromScene(block.scene_box())
    size = item.local_rect()
    x = min(max(item.pos().x(), box.left()), box.right() - min(size.width(), box.width()) - 1)
    y = min(max(item.pos().y(), box.top()), box.bottom() - min(size.height(), box.height()) - 1)
    wanted = QPointF(max(x, box.left()), max(y, box.top()))
    if wanted != item.pos():
        item.setPos(wanted)


def keep_blocks_whole(scene, moved: list) -> str:
    """After a drag or nudge (*moved*: [(item, origin)], origin in the item's
    parent): an equation that was in a block stays in it, one that wasn't
    can't be dropped into one, and a block can't land on equations that
    aren't its own. Returns what to tell the user ('' if nothing was undone)."""
    blocks = [i for i in scene.items() if isinstance(i, CalcBlockItem)]
    if not blocks:
        return ""
    said = ""
    origin_of = {id(item): origin for item, origin in moved}

    def before_point(item) -> QPointF:
        origin = origin_of.get(id(item))
        parent = item.parentItem()
        if origin is not None and parent is not None:
            return parent.mapToScene(origin)
        return _corner(item)

    calc_items = [i for i in scene.items() if isinstance(i, (CalcItem, CalcTextItem))
                  and i.parentItem() is not None]
    # a block put down over equations that aren't its own: the whole move goes back
    for block in blocks:
        if id(block) not in origin_of:
            continue
        own = {id(i) for i in calc_items if block._settled_box is not None
               and _holder([block], before_point(i), settled=True) is block}
        if any(id(i) not in own and block.scene_box().contains(_corner(i)) for i in calc_items):
            for item, origin in moved:
                item.setPos(origin)
            said = "A block can't be put down over equations that aren't its own"
            break
    else:
        for item, origin in moved:
            if not isinstance(item, (CalcItem, CalcTextItem)):
                continue
            before = _holder(blocks, before_point(item), settled=True)
            now = _holder(blocks, _corner(item), settled=False)
            if before is now:
                continue
            if before is None:
                item.setPos(origin)                    # not dragged into a block
                said = "Equations can't be dragged into a block — type them inside it"
                continue
            # dragged out of its block: kept inside it, at the nearest place
            box = item.parentItem().mapRectFromScene(before.scene_box())
            size = item.local_rect()
            x = min(max(item.pos().x(), box.left()), box.right() - min(size.width(), box.width()) - 1)
            y = min(max(item.pos().y(), box.top()), box.bottom() - min(size.height(), box.height()) - 1)
            item.setPos(QPointF(max(x, box.left()), max(y, box.top())))
            said = "Equations stay in their block — it is a page of its own"
    for block in blocks:
        block.settle()
    return said


def keep_block_resize(block) -> str:
    """After a block's frame is dragged: it may not take in equations that
    weren't its own, or leave its own out. If it would, the resize goes back."""
    scene = block.scene()
    if scene is None or block._settled_box is None:
        return ""
    calc_items = [i for i in scene.items() if isinstance(i, (CalcItem, CalcTextItem))
                  and i.parentItem() is not None]
    before = {id(i) for i in calc_items if block._settled_box.contains(_corner(i))}
    now = {id(i) for i in calc_items if block.scene_box().contains(_corner(i))}
    if before == now:
        block.settle()
        return ""
    block.set_local_rect(QRectF(block._settled_rect))
    block.setPos(block._settled_pos)
    block.settle()
    return ("A block can't be made smaller than what is in it" if before - now
            else "A block can't be stretched over equations that aren't its own")
