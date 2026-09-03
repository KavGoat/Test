"""The canvas: one scene holding every page of the document.

A calculation sheet is read the way a PDF is read — scrolled through, not
turned page by page — so all the pages live in one scene, stacked down the
canvas with a gap between them. Each page is a :class:`PageFrame`: it draws
its own paper, edge, shadow, imported background, grid, margins and running
text, and owns its markups as child items.

Keeping markups as children of their page is what makes this cheap: an item's
position stays relative to the top-left of its own page, exactly as it is
saved, so nothing else in the application has to know where that page happens
to sit on the canvas today.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QImage, QLinearGradient, QPainter,
                           QPen, QPixmap)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject, QGraphicsScene

from ..core.document import MM_TO_PT, Document, Page
from ..theme import CANVAS, LIGHT
from ..items.base import MarkupItem, build_item
from ..items.media import ImageItem

ROW_TOLERANCE = 9.0        # points; items this close vertically share a row

PAPER = QColor("#ffffff")
PAGE_EDGE = QColor(92, 98, 108)        # the line around the sheet
PAGE_GAP = 26.0                        # points of desk between pages
SHADOW_DEPTH = 7.0                     # how far the shadow reaches


def _order_key(item):
    """A total order for reading: position first, then something unchanging.

    Two markups can sit at exactly the same spot — a duplicate before it is
    dragged clear, say. Position alone would then leave their order up to
    whatever the scene happened to hand back, and in a document where order
    decides what is defined, that means the same sheet could evaluate two
    different ways. The uid breaks the tie the same way every time.
    """
    position = item.pos()
    return (position.y(), position.x(), item.zValue(), getattr(item, "uid", ""))


def reading_order(items: list) -> list:
    """Sort *items* top-left to bottom-right, banding near-equal tops into rows."""
    remaining = sorted(items, key=_order_key)
    ordered: list = []
    row: list = []
    row_top = None
    for item in remaining:
        top = item.pos().y()
        if row_top is None or abs(top - row_top) <= ROW_TOLERANCE:
            if row_top is None:
                row_top = top
            row.append(item)
        else:
            ordered.extend(sorted(row, key=lambda i: _order_key(i)[1:]))
            row = [item]
            row_top = top
    ordered.extend(sorted(row, key=lambda i: _order_key(i)[1:]))
    return ordered


def detach(item: MarkupItem) -> None:
    """Take a markup off whatever page it is on.

    An item always leaves the page it is actually on. A draft begun on one page
    and abandoned after scrolling to another would otherwise be removed from
    the wrong one, which Qt ignores with a warning while leaving the item
    stranded where it came from.
    """
    frame = item.parentItem()
    if isinstance(frame, PageFrame):
        frame.remove_markup(item)
        return
    scene = item.scene()
    if scene is not None:
        scene.removeItem(item)


MARGIN_PEN = QColor(120, 160, 220, 120)
GRID_PEN = QColor(180, 195, 210, 110)
GRID_PEN_MAJOR = QColor(150, 170, 195, 150)


class PageFrame(QGraphicsObject):
    """One page of the document, and everything drawn on it."""

    itemsChanged = Signal()

    def __init__(self, page: Page, document: Document):
        super().__init__()
        self.page = page
        self.document = document
        self.workspace = document.workspace
        self._background: Optional[QPixmap] = None
        self._logo: Optional[QPixmap] = None
        self._logo_key = ""
        self.print_mode = False
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        # Behind every markup, and behind the desk's own shadow drawing.
        self.setZValue(-1000.0)

    # -- geometry ----------------------------------------------------------
    def page_rect(self) -> QRectF:
        return QRectF(0, 0, self.page.width_pt, self.page.height_pt)

    def boundingRect(self) -> QRectF:
        return self.page_rect().adjusted(-1, -1, SHADOW_DEPTH + 1, SHADOW_DEPTH + 1)

    def update_scene_rect(self) -> None:
        """The page's size changed; the canvas has to be laid out again."""
        self.prepareGeometryChange()
        scene = self.scene()
        if isinstance(scene, DocumentScene):
            scene.layout_pages()

    # -- background --------------------------------------------------------
    def load_background(self) -> None:
        data = self.document.asset(self.page.background_key)
        if not data:
            self._background = None
            return
        pixmap = QPixmap()
        pixmap.loadFromData(QByteArray(data))
        self._background = pixmap if not pixmap.isNull() else None

    def paint(self, painter: QPainter, option, widget=None) -> None:
        rect = self.page_rect()
        if not self.print_mode:
            self._paint_shadow(painter, rect)
        painter.fillRect(rect, PAPER)
        if self._background is None and self.page.background_key:
            self.load_background()
        if self._background is not None:
            painter.save()
            painter.setOpacity(self.page.background_opacity)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawPixmap(rect, self._background, QRectF(self._background.rect()))
            painter.restore()
        if not self.print_mode:
            self._paint_grid(painter, rect)
            self._paint_margins(painter)
        self._paint_running_text(painter)
        if not self.print_mode:
            # Last, so nothing drawn on the page can paint over its own edge.
            painter.save()
            pen = QPen(PAGE_EDGE)
            pen.setWidthF(0)              # one device pixel, at any zoom
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect)
            painter.restore()

    def _paint_shadow(self, painter: QPainter, rect: QRectF) -> None:
        """A soft edge under the sheet, so it reads as paper lying on a desk."""
        painter.save()
        painter.setPen(Qt.NoPen)
        right = QLinearGradient(rect.right(), 0, rect.right() + SHADOW_DEPTH, 0)
        right.setColorAt(0.0, QColor(0, 0, 0, 62))
        right.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(QRectF(rect.right(), rect.top() + SHADOW_DEPTH * 0.5,
                                SHADOW_DEPTH, rect.height()), QBrush(right))
        below = QLinearGradient(0, rect.bottom(), 0, rect.bottom() + SHADOW_DEPTH)
        below.setColorAt(0.0, QColor(0, 0, 0, 62))
        below.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(QRectF(rect.left() + SHADOW_DEPTH * 0.5, rect.bottom(),
                                rect.width(), SHADOW_DEPTH), QBrush(below))
        painter.restore()

    def _paint_grid(self, painter: QPainter, page_rect: QRectF) -> None:
        settings = self.document.settings
        if not settings.show_grid:
            return
        step = max(settings.grid_mm, 1.0) * MM_TO_PT
        painter.save()
        minor = QPen(GRID_PEN)
        minor.setWidthF(0.3)
        major = QPen(GRID_PEN_MAJOR)
        major.setWidthF(0.6)
        index = 0
        x = 0.0
        while x <= page_rect.right():
            painter.setPen(major if index % 5 == 0 else minor)
            painter.drawLine(QPointF(x, page_rect.top()), QPointF(x, page_rect.bottom()))
            x += step
            index += 1
        index = 0
        y = 0.0
        while y <= page_rect.bottom():
            painter.setPen(major if index % 5 == 0 else minor)
            painter.drawLine(QPointF(page_rect.left(), y), QPointF(page_rect.right(), y))
            y += step
            index += 1
        painter.restore()

    def _paint_margins(self, painter: QPainter) -> None:
        if not self.document.settings.show_margins:
            return
        x, y, width, height = self.page.setup.content_rect_pt
        pen = QPen(MARGIN_PEN)
        pen.setWidthF(0.6)
        pen.setStyle(Qt.DashLine)
        painter.save()
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(x, y, width, height))
        painter.restore()

    def load_logo(self) -> Optional[QPixmap]:
        """The header/footer logo, decoded once and kept."""
        settings = self.document.settings
        key = settings.logo_key
        if not key:
            self._logo = None
            self._logo_key = ""
            return None
        if getattr(self, "_logo_key", "") != key:
            data = self.document.asset(key)
            pixmap = QPixmap()
            if data:
                pixmap.loadFromData(QByteArray(data))
            self._logo = pixmap if not pixmap.isNull() else None
            self._logo_key = key
        return self._logo

    def _logo_rect(self, band: QRectF, slot: str) -> QRectF:
        """Where the logo sits in its band, scaled to the height asked for.

        Never taller than the band it is in: a logo that spilled past the
        margin would print over the paper's edge.
        """
        logo = self.load_logo()
        if logo is None or logo.height() <= 0:
            return QRectF()
        height = min(self.document.settings.logo_height_mm * MM_TO_PT, band.height())
        width = height * logo.width() / logo.height()
        width = min(width, band.width())
        if slot.endswith("right"):
            x = band.right() - width
        elif slot.endswith("center"):
            x = band.center().x() - width / 2
        else:
            x = band.left()
        return QRectF(x, band.center().y() - height / 2, width, height)

    def _paint_running_text(self, painter: QPainter) -> None:
        settings = self.document.settings
        index = self.document.index_of(self.page)
        left, top, width, height = self.page.setup.content_rect_pt
        from ..core.typography import page_font
        painter.save()
        painter.setFont(page_font("", 8.0))
        painter.setPen(QPen(QColor(90, 96, 106)))
        if settings.show_header:
            # The band is as deep as it has to be for the logo, but never
            # deeper than the margin it lives in.
            band = self._band(QRectF(left, top - 18, width, 14), "header", top)
            self._paint_three(painter, band, settings.header_left,
                              settings.header_center, settings.header_right,
                              index, "header")
            pen = QPen(QColor(190, 196, 206))
            pen.setWidthF(0.5)
            painter.setPen(pen)
            painter.drawLine(QPointF(left, top - 4), QPointF(left + width, top - 4))
            painter.setPen(QPen(QColor(90, 96, 106)))
        if settings.show_footer:
            band = self._band(QRectF(left, top + height + 5, width, 14), "footer",
                              self.page.height_pt - (top + height))
            self._paint_three(painter, band, settings.footer_left,
                              settings.footer_center, settings.footer_right,
                              index, "footer")
            pen = QPen(QColor(190, 196, 206))
            pen.setWidthF(0.5)
            painter.setPen(pen)
            painter.drawLine(QPointF(left, top + height + 3),
                             QPointF(left + width, top + height + 3))
        painter.restore()

    def _band(self, box: QRectF, which: str, room: float) -> QRectF:
        """Grow the header or footer band to hold the logo, within the margin."""
        settings = self.document.settings
        if not settings.logo_key or not settings.logo_slot.startswith(which):
            return box
        wanted = min(settings.logo_height_mm * MM_TO_PT, max(room - 8.0, 8.0))
        if wanted <= box.height():
            return box
        if which == "header":
            return QRectF(box.left(), box.bottom() - wanted, box.width(), wanted)
        return QRectF(box.left(), box.top(), box.width(), wanted)

    def _paint_three(self, painter: QPainter, box: QRectF, left: str, center: str,
                     right: str, index: int, which: str = "") -> None:
        settings = self.document.settings
        slot = settings.logo_slot if settings.logo_key else ""
        logo_rect = QRectF()
        if slot.startswith(which) and which:
            logo_rect = self._logo_rect(box, slot)
            if not logo_rect.isEmpty():
                painter.save()
                painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
                painter.drawPixmap(logo_rect, self._logo,
                                   QRectF(self._logo.rect()))
                painter.restore()

        def room(alignment: str) -> QRectF:
            """The text box for one slot, stepped aside from the logo."""
            if logo_rect.isEmpty() or not slot.endswith(alignment):
                return box
            gap = logo_rect.width() + 4.0
            if alignment == "right":
                return box.adjusted(0, 0, -gap, 0)
            if alignment == "left":
                return box.adjusted(gap, 0, 0, 0)
            return box                      # centred: the logo is behind it

        if left:
            painter.drawText(room("left"), Qt.AlignLeft | Qt.AlignVCenter,
                             self.document.expand_fields(left, index))
        if center:
            painter.drawText(room("center"), Qt.AlignHCenter | Qt.AlignVCenter,
                             self.document.expand_fields(center, index))
        if right:
            painter.drawText(room("right"), Qt.AlignRight | Qt.AlignVCenter,
                             self.document.expand_fields(right, index))

    # -- items -------------------------------------------------------------
    def markups(self) -> list[MarkupItem]:
        return [item for item in self.childItems() if isinstance(item, MarkupItem)]

    def ordered_markups(self) -> list[MarkupItem]:
        """Reading order: top-left to bottom-right, the way SMath evaluates.

        Items whose tops are within a line's height of each other count as one
        row and are read left to right, so a value placed beside another still
        evaluates after it rather than before.
        """
        return reading_order(self.markups())

    def add_markup(self, item: MarkupItem, position: Optional[QPointF] = None) -> MarkupItem:
        if position is not None:
            item.setPos(position)
        if not item.zValue():
            item.setZValue(self.next_z())
        if isinstance(item, ImageItem):
            item.load_from_document(self.document)
        item.setParentItem(self)
        item.refresh(self.workspace, self.page)
        self.itemsChanged.emit()
        return item

    def remove_markup(self, item: MarkupItem) -> None:
        item.setParentItem(None)
        scene = item.scene()
        if scene is not None:
            scene.removeItem(item)
        self.itemsChanged.emit()

    def next_z(self) -> float:
        markups = self.markups()
        return (max((i.zValue() for i in markups), default=0.0) + 1.0) if markups else 1.0

    def serialize_items(self) -> list[dict]:
        return [item.serialize() for item in sorted(self.markups(), key=lambda i: i.zValue())]

    def load_items(self, data: list[dict]) -> None:
        for item in self.markups():
            self.remove_markup(item)
        for entry in data:
            item = build_item(entry)
            if item is None:
                continue
            if isinstance(item, ImageItem):
                item.load_from_document(self.document)
            item.setParentItem(self)
        self.refresh_items()
        self.itemsChanged.emit()

    def refresh_items(self) -> None:
        """Re-evaluate this page's items against the shared workspace.

        Only ever safe as part of a whole-document pass. On its own it
        evaluates this page against a workspace that already holds the
        definitions from the last pass, which turns every definition on the
        page into a check — the window recalculates instead.
        """
        for item in self.ordered_markups():
            item.refresh(self.workspace, self.page)

    def apply_layers(self) -> None:
        """Hide and lock items according to the layer they sit on."""
        for item in self.markups():
            layer = self.document.layer(item.layer)
            item.setVisible(layer.visible)
            movable = not item.locked and not layer.locked
            item.setFlag(QGraphicsItem.ItemIsMovable, movable)
            item.setFlag(QGraphicsItem.ItemIsSelectable, layer.visible)
            if not layer.visible:
                item.setSelected(False)

    def layer_prints(self, item) -> bool:
        layer = self.document.layer(item.layer)
        return layer.printable and layer.visible

    def assets_used(self) -> set[str]:
        used: set[str] = set()
        for item in self.markups():
            used |= item.assets_used()
        if self.page.background_key:
            used.add(self.page.background_key)
        return used

    # -- rendering ---------------------------------------------------------
    def render_page(self, painter: QPainter, target: QRectF, for_print: bool = True) -> None:
        """Draw the whole page into *target*, hiding editing chrome."""
        scene = self.scene()
        if scene is None:
            return
        previous = self.print_mode
        self.print_mode = for_print
        # The selection is *hidden* for the render, not cleared and put back.
        # Putting it back is how a page thumbnail resurrected a selection the
        # reader had since let go of: the thumbnail is drawn from a queued
        # refresh, so the restore landed after the clearing.
        hidden_handles = [item for item in self.markups() if item._handles_visible]
        chrome: list = []
        for item in self.markups():
            if hasattr(item, "set_chrome") and item.show_chrome:
                chrome.append(item)
                item.set_chrome(False)
            item._handles_visible = False
        hidden = [item for item in self.markups()
                  if for_print and (not item.printable or not self.layer_prints(item))]
        for item in hidden:
            item.setVisible(False)
        source = self.mapRectToScene(self.page_rect())
        scene.render(painter, target, source, Qt.IgnoreAspectRatio)
        for item in hidden:
            item.setVisible(self.document.layer(item.layer).visible)
        for item in chrome:
            item.set_chrome(True)
        for item in hidden_handles:
            item._handles_visible = True
        self.print_mode = previous

    def render_image(self, dpi: float = 150.0, for_print: bool = True,
                     region: Optional[QRectF] = None) -> QImage:
        """The page as pixels — or just *region* of it, in page coordinates.

        Rendering a whole A4 sheet at 300 dpi to take a picture of one detail
        of it costs about thirty megabytes and most of a second, all of which
        is then thrown away. Asking for the part that is wanted costs what
        that part is worth.
        """
        scale = dpi / 72.0
        box = QRectF(0, 0, self.page.width_pt, self.page.height_pt)
        if region is not None:
            box = QRectF(region).normalized().intersected(box)
        if box.width() <= 0 or box.height() <= 0:
            return QImage()
        width = max(int(box.width() * scale), 1)
        height = max(int(box.height() * scale), 1)
        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(Qt.white)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.translate(-box.left() * scale, -box.top() * scale)
        self.render_page(painter,
                         QRectF(0, 0, self.page.width_pt * scale,
                                self.page.height_pt * scale), for_print)
        painter.end()
        return image


class DocumentScene(QGraphicsScene):
    """Every page of the document, stacked down one continuous canvas."""

    itemsChanged = Signal()
    selectionInfoChanged = Signal()

    def __init__(self, document: Document):
        super().__init__()
        self.document = document
        self.workspace = document.workspace
        self.frames: list[PageFrame] = []
        self.print_mode = False
        # Markups are dragged, resized and re-laid-out constantly, and a
        # calculation changes shape every time a character is typed into it.
        # Qt's spatial index assumes the opposite, and any bounding rectangle
        # that changes without it being told leaves it dereferencing stale
        # geometry — a crash, not a glitch.  A calculation sheet holds hundreds
        # of items, not hundreds of thousands, so a linear scan is cheaper than
        # the index would have been anyway.
        self.setItemIndexMethod(QGraphicsScene.NoIndex)
        self.set_canvas_colour(CANVAS[LIGHT])
        self.selectionChanged.connect(self.selectionInfoChanged.emit)

    def set_canvas_colour(self, colour: str) -> None:
        self.setBackgroundBrush(QBrush(QColor(colour)))

    # -- pages -------------------------------------------------------------
    def add_frame(self, page: Page) -> PageFrame:
        frame = PageFrame(page, self.document)
        self.addItem(frame)
        frame.itemsChanged.connect(self.itemsChanged.emit)
        self.frames.append(frame)
        return frame

    def clear_frames(self) -> None:
        for frame in self.frames:
            self.removeItem(frame)
        self.frames = []

    def layout_pages(self) -> None:
        """Stack the pages down the canvas, centred on the widest one."""
        widest = max((frame.page.width_pt for frame in self.frames), default=0.0)
        y = 0.0
        for frame in self.frames:
            frame.setPos((widest - frame.page.width_pt) / 2.0, y)
            y += frame.page.height_pt + PAGE_GAP
        height = max(y - PAGE_GAP, 0.0)
        # A generous margin of desk, so the first and last pages are not welded
        # to the edge of the window.
        self.setSceneRect(QRectF(-PAGE_GAP, -PAGE_GAP,
                                 widest + 2 * PAGE_GAP, height + 2 * PAGE_GAP))

    def frame_for(self, page: Page) -> Optional[PageFrame]:
        for frame in self.frames:
            if frame.page is page:
                return frame
        return None

    def frame_at(self, scene_pos: QPointF) -> Optional[PageFrame]:
        """The page under a point — or the nearest one, for a point on the desk."""
        if not self.frames:
            return None
        best, best_distance = None, float("inf")
        for frame in self.frames:
            rect = frame.mapRectToScene(frame.page_rect())
            if rect.contains(scene_pos):
                return frame
            centre = rect.center()
            distance = abs(centre.y() - scene_pos.y())
            if distance < best_distance:
                best, best_distance = frame, distance
        return best

    def index_at(self, scene_pos: QPointF) -> int:
        frame = self.frame_at(scene_pos)
        return self.frames.index(frame) if frame in self.frames else 0

    def page_top(self, index: int) -> float:
        if 0 <= index < len(self.frames):
            return self.frames[index].pos().y()
        return 0.0

    # -- items across the whole document ------------------------------------
    def markups(self) -> list[MarkupItem]:
        return [item for item in self.items() if isinstance(item, MarkupItem)]

    def ordered_markups(self) -> list[MarkupItem]:
        """The whole document in reading order: page by page, each top-left
        to bottom-right. This is the order the document evaluates in."""
        ordered: list[MarkupItem] = []
        for frame in self.frames:
            ordered.extend(frame.ordered_markups())
        return ordered

    def apply_layers(self) -> None:
        for frame in self.frames:
            frame.apply_layers()

    def refresh_items(self) -> None:
        for frame in self.frames:
            frame.refresh_items()

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        # Qt's own drawBackground would paint the brush; this one replaces it,
        # so the desk the sheets lie on has to be painted here.
        painter.fillRect(rect, self.backgroundBrush())
