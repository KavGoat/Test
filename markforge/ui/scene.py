"""The canvas: one scene holding every page of the document.

A drawing set is read scrolled through, not turned page by page, so all the
pages live in one scene, stacked down the canvas with a gap between them. Each page is a :class:`PageFrame`: it draws
its own paper, edge, shadow, imported background, grid, margins and running
text, and owns its markups as child items.

Keeping markups as children of their page is what makes this cheap: an item's
position stays relative to the top-left of its own page, exactly as it is
saved, so nothing else in the application has to know where that page happens
to sit on the canvas today.
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QImage, QLinearGradient, QPainter,
                           QPen, QPicture, QPixmap)
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
FOOTER_DEPTH = 14.0                    # how deep the running footer is


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


def _painted_scale(painter) -> float:
    """Pixels per point, the way this painter is set up to draw."""
    shape = painter.transform()
    across = math.hypot(shape.m11(), shape.m12())
    down = math.hypot(shape.m21(), shape.m22())
    return max(across, down, 0.01)


def _exposed_part(option, whole: QRectF) -> QRectF:
    """The part of the page this repaint is actually for."""
    exposed = getattr(option, "exposedRect", None)
    if exposed is None:
        return QRectF(whole)
    box = QRectF(exposed)
    return QRectF(whole) if box.isEmpty() else box


def _region_to_draw(wanted: QRectF, whole: QRectF, scale: float,
                    most_pixels: int) -> tuple[QRectF, float]:
    """A little more than is being looked at, held under what can be drawn.

    A margin round the exposed part means a small scroll does not start another
    draw. If the margin will not fit in the pixels available it goes first, and
    only then does the sharpness give way — losing the margin costs a redraw,
    losing the sharpness is the thing this is all for.
    """
    for margin in (0.35, 0.1, 0.0):
        region = wanted.adjusted(-wanted.width() * margin, -wanted.height() * margin,
                                 wanted.width() * margin, wanted.height() * margin)
        region = region.intersected(whole)
        if region.width() * scale * region.height() * scale <= most_pixels:
            return region, scale
    region = QRectF(wanted).intersected(whole)
    pixels = max(region.width() * scale * region.height() * scale, 1.0)
    return region, scale * (most_pixels / pixels) ** 0.5


def _sharpness_step(scale: float) -> float:
    """The resolution to ask for, in steps rather than continuously.

    Re-drawing the page on every notch of the wheel would be all wait and no
    picture, so the size asked for doubles rather than creeping: a zoom is one
    re-draw, not fifty.
    """
    step = 0.5
    while step < scale and step < 32.0:
        step *= 2.0
    return step


class PageFrame(QGraphicsObject):
    """One page of the document, and everything drawn on it."""

    itemsChanged = Signal()

    def __init__(self, page: Page, document: Document):
        super().__init__()
        self.page = page
        self.document = document
        self._background: Optional[QPixmap] = None
        # The part of the page drawn from the source PDF at the size it is
        # being looked at, and where it belongs. A page imported from a PDF
        # shows its stored thumbnail the instant it opens and then this over
        # the top of it, so what is on screen is as sharp as the file is
        # rather than as sharp as one guess about resolution made once.
        self._sharp: Optional[QPixmap] = None
        self._sharp_region = QRectF()
        self._sharp_scale = 0.0
        self._logo: Optional[QPixmap] = None
        self._logo_key = ""
        self.print_mode = False
        self._pdf_overlay = False
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        # Behind every markup, and behind the desk's own shadow drawing.
        self.setZValue(-1000.0)

    def shows(self, key) -> bool:
        """Whether a tile or sheet that has just been drawn belongs here."""
        page = self.page
        return (page.pdf_key is not None and key.source == page.pdf_key
                and key.index == page.pdf_page_index)

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

    def forget_sharp_background(self) -> None:
        self._sharp = None
        self._sharp_region = QRectF()
        self._sharp_scale = 0.0

    def paint_the_pdf(self, painter: QPainter, looking_at: QRectF,
                      scale: float) -> bool:
        """Draw the source page under the markups. Says whether it drew.

        Nothing is rendered here. The tile cache is asked for the squares of
        the page on screen at the zoom on screen; whatever is ready is drawn,
        and whatever is not is asked for and will arrive in a moment, at which
        point this part of the page is repainted. Under the tiles goes the
        small picture of the whole page, so what shows before they arrive is
        the page, soft, rather than a hole.

        Printing does not go through the tiles. It wants the whole page at
        one resolution and is entitled to wait for it.
        """
        page = self.page
        if page.pdf_key is None or page.pdf_page_index is None:
            return False
        data = self.document.asset(page.pdf_key)
        if not data:
            return False
        from ..io import pdfio, pdftiles

        whole = self.page_rect()
        index = int(page.pdf_page_index)
        shown = bool(getattr(page, "pdf_annotations", True))
        painter.save()
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        drew = False
        if self.print_mode:
            # One render, at the resolution being printed, synchronously.
            step = max(min(scale, 8.0), 1.0)
            region, step = _region_to_draw(
                QRectF(looking_at).intersected(whole) or whole, whole, step,
                pdfio.MOST_LIVE_PIXELS)
            drawn = pdfio.LIVE.draw_region(page.pdf_key, data, index, whole,
                                           region, step, shown)
            if drawn is not None and not drawn.isNull():
                painter.drawImage(region, drawn, QRectF(drawn.rect()))
                drew = True
            painter.restore()
            return drew

        shown_part = QRectF(looking_at).intersected(whole)
        tiles: list = []
        missing = True
        if not shown_part.isEmpty():
            # A margin, so a small scroll lands on tiles that are already here.
            margin_x = shown_part.width() * 0.25
            margin_y = shown_part.height() * 0.25
            asked = shown_part.adjusted(-margin_x, -margin_y, margin_x, margin_y)
            tiles, missing = pdftiles.TILES.tiles(
                page.pdf_key, data, index, whole, scale, asked, shown)
        if missing:
            # Only while the tiles are still coming, and only the part of it
            # that is on screen: stretching the whole small picture over a
            # whole sheet on every repaint is the sort of thing that makes
            # scrolling a drawing feel like wading.
            sheet = pdftiles.TILES.sheet(page.pdf_key, data, index, whole, shown)
            if sheet is not None:
                part = shown_part if not shown_part.isEmpty() else whole
                across = sheet.width() / max(whole.width(), 1.0)
                down = sheet.height() / max(whole.height(), 1.0)
                painter.drawPixmap(
                    part, sheet,
                    QRectF(part.left() * across, part.top() * down,
                           part.width() * across, part.height() * down))
                drew = True
        for where, tile in tiles:
            painter.drawPixmap(where, tile, QRectF(tile.rect()))
            drew = True
        painter.restore()
        return drew

    def paint(self, painter: QPainter, option, widget=None) -> None:
        rect = self.page_rect()
        if not self.print_mode:
            self._paint_shadow(painter, rect)
        if not self._pdf_overlay:
            painter.fillRect(rect, PAPER)
            if self._background is None and self.page.background_key:
                self.load_background()
            painter.save()
            painter.setOpacity(self.page.background_opacity)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            if self._background is not None:
                painter.drawPixmap(rect, self._background,
                                   QRectF(self._background.rect()))
            self.paint_the_pdf(painter, _exposed_part(option, rect),
                               _painted_scale(painter))
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
        if not self.page.shows_a_grid(settings):
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
        if self.page.shows_a_header(settings):
            # The same the other way up: a header written above the top of
            # the paper is a header nobody reads.
            # The band is as deep as it has to be for the logo, but never
            # deeper than the margin it lives in.
            band = self._band(QRectF(left, max(top - 18, 3), width, 14),
                              "header", top)
            self._paint_three(painter, band, settings.header_left,
                              settings.header_center, settings.header_right,
                              index, "header")
            pen = QPen(QColor(190, 196, 206))
            pen.setWidthF(0.5)
            painter.setPen(pen)
            rule = band.bottom() + 4
            painter.drawLine(QPointF(left, rule), QPointF(left + width, rule))
            painter.setPen(QPen(QColor(90, 96, 106)))
        if self.page.shows_a_footer(settings):
            # A page that came in from a PDF has no margins to speak of, so
            # the footer used to be written five points below the bottom of
            # the paper, where nothing can see it. Wherever the margin puts
            # it, it is brought back far enough to be on the sheet.
            room = self.page.height_pt - (top + height)
            baseline = min(top + height + 5,
                           self.page.height_pt - FOOTER_DEPTH - 3)
            band = self._band(QRectF(left, baseline, width, 14), "footer", room)
            self._paint_three(painter, band, settings.footer_left,
                              settings.footer_center, settings.footer_right,
                              index, "footer")
            pen = QPen(QColor(190, 196, 206))
            pen.setWidthF(0.5)
            painter.setPen(pen)
            rule = band.top() - 2
            painter.drawLine(QPointF(left, rule), QPointF(left + width, rule))
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
        if hasattr(item, "load_from_document"):
            item.load_from_document(self.document)
        item.setParentItem(self)
        item.refresh(page=self.page)
        self.itemsChanged.emit()
        return item

    def remove_markup(self, item: MarkupItem) -> None:
        item.setParentItem(None)
        scene = item.scene()
        if scene is not None:
            scene.removeItem(item)
        self.itemsChanged.emit()

    def next_z(self) -> float:
        """The z a new markup goes on: over everything already drawn here.

        The page's own line work is not counted. It sits below every markup
        deliberately, and a new markup starting one above it would be at the
        bottom of the pile rather than the top.
        """
        drawn = [item for item in self.markups() if not item.from_drawing]
        return (max((i.zValue() for i in drawn), default=0.0) + 1.0) if drawn else 1.0

    def serialize_items(self) -> list[dict]:
        return [item.serialize() for item in sorted(self.markups(), key=lambda i: i.zValue())]

    def load_items(self, data: list[dict]) -> None:
        for item in self.markups():
            self.remove_markup(item)
        for entry in data:
            item = build_item(entry)
            if item is None:
                continue
            if hasattr(item, "load_from_document"):
                item.load_from_document(self.document)
            item.setParentItem(self)
        self.refresh_items()
        self.itemsChanged.emit()

    def refresh_items(self) -> None:
        """Work out again what every markup on this page reads."""
        for item in self.ordered_markups():
            item.refresh(page=self.page)

    def assets_used(self) -> set[str]:
        used: set[str] = set()
        for item in self.markups():
            used |= item.assets_used()
        if self.page.background_key:
            used.add(self.page.background_key)
        if self.page.pdf_key:
            used.add(self.page.pdf_key)
        return used

    # -- rendering ---------------------------------------------------------
    def render_page(self, painter: QPainter, target: QRectF, for_print: bool = True,
                    pdf_overlay: bool = False, without_markups: bool = False) -> None:
        """Draw the whole page into *target*, hiding editing chrome.

        With *without_markups*, only the page itself is drawn — the paper, the
        imported background, the grid, the running header and footer, the
        page's own line work rather than anybody's markup, and anything that
        has been flattened into the sheet, which is part of it now. That is what an export wants when the markups that are still
        markups are going into the file as real annotations instead of being
        painted into it.
        """
        scene = self.scene()
        if scene is None:
            return
        previous = self.print_mode
        previous_overlay = self._pdf_overlay
        self.print_mode = for_print
        self._pdf_overlay = bool(pdf_overlay)
        # The selection is *hidden* for the render, not cleared and put back.
        # Putting it back is how a page thumbnail resurrected a selection the
        # reader had since let go of: the thumbnail is drawn from a queued
        # refresh, so the restore landed after the clearing.
        hidden_handles = [item for item in self.markups() if item._handles_visible]
        chrome: list = []
        hidden: list = []
        try:
            for item in self.markups():
                if hasattr(item, "set_chrome") and item.show_chrome:
                    chrome.append(item)
                    item.set_chrome(False)
                item._handles_visible = False
            hidden = [item for item in self.markups()
                      if (without_markups and not item.flattened
                          and not item.from_drawing)
                      or (for_print and (not item.printable
                                         or (pdf_overlay and item.from_drawing)))]
            for item in hidden:
                item.setVisible(False)
            source = self.mapRectToScene(self.page_rect())
            scene.render(painter, target, source, Qt.IgnoreAspectRatio)
        finally:
            # Whatever happened while it was being drawn, the page goes back
            # to how it looks on screen. Leaving the handles off is how a
            # selected markup came back with no box round it — the selection
            # was there, but nothing was drawn to say so until something else
            # forced a repaint.
            for item in hidden:
                item.setVisible(not item.hidden)
            for item in chrome:
                item.set_chrome(True)
            for item in hidden_handles:
                item._handles_visible = True
                item.update()
            self.print_mode = previous
            self._pdf_overlay = previous_overlay

    def render_picture(self, region: QRectF) -> QPicture:
        """Snapshot drawing in *region*, recorded as vectors where possible.

        The paper/background is deliberately absent. Imported PDF linework and
        ordinary markups are copied, while typed content is included only when
        that item was explicitly selected before taking the snapshot. This
        keeps a drawing-detail snapshot from silently carrying somebody's notes
        across with it.

        The recording is in the region's own coordinates, so its top-left
        corner is the origin and its size is the size of the snapshot.
        """
        box = QRectF(region).normalized()
        return self.render_items_picture(self.picture_items(box), box)

    def picture_items(self, region: QRectF) -> list:
        """Which markups a snapshot of *region* takes with it.

        Kept separate from the recording because a snapshot keeps them as well
        as the recording: a list of drawing commands can be replayed but not
        asked anything, so changing a snapshot's colours later means having
        what it was taken of.
        """
        from ..items.text import _TextBase

        return [item for item in self.markups()
                if item.isVisible()
                and (not isinstance(item, _TextBase) or item.isSelected())]

    def sheet_region(self, region: QRectF, scale: float = 4.0):
        """The sheet itself under *region*, as pixels, or None if there is none.

        A page that came in from a PDF is not made of markups — it is the
        PDF's own page, drawn from the file. So anything that wants a copy of
        what is on the page, rather than a copy of what has been added to it,
        has to ask the file. A snapshot of a detail is the obvious one: what
        is under the marquee is mostly the drawing.
        """
        page = self.page
        box = QRectF(region).normalized().intersected(self.page_rect())
        if box.isEmpty():
            return None
        if page.pdf_key is not None and page.pdf_page_index is not None:
            data = self.document.asset(page.pdf_key)
            if data:
                from ..io import pdfio

                room = pdfio.MOST_LIVE_PIXELS
                want = float(scale)
                while want > 0.5 and box.width() * want * box.height() * want > room:
                    want /= 2.0
                drawn = pdfio.LIVE.draw_region(
                    page.pdf_key, data, int(page.pdf_page_index),
                    self.page_rect(), box, want,
                    getattr(page, "pdf_annotations", True))
                if drawn is not None and not drawn.isNull():
                    return box, drawn
        if self._background is None and page.background_key:
            self.load_background()
        if self._background is not None and not self._background.isNull():
            whole = self.page_rect()
            across = self._background.width() / max(whole.width(), 1.0)
            down = self._background.height() / max(whole.height(), 1.0)
            piece = self._background.copy(
                int(box.left() * across), int(box.top() * down),
                max(int(box.width() * across), 1), max(int(box.height() * down), 1))
            if not piece.isNull():
                return box, piece.toImage()
        return None

    def render_items_picture(self, items, region: QRectF,
                             sheet: bool = True) -> QPicture:
        """Record *items* in page coordinates inside *region*, over the sheet."""
        box = QRectF(region).normalized()
        picture = QPicture()
        if box.width() <= 0 or box.height() <= 0:
            return picture
        under = self.sheet_region(box) if sheet else None
        if not items and under is None:
            return picture
        painter = QPainter()
        painter.begin(picture)
        if under is not None:
            where, image = under
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawImage(
                QRectF(where.left() - box.left(), where.top() - box.top(),
                       where.width(), where.height()),
                image, QRectF(image.rect()))
        self.paint_items(painter, items, box)
        painter.end()
        return picture

    def paint_items(self, painter: QPainter, items, region: QRectF) -> None:
        """Draw exactly *items* onto *painter*, with *region* as the origin.

        Separate from the recording above because a recording is not always
        what is wanted: exporting a markup as its own annotation draws it
        straight onto the page being written, and going through a QPicture on
        the way would quietly rescale it — a recording carries the resolution
        it was made at, and is stretched by the ratio to whatever plays it.
        """
        box = QRectF(region).normalized()
        if box.width() <= 0 or box.height() <= 0 or not items:
            return
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setClipRect(QRectF(0, 0, box.width(), box.height()))
        painter.translate(-box.left(), -box.top())
        for item in sorted(items, key=lambda markup: markup.zValue()):
            transform, ok = item.itemTransform(self)
            if not ok:
                continue
            painter.save()
            painter.setWorldTransform(transform, True)
            item.paint_content(painter)
            painter.restore()

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
        # How far the pages are turned for reading, in degrees. A way of
        # looking at the document; nothing about the document itself.
        self.reading_turn = 0
        self.frames: list[PageFrame] = []
        self.print_mode = False
        self._pages_rect = QRectF()
        self._desk_margin = QPointF(PAGE_GAP, PAGE_GAP)
        # Markups are dragged, resized and re-laid-out constantly, and a text
        # markup changes shape every time a character is typed into it. Qt's
        # spatial index assumes the opposite, and any bounding rectangle that
        # changes without it being told leaves it dereferencing stale geometry
        # — a crash, not a glitch. A marked-up drawing holds hundreds of items,
        # not hundreds of thousands, so a linear scan is cheaper than the index
        # would have been anyway.
        self.setItemIndexMethod(QGraphicsScene.NoIndex)
        self.set_canvas_colour(CANVAS[LIGHT])
        self.selectionChanged.connect(self.selectionInfoChanged.emit)
        # A square of a page finished drawing in the background: repaint just
        # where it belongs. The scene listens rather than each page, because a
        # page frame is thrown away and rebuilt constantly and a signal still
        # pointing at a deleted one is a crash rather than a glitch.
        from ..io import pdftiles

        pdftiles.TILES.tileReady.connect(self._part_of_a_page_arrived)
        pdftiles.TILES.sheetReady.connect(self._a_page_arrived)
        # Tiles come back in bursts — a screenful is dozens of them — and
        # repainting once per tile is dozens of repaints of nearly the same
        # thing. They are gathered up and drawn together on the next turn of
        # the event loop instead.
        self._arrived: list = []
        self._settling = QTimer(self)
        self._settling.setSingleShot(True)
        self._settling.setInterval(0)
        self._settling.timeout.connect(self._draw_what_arrived)

    def _part_of_a_page_arrived(self, key) -> None:
        self._arrived.append(key)
        if not self._settling.isActive():
            self._settling.start()

    def _draw_what_arrived(self) -> None:
        keys, self._arrived = self._arrived, []
        for frame in self.frames:
            box = QRectF()
            for key in keys:
                if frame.shows(key):
                    box = box.united(key.page_rect()) if not box.isEmpty() \
                        else key.page_rect()
            if not box.isEmpty():
                frame.update(box)

    def _a_page_arrived(self, key) -> None:
        for frame in self.frames:
            if frame.shows(key):
                frame.update()

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
        """Stack the pages down the canvas, centred on the widest one.

        A page turned for reading is turned *here*, as the page's own
        rotation on the canvas, rather than by turning the whole view. Turning
        the view turns its scrollbars with it — the vertical bar starts moving
        the page sideways — and a scrollbar that does not scroll the way it
        points is worse than no rotation at all. Done this way the canvas
        stays the shape it always was and the pages simply lie on their side.
        """
        turned = self.reading_turn % 360 in (90, 270)
        def across(frame):
            return frame.page.height_pt if turned else frame.page.width_pt

        def down(frame):
            return frame.page.width_pt if turned else frame.page.height_pt

        widest = max((across(frame) for frame in self.frames), default=0.0)
        y = 0.0
        for frame in self.frames:
            frame.setTransformOriginPoint(0, 0)
            frame.setRotation(self.reading_turn)
            # A rotated item hangs off its own corner, so it is pushed back
            # by however far the turn took it.
            left = (widest - across(frame)) / 2.0
            offset = {
                0: QPointF(0, 0),
                90: QPointF(across(frame), 0),
                180: QPointF(across(frame), down(frame)),
                270: QPointF(0, down(frame)),
            }.get(self.reading_turn % 360, QPointF(0, 0))
            frame.setPos(left + offset.x(), y + offset.y())
            y += down(frame) + PAGE_GAP
        height = max(y - PAGE_GAP, 0.0)
        self._pages_rect = QRectF(0, 0, widest, height)
        self._apply_desk_margin()

    def set_desk_margin(self, across: float, down: float) -> None:
        """Leave enough canvas around the pages to centre any page edge."""
        self._desk_margin = QPointF(max(float(across), PAGE_GAP),
                                    max(float(down), PAGE_GAP))
        self._apply_desk_margin()

    def _apply_desk_margin(self) -> None:
        x = self._desk_margin.x()
        y = self._desk_margin.y()
        self.setSceneRect(self._pages_rect.adjusted(-x, -y, x, y))

    def set_reading_turn(self, degrees: int) -> None:
        """Turn every page on the canvas for reading. Changes no document."""
        self.reading_turn = int(degrees) % 360
        self.layout_pages()

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

    def refresh_items(self) -> None:
        for frame in self.frames:
            frame.refresh_items()

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        # Qt's own drawBackground would paint the brush; this one replaces it,
        # so the desk the sheets lie on has to be painted here.
        painter.fillRect(rect, self.backgroundBrush())
