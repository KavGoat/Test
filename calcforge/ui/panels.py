"""Dock panels: pages, the markups list, bookmarks, tool sets and properties."""
from __future__ import annotations

import csv
import functools
import shiboken6

from PySide6.QtCore import (QByteArray, QEvent, QMimeData, QPoint, QPointF, QRect, QRectF, QSize,
                            QTimer, Qt, Signal)
from PySide6.QtGui import (QColor, QDrag, QFont, QFontInfo, QFontMetrics, QIcon, QKeySequence,
                           QPainter, QPainterPath, QPen, QPixmap, QPolygonF)
from PySide6.QtWidgets import (QAbstractItemView, QAbstractSpinBox, QApplication,
                               QCheckBox, QComboBox, QDoubleSpinBox, QInputDialog, QMessageBox,
                               QFontComboBox, QFormLayout, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QListView, QListWidget,
                               QListWidgetItem, QMenu, QPlainTextEdit, QPushButton, QSizePolicy,
                               QScrollArea, QSpinBox, QLayout, QStyledItemDelegate,
                               QToolButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from ..core.units import format_quantity
from ..items.base import (DASH_ARRAYS, HATCH_PATTERNS,
                          MarkupItem)
from ..items.contents import ContentsItem
from ..items.media import ImageItem
from ..items.snapshot import SnapshotItem
from ..items.measure import CountItem, MeasureItem
from ..items.shapes import PolyItem, RectItem
from ..items.text import (STAMP_PRESETS, CalloutItem, NoteItem, StampItem, TextItem,
                          TypewriterItem, _TextBase)
from ..settings import app_settings
from .icons import drawn_icon, icon, visible_ink
from .stylecaps import CLOUD, CORNER
from .stylecaps import (ARROW_SIZE, DASH, FILL, FILL_OPACITY, HATCH, OPACITY, STROKE,
                        WIDTH, common_capabilities, takes_end_fill)
from .widgets import (ColorButton, KeptPlace, PatternCombo, UnitCombo, arrow_combo,
                      big_pattern_dropdown, fit_pattern_list, set_arrow)


#: Each line style's sample, drawn once for its ink, weight and dashes. The
#: Properties panel fills its line-style list again whenever the selection
#: changes, and drawing every style for it was a quarter of the time of
#: placing a call-out or a text box (the user, 2026-10-19: "placing a callout
#: is laggy"). Kept with the dashes it was drawn from, so one of one's own
#: changed is drawn again.
_LINE_STYLE_ICONS: dict = {}


def _line_style_icon(name: str, colour: str, width: float, cloud: bool = False) -> QIcon:
    """A line style's sample across the box — for a cloud, its scallops
    drawn in that style, as Revu's list shows a cloud's."""
    from ..items import complexlines
    from .icons import _scales
    colour = visible_ink(colour)
    complex_line = complexlines.is_complex(name)
    # a complex line (Double, Gas…) at one size, as Revu's samples are,
    # so a heavy line's still fits the row
    weight = 1.5 if complex_line else max(2.0, min(float(width) * 1.5, 6.0))
    dashes = list(DASH_ARRAYS.get(name, []))
    key = (name, colour, weight, bool(cloud), tuple(dashes), tuple(_scales()))
    kept = _LINE_STYLE_ICONS.get(key)
    if kept is not None:
        return kept
    if len(_LINE_STYLE_ICONS) > 512:
        _LINE_STYLE_ICONS.clear()

    def draw(painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(QColor(colour or "#111318"))
        pen.setWidthF(weight)
        if dashes:
            pen.setStyle(Qt.CustomDashLine)
            pen.setDashPattern(dashes)
            pen.setCapStyle(Qt.FlatCap)
        painter.setPen(pen)
        if cloud:
            from .propbar import _scallop_path
            path = _scallop_path(3.0, 147.0, 27.0, 12.0)
        else:
            path = QPainterPath(QPointF(4, 17))
            path.lineTo(146, 17)
        if complex_line:
            complexlines.draw(painter, path, _Sample(name, pen.widthF()))
        elif cloud:
            painter.drawPath(path)
        else:
            painter.drawLine(4, 17, 146, 17)
    made = drawn_icon(draw, 150, 34)
    _LINE_STYLE_ICONS[key] = made
    return made


class _Sample:
    """What a complex line's sample is drawn from: its name and width."""

    def __init__(self, name: str, width: float):
        self.line_style = name
        self.width = width
        self.dash_scale = 1.0


def line_style_name(name: str) -> str:
    """What a line style is called in the lists: one's own as it was named."""
    from ..items import linestyles
    return name if name in linestyles.CUSTOM else name.title()


def fill_line_style_combo(combo, colour: str, width: float, current: str = "",
                          cloud: bool = False) -> None:
    """A line-style list as Revu's: Manage… at the top, then every style
    drawn (one's own among them) — for a cloud, drawn as its scallops."""
    from ..items.linestyles import MANAGE
    combo.blockSignals(True)
    combo.clear()
    combo.addItem("Manage…", MANAGE)
    combo.insertSeparator(combo.count())
    for name in DASH_ARRAYS:
        combo.addItem(_line_style_icon(name, colour, width, cloud), line_style_name(name), name)
    combo.setProperty("cloudStyles", bool(cloud))
    combo.setCurrentIndex(line_style_index(combo, current))
    combo.setToolTip(combo.currentText())
    fit_pattern_list(combo)
    combo.blockSignals(False)


def line_style_index(combo, name: str) -> int:
    """Where *name* is in a line-style list — Solid when it is not there (a
    style of somebody else's, drawn from the dashes the markup carries)."""
    found = combo.findData(name or "solid")
    return found if found >= 0 else max(combo.findData("solid"), 0)


#: Each pattern's swatch, drawn once for its ink. The Properties panel fills
#: its pattern list again whenever the selection changes, and drawing every
#: pattern for it was a twelfth of a second of each Ctrl+A and each click on
#: a markup (QA, 2026-10-15). Kept with the pattern it was drawn from, so one
#: of one's own changed is drawn again.
_HATCH_ICONS: dict = {}


def _hatch_icon(name: str, colour: str) -> QIcon:
    from ..items.hatches import LIBRARY, key_for, sample_icon
    from .icons import _scales
    ink = visible_ink(colour)
    pattern = LIBRARY.get(key_for(name))
    key = (name, ink, tuple(_scales()))
    kept = _HATCH_ICONS.get(key)
    if kept is not None and kept[0] is pattern:
        return kept[1]
    if len(_HATCH_ICONS) > 512:
        _HATCH_ICONS.clear()
    made = sample_icon(name, ink, 150, 34)
    _HATCH_ICONS[key] = (pattern, made)
    return made


def fill_hatch_combo(combo, colour: str, current: str = "") -> None:
    """A hatch list as Revu's (the user's Revu, 2026-10-15): Manage… at the
    top, then (None) and every pattern drawn."""
    from ..items import hatches
    from .hatchpatterns import MANAGE
    combo.blockSignals(True)
    combo.clear()
    combo.addItem("Manage…", MANAGE)
    combo.insertSeparator(combo.count())
    for name in HATCH_PATTERNS:
        label = hatches.display_name(name) if name else "(None)"
        combo.addItem(_hatch_icon(name, colour), label, name)
    combo.setCurrentIndex(hatch_index(combo, current))
    fit_pattern_list(combo)
    combo.blockSignals(False)


def hatch_index(combo, key: str) -> int:
    """Where *key* is in a hatch list — found by Revu's name for it too
    ("Diagonal Up" is "up"); (None) when it is not there."""
    found = combo.findData(key or "")
    if found < 0 and key:
        from ..items.hatches import named_key
        found = combo.findData(named_key(key)) if named_key(key) else -1
    return found if found >= 0 else max(combo.findData(""), 0)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

#: How long after the Markups List changes the page's dimming follows it.
DIM_AFTER_MS = 90
#: How long after the last key in its search box the Markups List follows.
LIST_AFTER_MS = 120
#: Whether the Markups List's Filter List was last on (as Revu remembers it).
FILTER_LIST_KEY = "markups_list/filter_list"


def _remembered_filter_list() -> bool:
    """On unless it was turned off: CalcForge's headings have always had
    their filters showing."""
    value = app_settings().value(FILTER_LIST_KEY, True)
    return value if isinstance(value, bool) else str(value).lower() in ("true", "1")


#: A thumbnail's part in a workbook shown in Thumbnails (PagesPanel._sections_in):
#: {"head": its first page, "collapsed": shown as one entry, "member": shown
#: page by page, "key": the workbook's key}.
SECTION_ROLE = Qt.UserRole + 1
#: Whether a thumbnail prints: 0 it does, 1 some of the workbook doesn't,
#: 2 none of it does.
NO_PRINT_ROLE = Qt.UserRole + 2
#: the calc section a page starts (its label), drawn as the break's band over
#: its thumbnail (the user, 2026-10-29: "show the purple line on the thumbnail too")
BREAK_ROLE = Qt.UserRole + 4


class _ThumbnailDelegate(QStyledItemDelegate):
    """A thumbnail as Revu draws one: the page with a thin neutral edge,
    framed in Revu's blue when it is picked out (a softer frame under the
    pointer), and its number and label centred under it, the scale on a
    line of its own (the user, 2026-10-19)."""

    #: The frame round a picked page, and the gap and outline beyond it
    #: that mark the page in view (PageListWidget.in_view_frame).
    FRAME = 4
    GAP = 1
    OUTLINE = 2
    #: How far up and right each sheet behind a workbook's entry sits.
    STACK = 4
    #: From the top of the cell to the top of the picture's room.
    TOP = 8
    #: Between the picture's room and its first line of words.
    UNDER = 7

    def __init__(self, strip: "PageListWidget"):
        super().__init__(strip)
        self.strip = strip

    # -- where things go -----------------------------------------------------
    def _paint_break(self, painter: QPainter, cell: QRect, label: str) -> None:
        """A calc section break above the page: the band the canvas draws in
        the gap before the page (calcsections.paint_bands), here along the
        top of the thumbnail's cell, its name in the tag."""
        from .calcsections import BAND
        from PySide6.QtGui import QFont
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        middle = cell.top() + self.TOP // 2
        pen = QPen(BAND, 1.4, Qt.DashLine)
        painter.setPen(pen)
        painter.drawLine(cell.left() + 2, middle, cell.right() - 2, middle)
        font = QFont(painter.font())
        font.setPointSizeF(max(6.0, font.pointSizeF() * 0.8))
        font.setBold(True)
        painter.setFont(font)
        text = f" § {label} "
        width = min(painter.fontMetrics().horizontalAdvance(text), cell.width() - 8)
        tag = QRect(cell.left() + 4, middle - 6, width, 12)
        painter.setPen(Qt.NoPen)
        painter.setBrush(BAND)
        painter.drawRoundedRect(tag, 6, 6)
        painter.setPen(QColor("white"))
        painter.drawText(tag, Qt.AlignCenter,
                         painter.fontMetrics().elidedText(text, Qt.ElideRight, width))
        painter.restore()

    def picture_room(self, cell: QRect) -> QRect:
        """The box a page's picture is fitted into, centred across the cell."""
        size = self.strip.iconSize()
        left = cell.left() + (cell.width() - size.width()) // 2
        return QRect(left, cell.top() + self.TOP, size.width(), size.height())

    def picture_rect(self, cell: QRect, picture, collapsed: bool = False) -> QRect:
        """The page itself: its own shape fitted into the room and centred
        in it, so a row of portrait and landscape sheets keeps its words on
        one line. A workbook's entry (*collapsed*) leaves room in it for the
        sheets stacked behind its page: they stood out of the cell's top, and
        the blue frame round them was cut off there (the user, 2026-10-24)."""
        room = self.picture_room(cell)
        if collapsed:
            room = room.adjusted(0, 2 * self.STACK, -2 * self.STACK, 0)
        sizes = picture.availableSizes() if isinstance(picture, QIcon) else []
        if not sizes or sizes[-1].width() <= 0 or sizes[-1].height() <= 0:
            return room
        fitted = sizes[-1].scaled(room.size(), Qt.KeepAspectRatio)
        return QRect(room.left() + (room.width() - fitted.width()) // 2,
                     room.top() + (room.height() - fitted.height()) // 2,
                     fitted.width(), fitted.height())

    def stack_rect(self, page: QRect, collapsed: bool) -> QRect:
        """What a picked frame goes round: the page, and a workbook's entry
        with the sheets stacked behind it (framing the front page alone left
        the frame showing only down its left and along its bottom, an L)."""
        return page.united(page.translated(2 * self.STACK, -2 * self.STACK)) if collapsed else page

    def lines_rect(self, cell: QRect) -> QRect:
        """Where the words go: under the picture's room, across the cell."""
        room = self.picture_room(cell)
        top = room.bottom() + 1 + self.UNDER
        return QRect(cell.left() + 2, top, cell.width() - 4, max(cell.bottom() - top + 1, 1))

    def toggle_rect(self, cell: QRect) -> QRect:
        """A workbook entry's first line of words (its ▸ and name): a click
        there shows or hides its pages."""
        words = self.lines_rect(cell)
        return QRect(words.left(), words.top() - 2, words.width(),
                     QFontMetrics(self.strip.font()).height() + 4)

    # -- Qt's side -------------------------------------------------------------
    def sizeHint(self, option, index) -> QSize:
        return self.strip.cell_size()

    def paint(self, painter: QPainter, option, index) -> None:
        from PySide6.QtWidgets import QStyle
        from ..app import current_theme
        from ..theme import tokens
        colours = tokens(current_theme())
        cell = option.rect
        if cell.width() <= 0 or cell.height() <= 0:
            return       # a page hidden behind its workbook's entry: Qt still asks
        picture = index.data(Qt.DecorationRole)
        picture = picture if isinstance(picture, QIcon) else None
        section = index.data(SECTION_ROLE) or {}
        collapsed = bool(section.get("collapsed"))
        page = self.picture_rect(cell, picture, collapsed)
        painter.save()
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        picked = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)
        if section.get("member"):
            # a workbook's pages, shown: a band behind them says which they are
            band = QColor(colours["accent_soft"])
            band.setAlpha(150)
            painter.fillRect(cell.adjusted(0, 2, 0, -2), band)
        if picked or hovered:
            frame = self.stack_rect(page, collapsed).adjusted(-self.FRAME, -self.FRAME,
                                                               self.FRAME, self.FRAME)
            painter.fillRect(frame, QColor(colours["thumb_picked" if picked
                                                  else "thumb_hover"]))
        label = index.data(BREAK_ROLE)
        if label:
            self._paint_break(painter, cell, str(label))
        if collapsed:
            # a workbook as one entry: its first page on a stack of sheets
            painter.setPen(QPen(QColor(colours["thumb_edge"]), 1))
            for step in (2 * self.STACK, self.STACK):
                behind = page.translated(step, -step)
                painter.fillRect(behind, Qt.white)
                painter.drawRect(behind.adjusted(0, 0, -1, -1))
        silent = index.data(NO_PRINT_ROLE) or 0
        if silent == 2:
            painter.setOpacity(0.45)       # nothing of it prints: greyed
        if picture is not None:
            picture.paint(painter, page)
        else:
            painter.fillRect(page, Qt.white)
        painter.setOpacity(1.0)
        # the thin neutral edge: a white page on a pale panel keeps its shape
        painter.setPen(QPen(QColor(colours["thumb_edge"]), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(page.adjusted(0, 0, -1, -1))
        if silent:
            # a crossed-out printer in the corner: it doesn't print (or some of it)
            from .sheettabs import no_print_pixmap
            mark = no_print_pixmap(14, painter.device().devicePixelRatioF()
                                   if painter.device() is not None else 1.0, "#404854")
            spot = QRect(page.right() - 17, page.top() + 3, 14, 14)
            painter.fillRect(spot.adjusted(-1, -1, 1, 1), QColor(255, 255, 255, 220))
            painter.drawPixmap(spot, mark)
        # the number (and the label), and under it the scale: centred
        ink = index.data(Qt.ForegroundRole)
        painter.setPen(ink.color() if hasattr(ink, "color") else QColor(colours["ink"]))
        painter.setFont(option.font)
        metrics = QFontMetrics(option.font)
        words = self.lines_rect(cell)
        for number, line in enumerate((index.data(Qt.DisplayRole) or "").split("\n")):
            row = QRect(words.left(), words.top() + number * metrics.height(),
                        words.width(), metrics.height())
            painter.drawText(row, Qt.AlignHCenter | Qt.AlignTop,
                             metrics.elidedText(line, Qt.ElideRight, row.width()))
        painter.restore()


class PageListWidget(QListWidget):
    """A wrapping thumbnail grid: as many pages to a row as the strip has
    room for, each in an equal share of the row."""

    CELL_WIDTH = 116
    CELL_HEIGHT = 174

    #: How small and how large the pictures of the pages may be made.
    SMALLEST = 0.5
    LARGEST = 3.0

    #: A wheel notch's worth of zoom.
    STEP = 1.15

    zoomed = Signal(float)
    #: Delete pressed over the strip: the pages picked out are to go
    delete_pressed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("pageList")
        self.external_drop_row: int | None = None
        self.scale = 1.0
        #: How many lines of words go under each page: its number (and
        #: label), and its scale when a page has one (PagesPanel.rebuild).
        self.caption_lines = 1
        self._laying_out = False
        # The page in view, outlined in the accent: a run picked out stays
        # picked while the reader scrolls on, so the strip needs a marker of
        # its own for where they are (the user, 2026-10-17).
        self.in_view_row = -1
        self.itemSelectionChanged.connect(lambda: self.viewport().update())
        self.delegate = _ThumbnailDelegate(self)
        self.setItemDelegate(self.delegate)
        self.setUniformItemSizes(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # A page put in or taken out changes how many rows there are, and so
        # whether the scroll bar is wanted.
        self._relayout_timer = QTimer(self)
        self._relayout_timer.setSingleShot(True)
        self._relayout_timer.timeout.connect(self.relayout)
        self.model().rowsInserted.connect(lambda *_: self._relayout_timer.start(0))
        self.model().rowsRemoved.connect(lambda *_: self._relayout_timer.start(0))

    # -- the page in view -----------------------------------------------------
    def set_in_view(self, row: int) -> None:
        if row != self.in_view_row:
            self.in_view_row = row
            self.viewport().update()

    def in_view_outlined(self) -> bool:
        """Whether the page in view is drawn outlined: not when it is the one
        page picked out, whose highlight already says where the reader is."""
        entry = self.item(self.in_view_row) if self.in_view_row >= 0 else None
        if entry is None:
            return False
        picked = self.selectedItems()
        return not (len(picked) == 1 and picked[0] is entry)

    def picture_rect(self, row: int) -> QRect:
        """Where page *row*'s picture is drawn, in viewport pixels."""
        entry = self.item(row)
        if entry is None:
            return QRect()
        section = entry.data(SECTION_ROLE) or {}
        return self.delegate.picture_rect(self.visualItemRect(entry), entry.icon(),
                                          bool(section.get("collapsed")))

    def in_view_frame(self) -> QRect:
        """Where the outline goes: round the page's picture, just outside
        the frame a picked page has, so the two are told apart."""
        if self.in_view_row < 0 or self.item(self.in_view_row) is None:
            return QRect()
        out = self.delegate.FRAME + self.delegate.GAP + self.delegate.OUTLINE
        section = self.item(self.in_view_row).data(SECTION_ROLE) or {}
        page = self.delegate.stack_rect(self.picture_rect(self.in_view_row),
                                        bool(section.get("collapsed")))
        return page.adjusted(-out, -out, out, out)

    def cell_size(self) -> QSize:
        """A page's cell: room for its picture, the words under it, and the
        space round both."""
        words = QFontMetrics(self.font()).height() * max(self.caption_lines, 1)
        tall = (_ThumbnailDelegate.TOP + self.iconSize().height()
                + _ThumbnailDelegate.UNDER + words + 6)
        return QSize(max(int(self.CELL_WIDTH * self.scale), 24), max(tall, 32))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.relayout()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.relayout()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in (QEvent.FontChange, QEvent.StyleChange):
            self.relayout()

    def indexAt(self, point):
        """The thumbnail under *point*. With a workbook's pages hidden behind
        its entry, Qt's own answer counted the hidden rows once their
        pictures came in, and a click on the first page found nothing —
        the reader was stuck in the workbook (the user, 2026-10-22); then
        the thumbnails showing are asked where they are."""
        if self.shown_count() == self.count():
            return super().indexAt(point)
        from PySide6.QtCore import QModelIndex
        for row in self.shown_rows():
            index = self.model().index(row, 0)
            if self.visualRect(index).contains(point):
                return index
        return QModelIndex()

    def shown_count(self) -> int:
        """How many thumbnails are showing: a workbook shown as one entry
        hides the rest of its pages."""
        return sum(1 for row in range(self.count()) if not self.isRowHidden(row))

    def shown_rows(self) -> list:
        return [row for row in range(self.count()) if not self.isRowHidden(row)]

    def scroll_bar_width(self) -> int:
        return max(self.verticalScrollBar().sizeHint().width(), 1)

    @staticmethod
    def columns_for(width: int, cell: int, count: int = 0) -> tuple:
        """How many cells *cell* wide go across *width* pixels, and how wide
        each one's share of the row is. Fewer pages than there is room for
        share the whole row, so they sit centred in it, as Revu's do.

        Qt starts a new row as soon as the next cell would reach the right
        edge, so the shares must come to less than the whole width: shares
        of width / columns put the last page of every row on the next one
        (the user, 2026-10-19: page 3 under page 1 with room for it)."""
        room = max(width - 1, 1)
        columns = max(room // max(cell, 1), 1)
        if count > 0:
            columns = min(columns, count)
        return columns, max(room // columns, 1)

    def relayout(self) -> None:
        """Lay the pages out in as many columns as fit across the strip.

        The scroll bar is shown only when the rows are taller than the
        strip, and its width is kept out of the rows only then: left to
        Qt, a strip that might scroll keeps a scroll bar's width spare even
        while it shows none."""
        if self._laying_out:
            return
        self._laying_out = True
        try:
            cell = self.cell_size()
            # the width with no scroll bar, whether or not one is showing: the
            # viewport itself catches up with a change of policy later
            margins = self.viewportMargins()
            across = self.contentsRect().width() - margins.left() - margins.right()
            shown = self.shown_count()
            columns, share = self.columns_for(across, cell.width(), shown)
            rows = -(-shown // columns)
            tall = self.contentsRect().height() - margins.top() - margins.bottom()
            scrolls = shown > 0 and rows * cell.height() > tall
            if scrolls:
                columns, share = self.columns_for(across - self.scroll_bar_width(),
                                                  cell.width(), shown)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn if scrolls
                                            else Qt.ScrollBarAlwaysOff)
            self._fit_icon(share)
            grid = QSize(share, self.cell_size().height())
            if grid != self.gridSize():
                self.setGridSize(grid)
        finally:
            self._laying_out = False

    #: The pictures' size as zoomed (Ctrl+wheel); drawn smaller only while
    #: the strip is too narrow for them.
    _wanted_icon = None

    def setIconSize(self, size: QSize) -> None:
        self._wanted_icon = QSize(size)
        super().setIconSize(size)
        self.relayout()

    def _fit_icon(self, share: int) -> None:
        """Zoomed in past the strip's width, the pages are made to fit it, as
        Revu's are, rather than being cut off at its edge (the user,
        2026-10-23: "zooming in and out in the page panel should resize the
        grid"); wider again, they are as big as they were zoomed."""
        wanted = self._wanted_icon or self.iconSize()
        d = self.delegate
        room = share - 2 * (d.FRAME + d.GAP + d.OUTLINE + 2 * d.STACK) - 2
        size = QSize(wanted)
        if 16 <= room < wanted.width():
            size = QSize(room, max(int(wanted.height() * room / wanted.width()), 20))
        if size != self.iconSize():
            QListWidget.setIconSize(self, size)

    def keyPressEvent(self, event) -> None:
        """Delete (or Backspace) deletes the pages picked out, as in Revu's
        Thumbnails (the user, 2026-10-23: "can't press delete to delete
        pages")."""
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace) and \
                not (event.modifiers() & (Qt.ControlModifier | Qt.AltModifier | Qt.ShiftModifier)):
            if self.selectedItems():
                self.delete_pressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:
        """Ctrl and the wheel makes the pages bigger and smaller.

        A drawing set is read by its sheets, and at the size they come out of
        the box a title block is a grey smudge. Plain scrolling is left alone:
        the wheel over a list scrolls it, and taking that away to zoom instead
        would be surprising in the one place the wheel already has a job.
        """
        if not (event.modifiers() & Qt.ControlModifier):
            super().wheelEvent(event)
            return
        notches = event.angleDelta().y()
        if not notches:
            event.accept()
            return
        # By how far the wheel turned, not by whether it turned: a trackpad
        # sends a stream of small amounts and a mouse sends whole notches, and
        # one step for either makes the trackpad crawl and the mouse coarse.
        step = self.STEP ** (notches / 120.0)
        wanted = max(self.SMALLEST, min(self.scale * step, self.LARGEST))
        if abs(wanted - self.scale) > 1e-6:
            self.zoomed.emit(wanted)
        event.accept()

    #: What a drag of pages within the strip carries.
    PAGES_MIME = "application/x-calcforge-pages"

    def startDrag(self, actions) -> None:
        """Pages dragged to a new place: a small white sheet by the pointer,
        with how many when there are several — not a picture of the whole
        page covering where it is going, and not Qt's no-entry cross over the
        strip it is being dragged along (the user, 2026-10-05)."""
        rows = sorted(self.row(entry) for entry in self.selectedItems())
        if self.picked is not None:
            rows = self.picked()          # a workbook's entry: all its pages
        if not rows and self.currentRow() >= 0:
            rows = [self.currentRow()]
        if not rows:
            return
        self.dragging_rows = rows
        data = QMimeData()
        data.setData(self.PAGES_MIME, QByteArray(",".join(map(str, rows)).encode()))
        drag = QDrag(self)
        drag.setMimeData(data)
        ratio = self.devicePixelRatioF()
        picture = self._drag_picture(len(rows), ratio)
        drag.setPixmap(picture)
        drag.setHotSpot(QPoint(-10, -8))          # beside the pointer, not under it
        try:
            drag.exec(Qt.MoveAction, Qt.MoveAction)
        finally:
            self.dragging_rows = None
            self.set_external_drop_row(None)

    dragging_rows = None
    #: The pages picked out, a workbook's entry standing for all its pages
    #: (PagesPanel.picked_rows).
    picked = None

    @staticmethod
    def _drag_picture(count: int, ratio: float = 1.0) -> QPixmap:
        width, height = 30, 38
        stacked = 4 if count > 1 else 0
        pixmap = QPixmap(int((width + stacked + 4) * ratio), int((height + stacked + 4) * ratio))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        border = QPen(QColor(120, 128, 140, 200), 1.0)
        if stacked:
            painter.setPen(border)
            painter.setBrush(QColor(255, 255, 255, 170))
            painter.drawRoundedRect(QRectF(stacked + 1.5, 1.5, width, height), 2, 2)
        painter.setPen(border)
        painter.setBrush(QColor(255, 255, 255, 215))
        painter.drawRoundedRect(QRectF(1.5, stacked + 1.5, width, height), 2, 2)
        # a few grey lines: it reads as a sheet
        painter.setPen(QPen(QColor(170, 176, 186, 200), 1.0))
        for line in range(3):
            y = stacked + 9.5 + line * 6
            painter.drawLine(QPointF(7, y), QPointF(width - 5, y))
        if count > 1:
            font = painter.font()
            font.setPixelSize(11)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(40, 48, 60))
            painter.drawText(QRectF(1.5, stacked + height - 15, width, 14),
                             Qt.AlignCenter, str(count))
        painter.end()
        return pixmap

    def set_external_drop_row(self, row: int | None) -> None:
        row = None if row is None else max(0, min(int(row), self.count()))
        if row != self.external_drop_row:
            self.external_drop_row = row
            self.viewport().update()

    def uses_horizontal_slots(self) -> bool:
        """Whether successive thumbnails currently share a visual row."""
        shown = self.shown_rows()
        if len(shown) > 1:
            first = self.visualItemRect(self.item(shown[0]))
            second = self.visualItemRect(self.item(shown[1]))
            return abs(first.center().y() - second.center().y()) < \
                max(first.height(), second.height()) / 2
        return self.viewport().width() >= self.CELL_WIDTH * 2

    def drop_indicator_line(self, row: int):
        """Where pages dropped at *row* go, in viewport pixels: Revu's short
        line in the gap beside the page they go in front of (after the last,
        beside it), as long as the page and no longer — not the whole cell,
        words and all (the user, 2026-10-23: "quite long and not like
        Bluebeam")."""
        shown = self.shown_rows()
        if not shown:
            return QPointF(6, 6), QPointF(max(self.viewport().width() - 6, 6), 6)
        # the slot in front of *row*: the first thumbnail showing from there
        # (a workbook's hidden pages are behind its entry)
        ahead = next((r for r in shown if r >= row), None)
        page = self.picture_rect(ahead if ahead is not None else shown[-1])
        before = shown[shown.index(ahead) - 1] if ahead is not None and shown.index(ahead) > 0 \
            else (shown[-1] if ahead is None else None)
        reach = self.delegate.FRAME + self.delegate.GAP + self.delegate.OUTLINE + 3
        if not self.uses_horizontal_slots():
            # one page to a row: across, in the gap above it (below the last)
            if ahead is None:
                y = page.bottom() + reach + 2
            elif before is not None:
                above = self.visualItemRect(self.item(before)).bottom()
                y = (above + page.top()) // 2
            else:
                y = page.top() - reach
            return QPointF(page.left(), y), QPointF(page.right(), y)
        if ahead is None:
            x = page.right() + reach + 2
        else:
            x = page.left() - reach
            if before is not None:
                left = self.picture_rect(before)
                if abs(left.center().y() - page.center().y()) < page.height() / 2:
                    x = (left.right() + page.left()) // 2         # between the two
        return QPointF(x, page.top()), QPointF(x, page.bottom())

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.in_view_outlined():
            from ..app import current_theme
            from ..theme import tokens
            frame = self.in_view_frame()
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(QPen(QColor(tokens(current_theme())["accent"]), 2.0))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(frame).adjusted(1, 1, -1, -1), 2, 2)
            painter.end()
        if self.external_drop_row is None:
            return
        start, end = self.drop_indicator_line(self.external_drop_row)
        painter = QPainter(self.viewport())
        pen = QPen(QColor("#1971c2"), 3.0, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(start, end)
        painter.end()

class _PanelTools(QWidget):
    """A panel's row of header buttons; it redraws their pictures when the
    theme changes (DockTitleBar.refresh_icons)."""

    def __init__(self, refresh, parent=None):
        super().__init__(parent)
        self._refresh = refresh

    def refresh_icons(self) -> None:
        self._refresh()


class PagesPanel(QWidget):
    """Thumbnail strip with reordering and page commands."""

    pageSelected = Signal(int)
    # Where a run of pages was dragged to: the first of them, how many, and
    # the page number the run now starts at. A run, because a block of sheets
    # picked out together is dragged as a block.
    pagesReordered = Signal(int, int, int)

    def __init__(self, window):
        super().__init__()
        self._thumbnails: dict = {}      # id(page) -> (what it showed, icon, page)
        self.window = window
        # A page finished being drawn in the background: put it in its row.
        from ..io import pdftiles

        pdftiles.TILES.sheetReady.connect(self._page_was_drawn)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(0)

        # Revu's header (the user, 2026-10-19): the panel's name is the menu
        # of its commands, "Thumbnails ▾", and its buttons follow it, small,
        # flat and evenly spaced. Both go on the panel's title bar
        # (PanelDock.set_header, through dock_header).
        self.title_button = QToolButton()
        self.title_button.setObjectName("panelTitleMenu")
        self.title_button.setText("Thumbnails")
        self.title_button.setToolTip("Thumbnails: what can be done to the pages")
        self.title_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.title_button.setPopupMode(QToolButton.InstantPopup)
        self.title_button.setFocusPolicy(Qt.NoFocus)
        self.options_menu = QMenu(self.title_button)
        self.options_menu.setObjectName("thumbnailsMenu")
        self.options_menu.aboutToShow.connect(
            lambda: self.build_options_menu(self.options_menu))
        self.title_button.setMenu(self.options_menu)
        self.header_tools = _PanelTools(self.refresh_icons)
        self.header_tools.setObjectName("panelTools")
        buttons = QHBoxLayout(self.header_tools)
        buttons.setContentsMargins(6, 0, 0, 0)
        buttons.setSpacing(2)
        # Each button is the menus' command under the menus' name (bug hunt
        # E4); the inserts offer Before / After on their arrow, as every
        # insert does, and a click on the button itself puts it after.
        # Lambdas, not the bound methods: clicked() carries a "checked" bool
        # that would otherwise arrive as the page to act on.
        family = {entry[0]: entry for entry in self.window.insert_family()}
        self.page_buttons = {}
        self._button_icons = {}
        for key, picture, tip, slot in (
                # one click, no dialog: a blank page after this one
                ("quick_add_page", "add_page", "Add Page — a blank page after this "
                 "one (after the whole workbook on a workbook), no questions",
                 lambda: self.window.quick_add_page()),
                ("insert_pdf", "insert_pages", "Insert Pages — pages from a PDF, after "
                 "this page; the arrow offers Before or After",
                 lambda: self.window.insert_pdf()),
                ("add_page", "insert_blank_page", "Insert Blank Page — after this page; "
                 "the arrow offers Before or After", lambda: self.window.add_page()),
                ("add_sheet_page", "insert_sheet_page", "Insert Spreadsheet Page — after "
                 "this page (pages next to each other are one sheet); the arrow offers "
                 "Before or After", lambda: self.window.insert_spreadsheet()),
                ("duplicate_page", "duplicate_page", "Duplicate Page — the page, or the "
                 "pages picked out",
                 lambda: self.window.duplicate_page(
                     self.window.selected_pages()[0]
                     if self.window.selected_pages() else None)),
                ("delete_page", "delete_pages", "Delete Pages… — the page, or the pages "
                 "picked out",
                 lambda: self.window.delete_page(
                     self.window.selected_pages()[0]
                     if self.window.selected_pages() else None))):
            button = QToolButton()
            button.setObjectName(f"thumbnails_{key}")
            button.setIcon(icon(picture, self.TOOL_ICON))
            button.setIconSize(QSize(self.TOOL_ICON, self.TOOL_ICON))
            button.setAutoRaise(True)
            button.setToolTip(tip)
            button.clicked.connect(slot)
            if key in family:
                choice = QMenu(button)
                # the same Before / After as Document ▸ Insert's (bindable.py)
                choice.setProperty("cf_context", f"insert.{key}")
                self.window.fill_insert_choice(choice, family[key])
                button.setMenu(choice)
                button.setPopupMode(QToolButton.MenuButtonPopup)
            buttons.addWidget(button)
            self.page_buttons[key] = button
            self._button_icons[button] = picture

        self.list = PageListWidget()
        #: The workbooks shown page by page (by key); the rest are one entry.
        self.expanded: set = set()
        #: The workbooks whose entry the reader picked (it stands for all its pages).
        self._section_pick: set = set()
        self.list.picked = self.picked_rows
        self.list.itemSelectionChanged.connect(self._picked_in_strip)
        self.list.scale = self._remembered_scale()
        self.list.zoomed.connect(self.set_thumbnail_scale)
        self.list.delete_pressed.connect(self.delete_picked)
        # Sheets are drawn as they are scrolled to rather than all at once.
        self.list.verticalScrollBar().valueChanged.connect(
            lambda _value: self._draw_what_is_on_screen())
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setIconSize(self._icon_size())
        self.list.setFlow(QListView.LeftToRight)
        self.list.setWrapping(True)
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Static)
        # the room round each page is in its cell (PageListWidget.cell_size)
        self.list.setSpacing(0)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        # The line that says where a dragged page will land. Without it a drag
        # is a guess, and a page dropped one place out has to be dragged again.
        self.list.setDropIndicatorShown(True)
        # More than one page at a time: a header taken off a run of drawing
        # sheets, or a block of pages dragged somewhere else, is one gesture
        # rather than twenty.
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.currentRowChanged.connect(self._row_changed)
        self.list.itemClicked.connect(self._clicked)
        self.list.model().rowsMoved.connect(self._rows_moved)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)
        self.list.installEventFilter(self)
        self._hover_row = None
        self.list.setMouseTracking(True)
        self.list.viewport().setMouseTracking(True)
        self.list.viewport().installEventFilter(self)
        # A copied page arriving on the clipboard shows its bar at once, and
        # one going away takes the bar with it.
        QApplication.clipboard().dataChanged.connect(self._clipboard_changed)
        # A PDF or an image dragged onto the strip goes in where the line is.
        self.list.setAcceptDrops(True)
        self.list.viewport().setAcceptDrops(True)
        self.list.dragEnterEvent = self._drag_enter
        self.list.dragMoveEvent = self._drag_move
        self.list.dragLeaveEvent = self._drag_leave
        self.list.dropEvent = self._drop
        layout.addWidget(self.list, 1)
        self._suppress = False

    # -- the header: Revu's "Thumbnails ▾" and the buttons after it ---------
    #: How big the header's buttons' pictures are, as Revu's panel icons.
    TOOL_ICON = 18

    def dock_header(self) -> tuple:
        """The title menu and the buttons, for the panel's title bar."""
        return self.title_button, self.header_tools

    def refresh_icons(self) -> None:
        """The buttons' pictures in the theme now in use."""
        for button, picture in self._button_icons.items():
            button.setIcon(icon(picture, self.TOOL_ICON))
        self.list.viewport().update()

    def build_options_menu(self, menu: QMenu | None = None) -> QMenu:
        """What "Thumbnails ▾" offers, as Revu's panel menu does: every
        button's command and the rest of what is done to pages, then the
        thumbnails' size. Each entry is the window's own command, so its
        key is the same here as on the Document menu."""
        window = self.window
        menu = menu if menu is not None else QMenu(self)
        for old in menu.findChildren(QMenu, options=Qt.FindDirectChildrenOnly):
            old.deleteLater()               # last time's submenus
        menu.clear()
        # every insert under its full name, Before / After the page in view,
        # the same choice as Document ▸ Insert's and the buttons' arrows
        for entry in window.insert_family():
            choice = menu.addMenu(entry[1])
            choice.setProperty("cf_context", f"insert.{entry[0]}")
            window.fill_insert_choice(choice, entry)
        menu.addSeparator()
        for name in ("duplicate_page", "extract_pages", "split_pages", "delete_page",
                     "crop_page"):
            action = getattr(window, f"act_{name}", None)
            if action is not None:
                menu.addAction(action)
        turn = menu.addMenu("Rotate Pages")
        turn.addAction(window.act_rotate_pages_cw)
        turn.addAction(window.act_rotate_pages_acw)
        menu.addSeparator()
        menu.addAction(window.act_page_setup)
        menu.addAction(window.act_scale)
        menu.addSeparator()
        menu.addAction(window.act_thumbnails_larger)
        menu.addAction(window.act_thumbnails_smaller)
        window.act_thumbnails_larger.setEnabled(self.list.scale < PageListWidget.LARGEST)
        window.act_thumbnails_smaller.setEnabled(self.list.scale > PageListWidget.SMALLEST)
        return menu

    def zoom_thumbnails(self, notches: float) -> None:
        """Larger or Smaller Thumbnails: a wheel notch's worth (Ctrl+wheel)."""
        self.set_thumbnail_scale(self.list.scale * PageListWidget.STEP ** notches)

    # -- how big the pictures are ------------------------------------------
    #: The icon inside a cell, before the cell's own padding.
    ICON_WIDTH = 96
    ICON_HEIGHT = 128

    @staticmethod
    def _remembered_scale() -> float:
        from . import preferences

        wanted = float(getattr(preferences.current(), "page_thumbnails", 1.0))
        return max(PageListWidget.SMALLEST,
                   min(wanted, PageListWidget.LARGEST))

    def _icon_size(self) -> QSize:
        scale = self.list.scale
        return QSize(max(int(self.ICON_WIDTH * scale), 16),
                     max(int(self.ICON_HEIGHT * scale), 20))

    def set_thumbnail_scale(self, scale: float) -> None:
        """Draw the pages this much bigger, and remember it.

        The pictures themselves are redrawn rather than the old ones being
        stretched: a thumbnail is made from the page's own small render, which
        has resolution to spare, so making it bigger makes it sharper.
        """
        from . import preferences

        scale = max(PageListWidget.SMALLEST,
                    min(float(scale), PageListWidget.LARGEST))
        if abs(scale - self.list.scale) < 1e-6:
            return
        self.list.scale = scale
        self.list.setIconSize(self._icon_size())
        self.list.relayout()
        document = getattr(self.window, "document", None)
        for row in range(self.list.count()):
            if document is not None and row < len(document.pages):
                self.list.item(row).setIcon(
                    self._thumbnail(document.pages[row], document))
        prefs = preferences.current()
        prefs.page_thumbnails = scale
        preferences.apply(prefs)

    # -- dropping a file on the strip --------------------------------------
    WELCOME = (".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff")

    def _files_in(self, event) -> list[str]:
        """The paths being dragged that this panel can do something with."""
        data = event.mimeData()
        if not data.hasUrls():
            return []
        paths = [url.toLocalFile() for url in data.urls()]
        return [path for path in paths
                if path.lower().endswith(self.WELCOME)]

    def _ours(self, event) -> bool:
        """Pages of this strip being dragged along it."""
        return (event.source() is self.list
                and event.mimeData().hasFormat(PageListWidget.PAGES_MIME))

    def _drag_enter(self, event) -> None:
        if self._ours(event):
            self.list.set_external_drop_row(self.drop_row(event.position().toPoint()))
            event.setDropAction(Qt.MoveAction)
            event.accept()
            return
        if self._files_in(event):
            self.list.set_external_drop_row(
                self.drop_row(event.position().toPoint()))
            event.setDropAction(Qt.CopyAction)
            event.acceptProposedAction()
            return
        self.list.set_external_drop_row(None)
        QListWidget.dragEnterEvent(self.list, event)

    def _drag_move(self, event) -> None:
        if self._ours(event):
            # the blue line says where they will go; nothing else moves yet
            self.list.set_external_drop_row(self.drop_row(event.position().toPoint()))
            event.setDropAction(Qt.MoveAction)
            event.accept()
            self._scroll_near_the_edge(event.position().toPoint())
            return
        if self._files_in(event):
            self.list.set_external_drop_row(
                self.drop_row(event.position().toPoint()))
            event.setDropAction(Qt.CopyAction)
            event.acceptProposedAction()
            return
        self.list.set_external_drop_row(None)
        QListWidget.dragMoveEvent(self.list, event)

    def _drag_leave(self, event) -> None:
        self.list.set_external_drop_row(None)
        event.accept()

    def drop_row(self, position) -> int:
        """Which page a drop at *position* goes in front of."""
        entry = self.list.itemAt(position)
        if entry is not None:
            row = self.list.row(entry)
            box = self.list.visualItemRect(entry)
            # A one-column strip reads top/bottom. A wrapping thumbnail grid
            # reads left/right within each visual row.
            after = (position.x() > box.center().x()
                     if self.list.uses_horizontal_slots()
                     else position.y() > box.center().y())
            section = self._collapsed.get(row)
            if after and section is not None:
                return section.last + 1     # after a workbook shown as one: after all of it
            return row + int(after)
        # In the gaps, find the first visual centre after the pointer rather
        # than treating every empty pixel as the end of the document.
        for row in self.list.shown_rows():
            box = self.list.visualItemRect(self.list.item(row))
            if position.y() < box.top():
                return row
            if box.top() <= position.y() <= box.bottom() \
                    and position.x() < box.center().x():
                return row
        return self.list.count()

    def _scroll_near_the_edge(self, point) -> None:
        bar = self.list.verticalScrollBar()
        height = self.list.viewport().height()
        if point.y() < 24:
            bar.setValue(bar.value() - 12)
        elif point.y() > height - 24:
            bar.setValue(bar.value() + 12)

    def _drop(self, event) -> None:
        if self._ours(event):
            rows = self.list.dragging_rows or [
                int(part) for part in bytes(event.mimeData().data(
                    PageListWidget.PAGES_MIME)).decode().split(",") if part]
            slot = self.drop_row(event.position().toPoint())
            self.list.set_external_drop_row(None)
            event.setDropAction(Qt.MoveAction)
            event.accept()
            self.move_rows(rows, slot)
            return
        files = self._files_in(event)
        if not files:
            self.list.set_external_drop_row(None)
            QListWidget.dropEvent(self.list, event)
            return
        row = self.drop_row(event.position().toPoint())
        self.list.set_external_drop_row(None)
        event.setDropAction(Qt.CopyAction)
        event.accept()
        self.window.insert_files_at(files, row)

    def move_rows(self, rows: list, slot: int) -> None:
        """Pages *rows* dropped in front of *slot* (a slot in the strip as it
        is, before they leave). A run moves in one go; pages picked out here
        and there are gathered up into a run where they were dropped."""
        rows = sorted(set(rows))
        if not rows:
            return
        if rows == list(range(rows[0], rows[-1] + 1)):
            first, count = rows[0], len(rows)
            if first <= slot <= first + count:
                return                                    # dropped where it was
            target = slot - count if slot > first else slot
            self.pagesReordered.emit(first, count, max(target, 0))
            return
        # one at a time, each to the place after the one before it, keeping
        # track of where every page has got to
        order = list(range(self.list.count()))
        start = slot - sum(1 for row in rows if row < slot)
        for placed, row in enumerate(rows):
            current = order.index(row)
            target = start + placed
            if current != target:
                self.pagesReordered.emit(current, 1, target)
                order.insert(target, order.pop(current))

    def show_where_it_landed(self, row: int, count: int = 1) -> None:
        """Say where pasted pages went: the slot line, and the pages picked out.

        A drop shows the slot it is about to land in, because the pointer is
        there to show it. A paste has no pointer, so it says it afterwards
        instead — the same blue line at the slot the pages went into, and the
        pages themselves picked out, so it is never a question where they are.
        """
        self.list.set_external_drop_row(row)
        self.list.clearSelection()
        for offset in range(max(count, 1)):
            entry = self.list.item(row + offset)
            if entry is not None:
                entry.setSelected(True)
        last = self.list.item(row)
        if last is not None:
            self.list.scrollToItem(last)
        # Long enough to be seen and short enough not to be mistaken for a
        # drop about to happen. Tied to the list rather than left loose: a
        # timer with a bare lambda outlives the window that owns it and comes
        # back nine hundred milliseconds later to paint a widget C++ has
        # already deleted.
        QTimer.singleShot(900, self.list,
                          lambda: self.list.set_external_drop_row(None))

    # -- Rename Page Label, in place (Revu's Re-Label) ------------------------
    def edit_label(self, row: int):
        """Make page *row*'s label editable on its thumbnail, as Revu's
        Rename Page Label does: Enter (or clicking away) keeps it, Escape
        leaves it as it was. The editor, or None when there is no such row."""
        self.finish_label_edit(keep=False)
        entry = self.list.item(row)
        document = getattr(self.window, "document", None)
        if entry is None or document is None or not 0 <= row < len(document.pages):
            return None
        self.list.scrollToItem(entry)
        page = document.pages[row]
        editor = QLineEdit(self.list.viewport())
        editor.setObjectName("pageLabelEditor")
        editor.setText(page.label.strip() or str(row + 1))
        editor.setToolTip("The page's label: Enter keeps it, Esc leaves it as it was")
        editor.setAlignment(Qt.AlignHCenter)
        box = self.list.visualItemRect(entry)
        tall = editor.sizeHint().height()
        # over the page's number, where the label is shown
        words = self.list.delegate.lines_rect(box)
        top = min(words.top() - (tall - QFontMetrics(self.list.font()).height()) // 2,
                  box.bottom() - tall - 1)
        editor.setGeometry(box.left() + 2, top, max(box.width() - 4, 40), tall)
        editor.row = row
        editor.installEventFilter(self)
        editor.editingFinished.connect(lambda: self.finish_label_edit(keep=True))
        self.label_editor = editor
        editor.show()
        editor.selectAll()
        editor.setFocus(Qt.OtherFocusReason)
        return editor

    def finish_label_edit(self, keep: bool = True) -> None:
        """Close the label editor; with *keep*, the label typed is the page's."""
        editor = getattr(self, "label_editor", None)
        if editor is None:
            return
        self.label_editor = None
        row, text = editor.row, editor.text().strip()
        editor.hide()
        editor.deleteLater()
        self.list.setFocus(Qt.OtherFocusReason)
        if keep:
            self.window.set_page_label(row, text)

    def eventFilter(self, watched, event):
        """Ctrl+C and Ctrl+V on the thumbnails copy and paste whole pages.

        The window's own Copy and Paste are shortcuts, and a shortcut takes the
        key before the list ever sees it — so the list claims those two keys
        first (ShortcutOverride), and they reach it as keys.

        While a page is on the clipboard the pointer carries an insertion bar
        over the thumbnails, as Bluebeam's does: it says where Ctrl+V will put
        the page.
        """
        editor = getattr(self, "label_editor", None)
        if editor is not None and watched is editor:
            if event.type() == QEvent.ShortcutOverride:
                event.accept()             # typing a label never fires a shortcut
                return False
            if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
                self.finish_label_edit(keep=False)
                return True
            return False
        if watched is self.list and event.type() in (QEvent.ShortcutOverride,
                                                     QEvent.KeyPress) \
                and event.key() == Qt.Key_F2 and event.modifiers() == Qt.NoModifier:
            # F2: Rename Page Label, in place
            if event.type() == QEvent.ShortcutOverride:
                event.accept()
                return True
            row = self.list.currentRow()
            if row >= 0:
                self.edit_label(row)
            return True
        if watched is self.list and event.type() == QEvent.ShortcutOverride \
                and event.key() in (Qt.Key_Delete, Qt.Key_Backspace) \
                and not (event.modifiers() & (Qt.ControlModifier | Qt.AltModifier
                                              | Qt.ShiftModifier)) \
                and self.list.selectedItems():
            # Delete over the pages picked out deletes them (keyPressEvent):
            # claimed here first, or the window's Delete shortcut takes the
            # key whenever a markup is selected on the page, and the pages
            # stay (the user, 2026-10-29: "still can't click delete keyboard
            # to delete multiple selected pages")
            event.accept()
            return True
        if watched is self.list and event.type() in (QEvent.ShortcutOverride,
                                                     QEvent.KeyPress):
            copy = event.matches(QKeySequence.Copy)
            paste = event.matches(QKeySequence.Paste)
            if copy or paste:
                if event.type() == QEvent.ShortcutOverride:
                    event.accept()
                    return True
                if copy:
                    self.window.copy_page(self.list.currentRow())
                else:
                    self.paste_pages_here()
                return True
        if watched is self.list.viewport():
            kind = event.type()
            if kind == QEvent.MouseButtonPress and event.button() == Qt.LeftButton \
                    and not event.modifiers():
                point = event.position().toPoint()
                entry = self.list.itemAt(point)
                row = self.list.row(entry) if entry is not None else -1
                section = self.section_at(row)
                if section is not None and row == section.first \
                        and self.list.delegate.toggle_rect(
                            self.list.visualItemRect(entry)).contains(point):
                    self.toggle_section(row)    # its name: show or hide its pages
                    return True
            if kind == QEvent.MouseMove:
                self._hover_row = self.drop_row(event.position().toPoint())
                self.list.set_external_drop_row(
                    self._hover_row if self._a_page_is_waiting() else None)
            elif kind == QEvent.Leave:
                self._hover_row = None
                self.list.set_external_drop_row(None)
        return super().eventFilter(watched, event)

    def _clipboard_changed(self) -> None:
        try:
            waiting = self._a_page_is_waiting()
        except RuntimeError:
            return
        if not waiting:
            self.list.set_external_drop_row(None)
        elif self._hover_row is not None:
            self.list.set_external_drop_row(self._hover_row)

    def _a_page_is_waiting(self) -> bool:
        board = QApplication.clipboard()
        if QApplication.platformName() not in ("offscreen", "minimal") and \
                not board.ownsClipboard():
            # only a page copied here can be waiting; somebody else's clipboard
            # is not opened to find out (Excel holds it a moment after a copy,
            # and Windows then says "Retrying to obtain clipboard", 2026-10-10)
            return False
        text = board.text() or ""
        return text.startswith('{"calcforge_page"') and \
            self.window.page_on_the_clipboard() is not None

    def paste_row(self) -> int:
        """Where a pasted page goes: under the insertion bar, else after the
        page picked out."""
        hovered = getattr(self, "_hover_row", None)
        if hovered is not None:
            return max(0, min(int(hovered), self.list.count()))
        return max(self.list.currentRow(), 0) + 1

    def paste_pages_here(self) -> None:
        row = self.paste_row()
        self.list.set_external_drop_row(None)
        if row >= self.list.count():
            self.window.paste_page(self.list.count() - 1)
        else:
            self.window.paste_page(row, before=True)

    def _context_menu(self, point) -> None:
        """Right-click a thumbnail for everything you can do to that page."""
        entry = self.list.itemAt(point)
        index = self.list.row(entry) if entry is not None else self.list.currentRow()
        if index < 0:
            return
        # Right-clicking inside a picked-out run keeps the run: the menu is
        # about all of them. Right-clicking anywhere else is about that page,
        # so the run is dropped rather than acted on by surprise.
        if entry is not None and not entry.isSelected():
            self.list.clearSelection()
            entry.setSelected(True)
            self.list.setCurrentItem(entry)
        if index in self._collapsed:
            # a workbook's entry right-clicked: the menu is about all its pages
            self._section_pick.add(self._collapsed[index].key)
        menu = self.window.page_menu(index)
        menu.exec(self.list.viewport().mapToGlobal(point))

    def show_current(self, row: int, keep_run: bool = False) -> None:
        """Make *row* the page in view in the strip, as going to a page does
        (Home/End, Ctrl+arrows, the page box): it alone is picked out —
        unless it is one of a run picked out, which stays picked. A row
        clicked or keyed to in the strip itself is left as the strip picked
        it.

        QListWidget.setCurrentRow only swaps the row it last picked by
        itself: rows picked any other way (a run re-picked after a rebuild,
        pasted pages shown where they landed) stayed picked, so going on to
        another page added it to them, and Page Setup or Set Scale opened on
        "Selected" for pages nobody had picked (2026-10-17).

        *keep_run*: the page came into view by scrolling, zooming or
        fitting rather than being gone to. A run picked out stays picked and
        only the current row moves — scrolling to look is not a choice of
        pages (the user, 2026-10-17); one page picked follows the view."""
        listed = self.list
        entry = listed.item(row)
        shown = self.shown_row(row)
        if entry is not None:
            listed.set_in_view(shown)    # the outline goes where the reader is
        if entry is None or self._following_the_strip:
            return                      # the strip itself chose it: as it chose
        from PySide6.QtCore import QItemSelectionModel
        if shown != row:
            # a page of a workbook shown as one entry: the entry is outlined;
            # a run (or the workbook) picked out stays picked while scrolling,
            # and going to the page picks nothing (it is not the workbook)
            if keep_run and listed.selectedItems():
                return
            was = listed.blockSignals(True)
            listed.clearSelection()
            listed.selectionModel().setCurrentIndex(listed.indexFromItem(listed.item(shown)),
                                                    QItemSelectionModel.NoUpdate)
            listed.blockSignals(was)
            self._section_pick.clear()
            return
        index = listed.indexFromItem(entry)
        run = keep_run and len(listed.selectedItems()) > 1
        if entry.isSelected() or run:
            if listed.currentRow() == row:
                return
            flags = QItemSelectionModel.NoUpdate
        else:
            flags = QItemSelectionModel.ClearAndSelect
            self._section_pick.clear()  # gone to its first page, not picked
        was = listed.blockSignals(True)
        listed.selectionModel().setCurrentIndex(index, flags)
        listed.blockSignals(was)

    def pick(self, rows) -> None:
        """Pick out *rows* again after a rebuild (the page in view stays the
        current one)."""
        listed = self.list
        rows = [row for row in rows if 0 <= row < listed.count()]
        if not rows or rows == [listed.currentRow()]:
            return                      # the rebuild already picked it alone
        from PySide6.QtCore import QItemSelection, QItemSelectionModel
        chosen = QItemSelection()
        for row in rows:
            index = listed.model().index(row, 0)
            chosen.select(index, index)
        was = listed.blockSignals(True)
        listed.selectionModel().select(chosen, QItemSelectionModel.ClearAndSelect)
        listed.blockSignals(was)

    #: True while a row clicked (or keyed to) in the strip is being gone
    #: to: the strip has already picked what the click or key meant.
    _following_the_strip = False

    def _row_changed(self, row: int) -> None:
        if not self._suppress and row >= 0:
            self._following_the_strip = True
            try:
                self.pageSelected.emit(row)
            finally:
                self._following_the_strip = False

    def _clicked(self, entry) -> None:
        """A click on the thumbnail that is already the current row goes
        there too. Inside a workbook shown as one entry the current row is
        its entry while the page in view is one of its other pages (sheet
        two, say), so a click on the entry changed no row and went nowhere:
        the reader was stuck in the workbook (the user, 2026-10-22)."""
        row = self.list.row(entry)
        if self._suppress or row < 0:
            return
        if row == getattr(self.window, "current_index", row):
            # the page in view already — but a workbook's page clicked opens
            # the workbook view (sheetview.py), unless it is open
            from .sheetview import run_shown
            document = getattr(self.window, "document", None)
            page = document.pages[row] if document is not None and row < len(document.pages) \
                else None
            if page is None or page.sheet is None or \
                    run_shown(getattr(self.window, "scene", None)) == page.sheet:
                return
        self._following_the_strip = True
        try:
            self.pageSelected.emit(row)
        finally:
            self._following_the_strip = False

    def _rows_moved(self, _parent, start, end, _dest, row) -> None:
        """A run of pages has been dragged somewhere else in the strip.

        Qt says where the run began and ended and the row it was dropped in
        front of. Only the first page used to be passed on, so dragging six
        sheets moved one of them and left five behind.
        """
        if self._suppress:
            return
        count = max(end - start + 1, 1)
        target = row - count if row > start else row
        self.pagesReordered.emit(start, count, max(target, 0))

    def rebuild(self, document, current: int) -> None:
        self._suppress = True
        # a slot line belongs to the strip it was drawn on: pages pasted then
        # undone leave no line behind at their old place (QA F-26)
        self.list.set_external_drop_row(None)
        live = {id(page) for page in document.pages}
        for gone in [key for key in self._thumbnails if key not in live]:
            del self._thumbnails[gone]
        self.list.clear()
        lines = 1
        # numbered as printed: a page that doesn't print has no number, and
        # those after it move up (the user, 2026-10-22)
        numbers = document.printed_numbers()
        for index, page in enumerate(document.pages):
            # The scale rides with the page number: what a measurement on that
            # page means depends on it, and it belongs where the page is named
            # — on a line of its own under the number, as Revu has it.
            scale = page.scale.label if page.scale.is_calibrated() else ""
            parts = [str(numbers[index])] if numbers[index] else []
            label = page.label.strip()
            if label and label not in (str(numbers[index] or ""), str(index + 1)):
                parts.append(label)
            caption = "   ".join(parts)
            if scale:
                caption += "\n" + scale
                lines = 2
            entry = QListWidgetItem(self._placeholder(page, document), caption)
            entry.setTextAlignment(Qt.AlignHCenter)
            tip = page.label or page.source_note or (
                f"Page {numbers[index]}" if numbers[index] else "No page number")
            tip += f"\nPage {index + 1} of the document's {len(document.pages)} (the page box)"
            if not page.printable:
                entry.setForeground(QColor("#8b929c"))
                tip += "\nExcluded from print and export"
            entry.setToolTip(f"{tip}\n{page.setup.size_name} {page.setup.orientation}"
                             f"\nScale {page.scale.label}")
            entry.setData(NO_PRINT_ROLE, 0 if page.printable else 2)
            if index > 0 and getattr(page, "section_break", False):
                from .calcsections import section_of_page
                entry.setData(BREAK_ROLE, section_of_page(document, index).short)
            self.list.addItem(entry)
        if self._sections_in(document):
            lines = 2                        # a workbook's name over its pages
        self.list.caption_lines = lines
        self.list.relayout()                 # the rows the pages now need
        shown = self.shown_row(current)
        if shown != current:
            from PySide6.QtCore import QItemSelectionModel
            self.list.selectionModel().setCurrentIndex(
                self.list.model().index(shown, 0), QItemSelectionModel.NoUpdate)
        else:
            self.list.setCurrentRow(current)
        self.list.in_view_row = shown
        self._suppress = False
        self._draw_what_is_on_screen()

    # -- workbooks: one entry each, its pages shown on asking ----------------------
    def _sections_in(self, document) -> list:
        """Mark each workbook in the strip (the user, 2026-10-21: "treat
        spreadsheet workbooks as a section ... shown in the thumbnail too
        instead of individual pages"): its first page's thumbnail is its
        entry, "▸ Loads" over "pages 2–10", on a stack of sheets, and its
        other pages are hidden behind it until it is expanded (collapsed to
        start, so a long workbook doesn't push the drawings out of sight).
        The page numbers stay the document's."""
        from .sheetpages import sections
        found = sections(document, fresh=True)
        self._collapsed = {}
        self._hidden = {}
        self._members = {}
        listed = self.list
        keys = {section.key for section in found}
        self.expanded &= keys
        self._section_pick &= keys
        for section in found:
            collapsed = section.key not in self.expanded
            pages = [document.pages[i] for i in section.pages]
            printing = sum(1 for page in pages if page.printable)
            silent = 0 if printing == len(pages) else (2 if printing == 0 else 1)
            for row in section.pages:
                self._members[row] = section
                entry = listed.item(row)
                if entry is None:
                    continue
                head = row == section.first
                entry.setData(SECTION_ROLE, {"head": head, "collapsed": collapsed and head,
                                             "member": not collapsed, "key": section.key})
                listed.setRowHidden(row, collapsed and not head)
                if collapsed and not head:
                    self._hidden[row] = section
            head = listed.item(section.first)
            if head is None:
                continue
            sheets = ", ".join(section._names)
            if collapsed:
                self._collapsed[section.first] = section
                head.setText(f"▸ {section.name}\n{section.page_range()}")
                head.setData(NO_PRINT_ROLE, silent)
                if silent == 2:
                    head.setForeground(QColor("#8b929c"))
                else:
                    head.setData(Qt.ForegroundRole, None)
                said = {0: "", 1: f"\n{len(pages) - printing} of its {len(pages)} pages "
                        "don't print", 2: "\nIt doesn't print"}[silent]
                head.setToolTip(f"{section.label()}\nSheets: {sheets}{said}\n"
                                "Click the picture to go to it; click its name to show "
                                "its pages")
            else:
                number = head.text().split("\n")
                head.setText(f"▾ {section.name}\n{number[0]}")
                head.setToolTip(f"{section.label()}\nSheets: {sheets}\n"
                                "Click its name to show it as one entry\n" + head.toolTip())
        return found

    _collapsed: dict = {}
    _hidden: dict = {}
    _members: dict = {}

    def shown_row(self, row: int) -> int:
        """The thumbnail that shows page *row*: its workbook's entry when
        its pages are hidden behind it."""
        section = self._hidden.get(row)
        return section.first if section is not None else row

    def section_at(self, row: int):
        """The workbook page *row* is a page of, as the strip shows it."""
        return self._members.get(row)

    def is_collapsed(self, key: str) -> bool:
        return key not in self.expanded

    def set_expanded(self, key: str, on: bool) -> None:
        """Show a workbook's pages one by one (or as one entry again)."""
        if on == (key in self.expanded):
            return
        picked = self.picked_rows()
        if on:
            self.expanded.add(key)
        else:
            self.expanded.discard(key)
        self._section_pick.discard(key)
        document = getattr(self.window, "document", None)
        if document is not None:
            self.rebuild(document, getattr(self.window, "current_index", 0))
            self.pick([row for row in picked if not self.list.isRowHidden(row)])

    def toggle_section(self, row: int) -> None:
        section = self.section_at(row)
        if section is not None:
            self.set_expanded(section.key, self.is_collapsed(section.key))

    def add_section_entries(self, menu: QMenu, index: int) -> None:
        """A page of a workbook's menu: Expand Section (its pages one by one
        in Thumbnails) or Collapse Section (one entry again), and an imported
        workbook's Self-contained tick, as on its sheet tab (the user,
        2026-10-24: "right click on workbook in thumbnail wont let me
        selection self contained vs not")."""
        from .sheetpages import section_of
        document = getattr(self.window, "document", None)
        section = section_of(document, index) if document is not None else None
        if section is None:
            return
        from ..sheet.docbook import book_for
        from .workbookscope import tab_action
        sheet = next((s for s in (book_for(document).by_uid.get(uid) for uid in section.runs)
                      if s is not None), None)
        tab_action(menu, sheet, self.window)
        if self.is_collapsed(section.key):
            entry = menu.addAction("Expand Section",
                                   lambda: self.set_expanded(section.key, True))
            entry.setToolTip(f"Show {section.label()} page by page in Thumbnails")
        else:
            entry = menu.addAction("Collapse Section",
                                   lambda: self.set_expanded(section.key, False))
            entry.setToolTip(f"Show {section.label()} as one entry in Thumbnails")

    def delete_picked(self) -> None:
        """The pages picked out deleted, after asking ("Delete these 3
        pages?"); a workbook's entry is all its pages."""
        rows = self.picked_rows()
        if rows:
            self.window.delete_page(pages=rows)

    def picked_rows(self) -> list:
        """The pages picked out: a workbook's entry, picked in the strip,
        is all its pages (deleted, moved, copied or extracted together)."""
        rows = sorted(self.list.row(entry) for entry in self.list.selectedItems())
        out = []
        for row in rows:
            section = self._collapsed.get(row)
            if section is not None and section.key in self._section_pick:
                out.extend(section.pages)
            else:
                out.append(row)
        return sorted(set(out))

    def _picked_in_strip(self) -> None:
        """The reader picked thumbnails: a workbook's entry among them is
        the workbook."""
        if self._suppress:
            return
        self._section_pick = {self._collapsed[self.list.row(entry)].key
                              for entry in self.list.selectedItems()
                              if self.list.row(entry) in self._collapsed}

    def _placeholder(self, page, document) -> QIcon:
        """A row's picture until it is in view: a PDF page's small sheet if
        it is already drawn, or what the row last showed, or a blank page of
        its shape. Drawing every sheet page of a 69-page workbook here took
        seven seconds of its opening (2026-10-10)."""
        if page.pdf_key:
            return self._thumbnail(page, document, ask=False)
        kept = self._thumbnails.get(id(page))
        if kept is not None and kept[2] is page:
            return kept[1]
        scale = getattr(self.list, "scale", 1.0)
        return self._blank_for(page, max(int(160 * scale), 24))

    def _draw_what_is_on_screen(self) -> None:
        """Ask for the sheets of the rows somebody can actually see.

        A forty-page set has forty sheets to draw and a dozen rows on screen.
        Drawing all of them before the window will move is six seconds of a
        drawing set opening; drawing the ones in view is a few hundred
        milliseconds, and the rest arrive as they are scrolled to.
        """
        document = getattr(self.window, "document", None)
        if document is None:
            return
        showing = self.list.viewport().rect()
        for index in range(self.list.count()):
            if not 0 <= index < len(document.pages):
                break
            entry = self.list.item(index)
            if entry is None or self.list.isRowHidden(index):
                continue                 # a workbook's pages behind its entry
            # A row well below the fold is not worth a render yet. The margin
            # is a screenful, so scrolling lands on sheets already drawn.
            box = self.list.visualItemRect(entry)
            if box.bottom() < -showing.height() or \
                    box.top() > showing.height() * 2:
                continue
            entry.setIcon(self._thumbnail(document.pages[index], document))

    def let_go(self) -> None:
        """Its window has closed for good: no more pages drawn for it, and
        no more clipboard watching."""
        import warnings
        from ..io import pdftiles
        for signal, slot in ((pdftiles.TILES.sheetReady, self._page_was_drawn),
                             (QApplication.clipboard().dataChanged, self._clipboard_changed)):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                try:
                    signal.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass

    def _page_was_drawn(self, key) -> None:
        """Fill in the row whose page has just been drawn, and only that one."""
        document = getattr(self.window, "document", None)
        if document is None:
            return
        for index, page in enumerate(document.pages):
            if page.pdf_key == key.source and page.pdf_page_index == key.index:
                entry = self.list.item(index)
                if entry is not None:
                    entry.setIcon(self._thumbnail(page, document))

    def refresh_current(self, document, current: int) -> None:
        entry = self.list.item(current)
        if entry is not None and 0 <= current < len(document.pages):
            entry.setIcon(self._thumbnail(document.pages[current], document))

    #: The longest and shortest wait after an edit before the thumbnails
    #: catch up, in milliseconds.
    LONGEST_WAIT = 400
    SHORTEST_WAIT = 40

    def refresh_soon(self) -> None:
        """An edit was made: the thumbnails it changed are drawn again once
        the edits stop. The wait is a few times what drawing them took last,
        so an ordinary page catches up at once (an Undo, a cell typed in a
        table: QA F-26) while a page of a thousand markups still waits for
        the drag to end rather than drawing on every move (2026-10-05)."""
        timer = getattr(self, "_refresh_timer", None)
        if timer is None:
            timer = self._refresh_timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._refresh_changed)
        cost = getattr(self, "_refresh_cost", 0.0)
        timer.start(int(max(self.SHORTEST_WAIT, min(self.LONGEST_WAIT, cost * 4))))

    def _refresh_changed(self) -> None:
        """Every thumbnail in view whose page changed — not only the current
        one: an Undo can change a page that is not the one shown."""
        import time
        start = time.perf_counter()
        document = getattr(self.window, "document", None)
        current = getattr(self.window, "current_index", -1)
        if document is not None:
            self.refresh_current(document, current)
            self._draw_what_is_on_screen()
        took = (time.perf_counter() - start) * 1000
        if took > 2.0:                     # a picture was drawn, not only looked up
            self._refresh_cost = took

    @staticmethod
    def _with_markups(sheet, page):
        """The page's markups and calculations drawn over its sheet: the PDF
        holds the drawing, but what was put on it lives on the canvas (and a
        CalcForge file's calculations are taken out of the PDF on opening)."""
        frame = page.frame
        if frame is None:
            return sheet
        items = [i for i in frame.markups() if i.isVisible() and not i.from_drawing]
        if not items:
            return sheet
        from PySide6.QtGui import QPainter
        from PySide6.QtCore import QRectF
        image = sheet.toImage() if hasattr(sheet, "toImage") else sheet
        painter = QPainter(image)
        painter.scale(image.width() / max(page.width_pt, 1.0),
                      image.height() / max(page.height_pt, 1.0))
        previous = frame.print_mode
        frame.print_mode = True                  # no handles or selection boxes
        try:
            frame.paint_items(painter, items, QRectF(0, 0, page.width_pt, page.height_pt))
        finally:
            frame.print_mode = previous
            painter.end()
        return QPixmap.fromImage(image) if hasattr(sheet, "toImage") else image

    def _thumbnail(self, page, document=None, ask: bool = True) -> QIcon:
        """A small picture of the page for the list.

        A page that came in from a PDF is drawn once, small, in the background
        for the canvas to have something to show while its tiles arrive — so
        the list borrows that rather than rendering every page again. Opening
        a drawing set used to spend half a second here doing exactly the work
        that was already being done.

        Made at whatever size the list is showing them at, not at one size and
        stretched: the picture it is cut from has resolution to spare, so a
        list zoomed in gets sharper pages rather than bigger blurry ones.
        """
        scale = getattr(self.list, "scale", 1.0)
        across = max(int(160 * scale), 24)
        frame = page.frame
        if frame is not None:
            # Drawn again only when something on the page has changed: a page
            # of a thousand markups drew all of them into its thumbnail every
            # time a page was added anywhere (2026-10-05).
            key = (across, frame.layer.generation, page.width_pt, page.height_pt,
                   page.pdf_key, page.pdf_page_index, page.background_key,
                   page.grid, page.header, page.footer, page.turn,
                   bool(getattr(page, "pdf_annotations", True)))
            kept = self._thumbnails.get(id(page))
            if kept is not None and kept[0] == key and kept[2] is page:
                return kept[1]
            made = self._thumbnail_drawn(page, document, ask, scale, across)
            if made is not None:
                self._thumbnails[id(page)] = (key, made, page)
                return made
        made = self._thumbnail_drawn(page, document, ask, scale, across)
        return made if made is not None else self._blank_for(page, across)

    def _blank_for(self, page, across: int) -> QIcon:
        tall = int(across * page.height_pt / max(page.width_pt, 1.0))
        waiting = QPixmap(across, max(tall, 1))
        waiting.fill(Qt.white)
        return _untinted(waiting)

    def _thumbnail_drawn(self, page, document, ask: bool, scale: float, across: int):
        """The thumbnail, or None while the page's sheet is still coming."""
        if document is not None and page.pdf_key and page.pdf_page_index is not None:
            data = document.asset(page.pdf_key)
            if data:
                from ..io import pdftiles
                from PySide6.QtCore import QRectF

                whole = QRectF(0, 0, page.width_pt, page.height_pt)
                sheet = pdftiles.TILES.sheet(
                    page.pdf_key, data, int(page.pdf_page_index), whole,
                    bool(getattr(page, "pdf_annotations", True)), ask=ask)
                if sheet is not None and not sheet.isNull():
                    small = sheet.scaled(across, across, Qt.KeepAspectRatio,
                                         Qt.SmoothTransformation)
                    return _untinted(self._with_markups(small, page))
                # Not drawn yet. A blank sheet of the right shape now, and the
                # row is refreshed when the picture arrives.
                return None
        scene = page.frame
        if scene is None:
            pixmap = QPixmap(max(int(96 * scale), 16), max(int(128 * scale), 20))
            pixmap.fill(Qt.white)
            return _untinted(pixmap)
        image = scene.render_image(dpi=18.0 * scale, for_print=False)
        return _untinted(QPixmap.fromImage(image))


# ---------------------------------------------------------------------------
# Markups list
# ---------------------------------------------------------------------------

def _comment_of(item) -> str:
    """The Markups list's Comment column, as Revu's Comments: the comment
    typed for the markup, or a text markup's own words — never its size or
    measurement, which are the Value column's (QA F-25)."""
    said = (getattr(item, "comment", "") or "").replace("\n", " ").strip()
    if said:
        return said[:160]
    if hasattr(item, "doc"):               # text box, callout: what it says
        return item.summary()
    return ""


@functools.lru_cache(maxsize=16384)
def _natural_key(text: str) -> tuple:
    """"Page 10" after "Page 9", "12.5" after "9": numbers compared as numbers.
    (Kept: sorting a thousand rows asks for each one's a dozen times.)"""
    import re
    return tuple((0, float(part), "") if part[:1].isdigit() else (1, 0.0, part.lower())
                 for part in re.findall(r"\d+(?:\.\d+)?|\D+", text or ""))


def _type_of(item) -> str:
    """The Markups list's Type column: what kind of markup it is, as
    Revu's Type, with its label in the Label column rather than here."""
    label = getattr(item, "label", "")
    if not label:
        return item.display_name()
    item.label = ""                    # a plain attribute: display_name reads it
    try:
        return item.display_name()
    finally:
        item.label = label


def _flat(text: str) -> str:
    """*text* on one line for a cell's editor, a character for each one
    (a line break becomes a space), so an edit made on the one line can be
    put back into the text with its other line breaks kept."""
    return (text or "").replace("\r", " ").replace("\n", " ")


def _spliced(before: str, after: str) -> tuple:
    """(start, end, words): what changed from *before* to *after*, as the
    span of *before* to replace and what to put there."""
    most = min(len(before), len(after))
    start = 0
    while start < most and before[start] == after[start]:
        start += 1
    tail = 0
    while tail < most - start and before[-1 - tail] == after[-1 - tail]:
        tail += 1
    return start, len(before) - tail, after[start:len(after) - tail]


class _MarkupCellDelegate(QStyledItemDelegate):
    """Revu's in-place editing of the Markups list's cells: Subject, Label,
    Author and Comment (a text box's or callout's words) take a box in the
    cell; Enter keeps what was typed, Esc leaves the cell as it was. The
    other columns (Page, Type, Date, the measured Value, the look) are read
    only: no box opens on them."""

    def __init__(self, panel):
        super().__init__(panel.tree)
        self.panel = panel

    def createEditor(self, parent, option, index):            # noqa: N802
        if self.panel.editable_at(index) is None:
            return None
        editor = QLineEdit(parent)
        editor.setObjectName("markupCellEditor")
        editor.setFrame(False)
        return editor

    def setEditorData(self, editor, index) -> None:           # noqa: N802
        found = self.panel.editable_at(index)
        if found is not None:
            editor.setText(self.panel.cell_text(*found))
            editor.selectAll()

    def setModelData(self, editor, model, index) -> None:     # noqa: N802
        found = self.panel.editable_at(index)
        if found is None:
            return
        text = editor.text()
        # Kept once the editor has closed: putting it in rebuilds the list,
        # which must not happen under the editor that is closing.
        QTimer.singleShot(0, self.panel, lambda: self.panel.set_cell(*found, text))

    def eventFilter(self, editor, event) -> bool:             # noqa: N802
        if event.type() == QEvent.ShortcutOverride and event.key() != Qt.Key_Escape:
            # typing in the cell never fires a shortcut (V, Delete, Ctrl+Z
            # are the words' own while the box is open)
            event.accept()
            return False
        return super().eventFilter(editor, event)


class _MarkupRow(QTreeWidgetItem):
    """A row (or a page heading) of the Markups list, sorted as a person
    reads it: Page 2 before Page 10, a width of 2 before 10."""

    def __lt__(self, other) -> bool:
        tree = self.treeWidget()
        column = tree.sortColumn() if tree is not None else 0
        return _natural_key(self.text(column)) < _natural_key(other.text(column))


class _FilterHeader(QHeaderView):
    """The Markups list's headings with Revu's filter button on each.

    A left-click on a heading sorts by it; a left-click on the filter button
    at its right end opens that column's filter list (Revu's Filter List),
    which used to be only on a right-click nobody looks for (novice finding
    14). The button is a small ▾, brighter under the pointer, and a blue
    funnel while the column is filtered.

    Each heading is drawn as Revu draws it, flat with a thin separator: the
    title on the left, cut short with "…" when the column is narrow, the
    sort arrow just after it, and the filter button at the right edge. The
    three never overlap at any width (the user, 2026-10-19: Qt's own sort
    arrow sat under the funnel); ``parts`` says where each one is.
    """

    filterClicked = Signal(int, QPoint)
    BUTTON = 14
    #: the sort arrow's box, and the gaps around the parts
    ARROW = 9
    PAD = 6
    GAP = 4

    def __init__(self, panel):
        super().__init__(Qt.Horizontal)
        self.panel = panel
        self.setSectionsClickable(True)
        self.setMouseTracking(True)
        self.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        #: (section under the pointer, whether it is on that section's button)
        self._hover = (-1, False)
        self._fit_minimum()

    # -- where things are --------------------------------------------------
    def _button_size(self) -> int:
        return max(self.BUTTON, round(self.fontMetrics().height() * 0.9))

    def _fit_minimum(self) -> None:
        """No column narrower than its sort arrow and filter button side by
        side: a narrower one would have to draw one over the other."""
        self.setMinimumSectionSize(self.PAD + self.ARROW + self.GAP // 2
                                   + self._button_size() + 3 + 2)

    def changeEvent(self, event) -> None:                       # noqa: N802
        if event.type() in (QEvent.FontChange, QEvent.StyleChange):
            self._fit_minimum()
        super().changeEvent(event)

    def section_rect(self, logical: int) -> QRect:
        """Column *logical*'s heading, in the header."""
        return QRect(self.sectionViewportPosition(logical), 0,
                     self.sectionSize(logical), self.viewport().height())

    def _parts_in(self, rect: QRect, logical: int) -> tuple:
        """(title, shown title, sort arrow, filter button) of the heading
        drawn in *rect*; an empty QRect for a part not shown."""
        metrics = self.fontMetrics()
        title = str(self.model().headerData(logical, Qt.Horizontal, Qt.DisplayRole) or "") \
            if self.model() is not None else ""
        right = rect.right() + 1 - self.PAD
        button = QRect()
        if self.panel.filter_list_on():
            size = self._button_size()
            button = QRect(rect.right() + 1 - 3 - size, rect.top() + (rect.height() - size) // 2,
                           size, size)
            right = button.left() - self.GAP // 2
        left = rect.left() + self.PAD
        sorted_here = self.isSortIndicatorShown() and self.sortIndicatorSection() == logical
        arrow = QRect()
        room = right - left
        if sorted_here and room >= self.ARROW:
            room -= self.ARROW + self.GAP
        shown = metrics.elidedText(title, Qt.ElideRight, max(room, 0)) if room > 0 else ""
        width = min(metrics.horizontalAdvance(shown), max(room, 0)) if shown else 0
        text = QRect(left, rect.top(), width, rect.height())
        if sorted_here and right - left >= self.ARROW:
            x = left + width + (self.GAP if width else 0)
            arrow = QRect(x, rect.top() + (rect.height() - self.ARROW) // 2,
                          self.ARROW, self.ARROW)
        return text, shown, arrow, button

    def parts(self, logical: int) -> tuple:
        """(title, sort arrow, filter button) of column *logical*'s heading,
        in the header; an empty QRect for a part not shown."""
        text, _shown, arrow, button = self._parts_in(self.section_rect(logical), logical)
        return text, arrow, button

    def filter_rect(self, logical: int) -> QRect:
        """Where column *logical*'s filter button is, in the header."""
        return self._parts_in(self.section_rect(logical), logical)[3]

    def sectionSizeFromContents(self, logical: int) -> QSize:   # noqa: N802
        size = super().sectionSizeFromContents(logical)
        title = str(self.model().headerData(logical, Qt.Horizontal, Qt.DisplayRole) or "") \
            if self.model() is not None else ""
        wide = (self.PAD + self.fontMetrics().horizontalAdvance(title) + self.GAP + self.ARROW
                + self.GAP + self._button_size() + 3)
        return QSize(max(wide, self.minimumSectionSize()), size.height())

    # -- drawing -----------------------------------------------------------
    def paintSection(self, painter: QPainter, rect: QRect, logical: int) -> None:  # noqa: N802
        if not rect.isValid():
            return
        from PySide6.QtWidgets import QStyle, QStyleOptionHeader
        option = QStyleOptionHeader()
        self.initStyleOptionForIndex(option, logical)
        option.rect = rect
        option.text = ""
        option.icon = QIcon()
        option.sortIndicator = QStyleOptionHeader.SortIndicator.None_
        painter.save()
        # the theme's flat heading with its thin separator, and nothing on it:
        # the title, the arrow and the button are put where they fit below
        self.style().drawControl(QStyle.CE_HeaderSection, option, painter, self)
        painter.restore()
        text, shown, arrow, button = self._parts_in(rect, logical)
        ink = self.palette().windowText().color()
        painter.save()
        painter.setClipRect(rect)
        if shown:
            painter.setPen(ink)
            painter.setFont(self.font())
            painter.drawText(text, Qt.AlignLeft | Qt.AlignVCenter, shown)
        painter.setRenderHint(QPainter.Antialiasing, True)
        if not arrow.isNull():
            # a small line chevron, up while A to Z and down while Z to A —
            # drawn in line, not filled, so it is never taken for the filter's ▾
            soft = QColor(ink)
            soft.setAlpha(210)
            pen = QPen(soft, 1.3)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            box = QRectF(arrow).adjusted(1, 2.5, -1, -2.5)
            if self.sortIndicatorOrder() == Qt.AscendingOrder:
                points = [QPointF(box.left(), box.bottom()), QPointF(box.center().x(), box.top()),
                          QPointF(box.right(), box.bottom())]
            else:
                points = [QPointF(box.left(), box.top()), QPointF(box.center().x(), box.bottom()),
                          QPointF(box.right(), box.top())]
            painter.drawPolyline(QPolygonF(points))
        if not button.isNull():
            self._paint_button(painter, button, logical, ink)
        painter.restore()

    def _paint_button(self, painter: QPainter, button: QRect, logical: int, ink: QColor) -> None:
        hovered, on_button = self._hover
        filtered = logical in self.panel.column_filters
        if hovered == logical and on_button:
            back = QColor(ink)
            back.setAlpha(40)
            painter.setPen(Qt.NoPen)
            painter.setBrush(back)
            painter.drawRoundedRect(QRectF(button), 2, 2)
        painter.setPen(Qt.NoPen)
        if filtered:
            # the funnel, blue, while the column is narrowed
            painter.setBrush(QColor("#0083db"))
            b = QRectF(button).adjusted(2.5, 3, -2.5, -3)
            funnel = QPolygonF([QPointF(b.left(), b.top()), QPointF(b.right(), b.top()),
                                QPointF(b.center().x() + 1.2, b.center().y() + 0.5),
                                QPointF(b.center().x() + 1.2, b.bottom()),
                                QPointF(b.center().x() - 1.2, b.bottom() - 1.5),
                                QPointF(b.center().x() - 1.2, b.center().y() + 0.5)])
            painter.drawPolygon(funnel)
            return
        # the drop-down's small ▾: faint until the pointer is on the heading
        glyph = QColor(ink)
        glyph.setAlpha(230 if hovered == logical else 120)
        painter.setBrush(glyph)
        centre = QRectF(button).center()
        painter.drawPolygon(QPolygonF([QPointF(centre.x() - 3.5, centre.y() - 1.75),
                                       QPointF(centre.x() + 3.5, centre.y() - 1.75),
                                       QPointF(centre.x(), centre.y() + 2.25)]))

    # -- the pointer -------------------------------------------------------
    def _set_hover(self, point) -> None:
        if point is None:
            hover = (-1, False)
        else:
            logical = self.logicalIndexAt(point)
            hover = (logical, logical >= 0 and self.panel.filter_list_on()
                     and self.filter_rect(logical).contains(point))
        if hover != self._hover:
            self._hover = hover
            self.viewport().update()

    def mouseMoveEvent(self, event) -> None:                     # noqa: N802
        self._set_hover(event.position().toPoint())
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:                         # noqa: N802
        self._set_hover(None)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:                    # noqa: N802
        if event.button() == Qt.LeftButton:
            point = event.position().toPoint()
            logical = self.logicalIndexAt(point)
            if logical >= 0 and self.panel.filter_list_on() \
                    and self.filter_rect(logical).contains(point):
                self.filterClicked.emit(logical, self.mapToGlobal(
                    self.filter_rect(logical).bottomLeft()))
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:                  # noqa: N802
        point = event.position().toPoint()
        logical = self.logicalIndexAt(point)
        if (event.button() == Qt.LeftButton and logical >= 0 and self.panel.filter_list_on()
                and self.filter_rect(logical).contains(point)):
            event.accept()             # the press opened the filter: no sort
            return
        super().mouseReleaseEvent(event)


class MarkupsPanel(QWidget):
    """Every markup in the document as a list, the way Bluebeam's Markups list works.

    Columns for what a markup looks like as well as what it is — colour, fill,
    line, width, opacity, font — so markups can be found by their look.
    Each heading sorts, and its filter button narrows the list to chosen
    values. Rows can be grouped by page, type, subject, colour or author.

    Picking rows picks those markups on the page, several at once, and the
    right-click menu changes all of them together: colour, fill, width, line
    style, font size, opacity, lock, hide or delete.
    """

    markupActivated = Signal(int, str)
    markupPicked = Signal(int, str)
    markupsPicked = Signal(list)          # [(page index, uid), ...]

    COLUMNS = ["Page", "Type", "Subject", "Label", "Colour", "Fill", "Line", "Width",
               "Opacity", "Font", "Size", "Value", "Checked", "Author", "Date", "Comment"]
    #: the columns edited in place, as Revu's, and what each one changes
    EDITABLE = {"Subject": "subject", "Label": "label", "Author": "author",
                "Comment": "comment"}
    GROUPS = ["Page", "Type", "Subject", "Colour", "Author", "None"]

    def __init__(self, window):
        super().__init__()
        self.window = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        top = QHBoxLayout()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter markups…")
        self.filter.setClearButtonEnabled(True)
        # Built again a moment after the typing stops, not at every key: with
        # a thousand markups one rebuild of the list is a tenth of a second,
        # and every key waited for it (2026-10-17).
        self._list_timer = QTimer(self)
        self._list_timer.setSingleShot(True)
        self._list_timer.setInterval(LIST_AFTER_MS)
        self._list_timer.timeout.connect(lambda: self.rebuild(self.window.document))
        self.filter.textChanged.connect(lambda _: self._list_timer.start())
        top.addWidget(self.filter, 1)
        # Revu's Filter List, beside the search: the filter on each column's
        # heading shown, or hidden with the filters kept but not used ("To
        # toggle off filtering without losing the filters you've set")
        self.filter_list = QToolButton()
        self.filter_list.setObjectName("markupsFilterList")
        self.filter_list.setText("Filter List")
        self.filter_list.setIcon(icon("filter_list", 16))
        self.filter_list.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.filter_list.setAutoRaise(True)
        self.filter_list.setCheckable(True)
        self.filter_list.setToolTip("Filter List: a filter on each column's heading; "
                                    "off, the filters are kept but not used")
        self.filter_list.setChecked(_remembered_filter_list())
        self.filter_list.toggled.connect(self.set_filter_list)
        top.addWidget(self.filter_list)
        layout.addLayout(top)
        top = QHBoxLayout()
        self.group_by = QComboBox()
        self.group_by.setToolTip("Group the list by")
        for name in self.GROUPS:
            self.group_by.addItem(f"By {name.lower()}" if name != "None" else "No groups",
                                  name)
        self.group_by.currentIndexChanged.connect(
            lambda _: self.rebuild(self.window.document))
        top.addWidget(self.group_by)
        self.clear_filters = QToolButton()
        self.clear_filters.setText("All")
        self.clear_filters.setToolTip("Clear every column filter")
        self.clear_filters.clicked.connect(self._clear_column_filters)
        top.addWidget(self.clear_filters)
        export = QToolButton()
        export.setText("CSV")
        export.setToolTip("Export the markups list to CSV")
        export.clicked.connect(self.export_csv)
        top.addWidget(export)
        top.addStretch(1)
        layout.addLayout(top)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(len(self.COLUMNS))
        self.tree.setHeaderLabels(self.COLUMNS)
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.itemDoubleClicked.connect(self._activate)
        self.tree.itemSelectionChanged.connect(self._picked)
        # Revu's in-place editing: a click on a picked row's cell, a
        # double-click, or F2 opens the cell's box (editable columns only)
        self.tree.setItemDelegate(_MarkupCellDelegate(self))
        self.tree.setEditTriggers(QAbstractItemView.DoubleClicked
                                  | QAbstractItemView.SelectedClicked
                                  | QAbstractItemView.EditKeyPressed)
        self.tree.installEventFilter(self)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._row_menu)
        # Values each column is narrowed to; a column not here shows all.
        self.column_filters: dict[int, set] = {}
        header = _FilterHeader(self)
        self.tree.setHeader(header)
        header.filterClicked.connect(self.filter_menu)
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionsMovable(True)
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(
            lambda point: self.filter_menu(header.logicalIndexAt(point),
                                           header.mapToGlobal(point))
            if self.filter_list_on() else None)
        self.tree.setSortingEnabled(True)
        # Page 1 first, as Revu lists them (Qt starts a sorted list descending)
        self.tree.sortByColumn(0, Qt.AscendingOrder)
        # Sizing a column to its contents reads a sample of the rows, not all
        # of them: with a thousand markups, all of them was a tenth of a
        # second each time anything changed (2026-10-05).
        self.tree.header().setResizeContentsPrecision(64)
        layout.addWidget(self.tree, 1)
        # True while the list is being rebuilt or is following the canvas, so
        # that putting a selection into it does not send that selection
        # straight back out and fight whatever set it.
        self._echoing = False
        self._items: dict = {}
        #: each row's node, by (page index, markup id)
        self._nodes: dict = {}
        #: what the list was last built from (rebuild)
        self._shown_before = None
        #: Revu dims on the page the markups the filter leaves out: a moment
        #: after the list changes, so typing in the search box never waits
        #: for the page (filterdim.py)
        self._dim_timer = QTimer(self)
        self._dim_timer.setSingleShot(True)
        self._dim_timer.setInterval(DIM_AFTER_MS)
        self._dim_timer.timeout.connect(self.dim_filtered_now)
        self._any_dimmed = False

        self.totals = QLabel("")
        self.totals.setWordWrap(True)
        self.totals.setStyleSheet("color:#4a5261; padding:2px;")
        layout.addWidget(self.totals)

    # -- the rows ----------------------------------------------------------
    @staticmethod
    def row_for(index: int, item) -> list[str]:
        style = item.style
        text_like = hasattr(item, "doc")
        return [str(index + 1), _type_of(item), item.subject, item.label,
                style.stroke or "none", style.fill or "none",
                style.line_style, f"{style.width:g}",
                f"{round(style.opacity * 100):d}%",
                style.font_family if text_like else "",
                f"{style.font_size:g}" if text_like else "",
                getattr(item, "value_text", ""),
                # a Checkbox's ticked options: "Satisfactory", or "A; C"
                item.checked_text() if hasattr(item, "checked_text") else "",
                item.author, item.modified[:10], _comment_of(item)]

    def filter_list_on(self) -> bool:
        """Whether Filter List is on: the column filters shown and used."""
        return self.filter_list.isChecked()

    def active_filters(self) -> dict:
        """The column filters in use: none while Filter List is off (they
        are kept, to come back when it is turned on)."""
        return self.column_filters if self.filter_list_on() else {}

    def set_filter_list(self, on: bool) -> None:
        """Filter List on or off: the headings' filters shown or hidden, the
        filters used or set aside, and the page's dimming following."""
        if self.filter_list.isChecked() != bool(on):
            self.filter_list.setChecked(bool(on))       # comes back here
            return
        settings = app_settings()
        settings.setValue(FILTER_LIST_KEY, bool(on))
        self.tree.header().viewport().update()
        self.rebuild(self.window.document)

    def _shown(self, row: list[str], needle: str) -> bool:
        if needle and not any(needle in str(cell).lower() for cell in row):
            return False
        return all(row[column] in allowed
                   for column, allowed in self.active_filters().items())

    def filtered_out(self, document) -> list:
        """The markups the list's filter (its search box and its column
        filters) leaves out — those Print's Dim Filtered Markups tones down."""
        needle = self.filter.text().strip().lower()
        if not needle and not self.active_filters():
            return []
        return [item for _index, item, row in self.all_rows(document)
                if not self._shown(row, needle)]

    def all_rows(self, document) -> list:
        """(page index, item, row) for every markup, before any filtering."""
        found = []
        for index, page in enumerate(document.pages):
            if page.frame is None:
                continue
            # (built so far: a page's markups come as it is looked at)
            for item in page.frame.ordered_markups():
                if getattr(item, "from_drawing", False):
                    continue
                if getattr(item, "IS_CALC", False):
                    continue           # the Markups list is markups only (decision 21)
                found.append((index, item, self.row_for(index, item)))
        return found

    def _what_is_shown(self, document, found) -> tuple:
        """Everything the list's rows are made from, to tell whether
        building them again would change them: how it is filtered and
        grouped, and each page's rows in reading order."""
        pages: dict = {}
        for index, item, row in found:
            pages.setdefault(index, []).append(self._signed(item, row))
        return (self._heading_of_what_is_shown(document),
                {index: tuple(rows) for index, rows in pages.items()})

    def _heading_of_what_is_shown(self, document) -> tuple:
        return (self.filter.text().strip().lower(), self.group_by.currentData() or "Page",
                tuple(sorted((column, tuple(sorted(allowed)))
                             for column, allowed in self.active_filters().items())),
                tuple(index for index, page in enumerate(document.pages)
                      if page.frame is not None))

    @staticmethod
    def _signed(item, row) -> tuple:
        return (item.uid, item.locked, _icon_for(item), tuple(row))

    def refresh(self, document, told: Optional[dict] = None) -> None:
        """The markups were edited: the list is built again only if that
        changed a row of it. A nudge or a drag moves markups without changing
        a word of their rows, and building four hundred rows again for it was
        a tenth of a second of every press of an arrow (QA, 2026-10-15).

        *told*: which markups the edit changed, {page id: markup ids} — just
        their rows are put in again (_patch)."""
        if told is not None and self._patch(document, told):
            return
        found = self.all_rows(document)
        if self._what_is_shown(document, found) != self._shown_before:
            self.rebuild(document)
            return
        # the same rows; only which markup each one is may have changed (an
        # undo puts back markups made afresh from its snapshot)
        self._items = {(index, item.uid): item for index, item, _row in found
                       if (index, item.uid) in self._items}
        self.totals.setText(self._totals_text(document))
        self.follow_the_canvas()
        self._dim_soon()

    def _dim_soon(self) -> None:
        if self._any_dimmed or self.filter.text().strip() or self.active_filters():
            self._dim_timer.start()

    def dim_filtered_now(self) -> int:
        """Dim on the page what the filter leaves out, and nothing else."""
        from . import filterdim
        self._dim_timer.stop()
        document = self.window.document
        filtered = self.filtered_out(document)
        changed = filterdim.apply(document, filtered)
        self._any_dimmed = bool(filtered)
        return changed

    def rebuild(self, document) -> None:
        self.filter_list.setIcon(icon("filter_list", 16))      # in the theme's ink
        needle = self.filter.text().strip().lower()
        grouping = self.group_by.currentData() or "Page"
        found = self.all_rows(document)
        self._shown_before = self._what_is_shown(document, found)
        self._echoing = True
        sorting = self.tree.isSortingEnabled()
        self.tree.setSortingEnabled(False)
        self.tree.clear()
        self._items = {}
        self._nodes = {}
        rows = []
        column = self.COLUMNS.index(grouping) if grouping in self.COLUMNS else None
        groups: dict = {}
        order: list = []
        if grouping == "Page":
            for index, page in enumerate(document.pages):
                if page.frame is not None:
                    order.append(f"Page {index + 1}")
        for index, item, row in found:
            if not self._shown(row, needle):
                continue
            node = self._node_for(index, item, row)
            self._items[(index, item.uid)] = item
            self._nodes[(index, item.uid)] = node
            if column is None:
                self.tree.addTopLevelItem(node)
            else:
                key = f"Page {index + 1}" if grouping == "Page" else (row[column] or "—")
                if key not in order:
                    order.append(key)
                groups.setdefault(key, []).append(node)
            rows.append(row)
        for key in order:
            children = groups.get(key, [])
            if not children:
                continue           # a page with no markups is not listed (Revu)
            parent = self._heading(key)
            if grouping == "Page":
                parent.setData(0, self.PAGE_ROLE, int(key.split()[-1]) - 1)
            parent.addChildren(children)
            self.tree.addTopLevelItem(parent)
            parent.setExpanded(True)
        for place in range(len(self.COLUMNS)):
            self.tree.resizeColumnToContents(place)
        self.tree.setSortingEnabled(sorting)
        self._rows = rows
        self.totals.setText(self._totals_text(document))
        self._echoing = False
        self.follow_the_canvas()
        self._dim_soon()

    #: where a page heading keeps the index of its page
    PAGE_ROLE = Qt.UserRole + 1
    #: most markups one change may touch and still be put in row by row
    PATCH_MOST = 60

    def _node_for(self, index: int, item, row: list) -> "_MarkupRow":
        node = _MarkupRow(row)
        node.row = row
        node.setData(0, Qt.UserRole, (index, item.uid))
        node.setIcon(1, icon(_icon_for(item), 16))
        node.setFlags(node.flags() | Qt.ItemIsEditable)
        for place, colour in ((self.COLUMNS.index("Colour"), item.style.stroke),
                              (self.COLUMNS.index("Fill"), item.style.fill)):
            if colour:
                node.setIcon(place, _swatch(colour))
        if item.locked:
            node.setForeground(1, QColor("#8b93a1"))
        return node

    def _heading(self, key: str) -> "_MarkupRow":
        parent = _MarkupRow([key] + [""] * (len(self.COLUMNS) - 1))
        font = parent.font(0)
        font.setBold(True)
        parent.setFont(0, font)
        parent.setFlags(parent.flags() & ~Qt.ItemIsSelectable)
        return parent

    def _patch(self, document, told: dict) -> bool:
        """Put the markups an edit changed into the list as they are now,
        row by row — {page id: markup ids}, from the edit's undo step.

        Building the list again, or reading every markup's row to find that
        nothing else changed, is in proportion to every markup in the file:
        on a set of a thousand that was a tenth of a second of every markup
        placed, every Escape and every undo (the user, 2026-10-21). False when
        the list is better built again: grouped by a column, more than a few
        rows, never built yet — or not in step with the pages before the edit
        (markups come or gone that the edit does not account for).
        """
        shown = self._shown_before
        if shown is None or not getattr(self, "_nodes", None) and not shown[1]:
            return False
        if shown[0] != self._heading_of_what_is_shown(document):
            return False
        if sum(len(uids) for uids in told.values()) > self.PATCH_MOST:
            return False
        grouping = self.group_by.currentData() or "Page"
        if grouping not in ("Page", "None"):
            return False
        pages = {page.uid: index for index, page in enumerate(document.pages)}
        if any(uid not in pages or document.pages[pages[uid]].frame is None for uid in told):
            return False
        changed = {pages[uid]: set(uids) for uid, uids in told.items()}
        # in step: each page has the markups the list last read of it, but
        # for those the edit says it changed (counted, for the other pages —
        # nothing of their rows is read)
        orders = {}
        for index, page in enumerate(document.pages):
            if page.frame is None:
                continue
            listed = shown[1].get(index, ())
            if index not in changed:
                count = sum(1 for item in page.frame.markups()
                            if not getattr(item, "from_drawing", False)
                            and not getattr(item, "IS_CALC", False))
                if count != len(listed):
                    return False
                continue
            order = {}
            for item in page.frame.ordered_markups():
                if not getattr(item, "from_drawing", False) \
                        and not getattr(item, "IS_CALC", False):
                    order[item.uid] = (len(order), item)
            if not (set(order) ^ {entry[0] for entry in listed}) <= changed[index]:
                return False
            orders[index] = order
        if not told:
            # announced again, with nothing more changed
            self.totals.setText(self._totals_text(document))
            self.follow_the_canvas()
            return True
        needle = self.filter.text().strip().lower()
        sorting = self.tree.isSortingEnabled()
        column = self.tree.sortColumn() if sorting else 0
        descending = sorting and self.tree.header().sortIndicatorOrder() == Qt.DescendingOrder
        self._echoing = True
        try:
            for index, uids in changed.items():
                order = orders[index]
                rows = {}
                for uid in uids:
                    rows[uid] = self._patch_row(index, uid, order, needle, grouping,
                                                column, sorting, descending)
                # this page's rows as a reading of the whole list would give
                # them: those changed afresh, the rest as they were
                before = {entry[0]: entry for entry in shown[1].get(index, ())}
                signed = []
                for uid, (_reading, item) in order.items():
                    entry = before.get(uid) if uid not in rows else None
                    if entry is None:
                        row = rows.get(uid) or self.row_for(index, item)
                        entry = self._signed(item, row)
                    signed.append(entry)
                if signed:
                    shown[1][index] = tuple(signed)
                else:
                    shown[1].pop(index, None)
            if grouping == "Page":
                for position in reversed(range(self.tree.topLevelItemCount())):
                    if not self.tree.topLevelItem(position).childCount():
                        self.tree.takeTopLevelItem(position)   # (Revu lists no empty page)
            for place in range(len(self.COLUMNS)):
                self.tree.resizeColumnToContents(place)
            self._rows = [node.row for node in self._nodes.values()]
        finally:
            self._echoing = False
        self._shown_before = shown
        self.totals.setText(self._totals_text(document))
        self.follow_the_canvas()
        self._dim_soon()
        return True

    def _patch_row(self, index, uid, order, needle, grouping, column, sorting,
                   descending) -> None:
        """One markup's row taken out, and put back as it is now."""
        key = (index, uid)
        old = self._nodes.pop(key, None)
        self._items.pop(key, None)
        if old is not None:
            holder = old.parent()
            if holder is not None:
                holder.removeChild(old)
            else:
                self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(old))
        found = order.get(uid)
        if found is None:
            return None                                # gone
        reading, item = found
        row = self.row_for(index, item)
        if not self._shown(row, needle):
            return row
        node = self._node_for(index, item, row)
        self._items[key] = item
        self._nodes[key] = node
        wanted = _natural_key(row[column])

        def before(other) -> bool:
            # where a fresh build puts it: by the sorted column, and in
            # reading order among rows that sort alike
            data = other.data(0, Qt.UserRole)
            theirs = _natural_key(other.text(column))
            if sorting and theirs != wanted:
                return theirs > wanted if descending else theirs < wanted
            if not data:
                return False
            if data[0] != index:
                return data[0] < index
            mine = order.get(data[1])
            return mine is not None and mine[0] < reading

        if grouping == "None":
            place = sum(1 for at in range(self.tree.topLevelItemCount())
                        if before(self.tree.topLevelItem(at)))
            self.tree.insertTopLevelItem(place, node)
            return row
        heading = None
        for at in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(at)
            if top.data(0, self.PAGE_ROLE) == index:
                heading = top
                break
        if heading is None:
            heading = self._heading(f"Page {index + 1}")
            heading.setData(0, self.PAGE_ROLE, index)
            wanted_heading = _natural_key(heading.text(column))

            def heading_before(other) -> bool:
                theirs = _natural_key(other.text(column))
                if sorting and theirs != wanted_heading:
                    return theirs > wanted_heading if descending else theirs < wanted_heading
                page = other.data(0, self.PAGE_ROLE)
                return page is not None and page < index
            place = sum(1 for at in range(self.tree.topLevelItemCount())
                        if heading_before(self.tree.topLevelItem(at)))
            self.tree.insertTopLevelItem(place, heading)
            heading.setExpanded(True)
        place = sum(1 for at in range(heading.childCount()) if before(heading.child(at)))
        heading.insertChild(place, node)
        return row

    # -- column filters ----------------------------------------------------
    def filter_menu(self, column: int, where=None):
        """A tick-list of the values in *column*; unticked ones are hidden."""
        if column < 0:
            return None
        values = sorted({row[column] for _i, _m, row in
                         self.all_rows(self.window.document)})
        allowed = self.column_filters.get(column, set(values))
        menu = QMenu(self)
        menu.setProperty("cf_data", True)          # the column's values: data, not commands
        menu.setTitle(f"Filter {self.COLUMNS[column]}")
        every = menu.addAction("(All)")
        every.triggered.connect(lambda: self.set_column_filter(column, None))
        menu.addSeparator()
        for value in values:
            action = menu.addAction(value or "(blank)")
            action.setCheckable(True)
            action.setChecked(value in allowed)
            if self.COLUMNS[column] in ("Colour", "Fill") and value.startswith("#"):
                action.setIcon(_swatch(value))
            action.toggled.connect(
                lambda on, v=value: self._toggle_value(column, v, on, values))
        if where is not None:
            menu.popup(where)
        return menu

    def _toggle_value(self, column: int, value: str, on: bool, values) -> None:
        allowed = set(self.column_filters.get(column, set(values)))
        (allowed.add if on else allowed.discard)(value)
        self.set_column_filter(column, None if allowed >= set(values) else allowed)

    def set_column_filter(self, column: int, allowed) -> None:
        if allowed is None:
            self.column_filters.pop(column, None)
        else:
            self.column_filters[column] = set(allowed)
        # the heading's funnel turns blue while its column is filtered
        self.tree.header().viewport().update()
        self.rebuild(self.window.document)

    def _clear_column_filters(self) -> None:
        for column in list(self.column_filters):
            self.set_column_filter(column, None)

    # -- totals ------------------------------------------------------------
    @staticmethod
    def _totals_text(document) -> str:
        """Group measurement values and count markers, the way a takeoff does."""
        from collections import defaultdict
        lengths = defaultdict(list)
        counts = defaultdict(int)
        for page in document.pages:
            if page.frame is None:
                continue
            for item in page.frame.markups():
                if isinstance(item, CountItem):
                    counts[item.subject] += 1
                elif isinstance(item, MeasureItem) and item.value is not None:
                    lengths[item.subject].append(item.value)
        parts = []
        for subject, values in sorted(lengths.items()):
            try:
                total = values[0]
                for value in values[1:]:
                    total = total + value
                parts.append(f"{subject}: {format_quantity(total, 4)} ({len(values)})")
            except Exception:
                parts.append(f"{subject}: {len(values)} items")
        for subject, number in sorted(counts.items()):
            parts.append(f"{subject}: {number}")
        return "  •  ".join(parts) if parts else "No measurements yet."

    # -- selection ---------------------------------------------------------
    def selected_keys(self) -> list:
        keys = []
        for node in self.tree.selectedItems():
            data = node.data(0, Qt.UserRole)
            if data:
                keys.append(tuple(data))
        return keys

    def selected_markups(self) -> list:
        return [self._items[key] for key in self.selected_keys() if key in self._items]

    def _activate(self, node: QTreeWidgetItem, _column: int) -> None:
        data = node.data(0, Qt.UserRole)
        if data:
            self.markupActivated.emit(data[0], data[1])

    # -- editing in place (Revu: click a picked row's cell, or F2) -----------
    def editable_at(self, index):
        """(page index, uid, column name) when the list's cell at model
        *index* can be edited in place, else None."""
        if not index.isValid():
            return None
        name = self.COLUMNS[index.column()] if index.column() < len(self.COLUMNS) else ""
        if name not in self.EDITABLE:
            return None
        data = index.siblingAtColumn(0).data(Qt.UserRole)
        if not data or tuple(data) not in self._items:
            return None
        item = self._items[tuple(data)]
        if getattr(item, "locked", False):
            return None                # a locked markup is not changed (Revu)
        return data[0], data[1], name

    def cell_text(self, page: int, uid: str, column: str) -> str:
        """What a cell's box starts with: the whole of it, on one line."""
        item = self._items.get((page, uid))
        if item is None:
            return ""
        if column == "Comment":
            return _flat(self._comment_source(item))
        return getattr(item, self.EDITABLE[column], "") or ""

    @staticmethod
    def _comment_source(item) -> str:
        """The words the Comment column shows: the markup's comment, or a
        text box's or callout's own words when it has none (_comment_of)."""
        if getattr(item, "comment", ""):
            return item.comment
        if hasattr(item, "doc"):
            return item.text()
        return ""

    def set_cell(self, page: int, uid: str, column: str, text: str) -> bool:
        """Put *text* into a markup's cell, as one step Ctrl+Z takes back.
        True when the markup changed."""
        import shiboken6
        item = self._items.get((page, uid))
        if not shiboken6.isValid(self) or item is None or not shiboken6.isValid(item) \
                or column not in self.EDITABLE or item.scene() is None:
            return False               # the markup went while its cell was open
        frame = item.parentItem()
        if column == "Comment":
            words = item.text() if not getattr(item, "comment", "") and hasattr(item, "doc") \
                else None
            before = self._comment_source(item)
            if _flat(before) == text:
                return False
        else:
            text = text.strip()
            if (getattr(item, self.EDITABLE[column], "") or "") == text:
                return False
        view = self.window.view
        view.begin_snapshot([frame] if frame is not None else view.all_frames())
        if column != "Comment":
            setattr(item, self.EDITABLE[column], text)
        elif words is not None:
            self._splice_words(item, words, text)
        else:
            # the rest of the comment's line breaks are kept
            start, end, put = _spliced(_flat(before), text)
            item.comment = before[:start] + put + before[end:]
        item.touch()
        item.update()
        view.commit_snapshot(f"Edit {column}")
        self.window.refresh_lists()
        self._reselect([(page, uid)])
        return True

    @staticmethod
    def _splice_words(item, words: str, text: str) -> None:
        """A text box's (callout's) words changed to *text*: only the part
        typed over is replaced, so the rest keeps its line breaks, bold and
        colours."""
        from PySide6.QtGui import QTextCursor
        start, end, put = _spliced(_flat(words), text)
        cursor = QTextCursor(item.doc)
        cursor.beginEditBlock()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        cursor.insertText(put)
        cursor.endEditBlock()
        if _flat(item.text()) != text:      # the document's places were not its words'
            item.set_text(text)
        item.written = item.text()

    def eventFilter(self, watched, event) -> bool:             # noqa: N802
        """F2 on the list edits the current cell, as Revu's (and any list
        on Windows); no shortcut elsewhere takes it first."""
        if watched is self.tree and event.type() == QEvent.ShortcutOverride \
                and event.key() == Qt.Key_F2 and event.modifiers() == Qt.NoModifier:
            event.accept()
            return True
        return super().eventFilter(watched, event)

    def _picked(self) -> None:
        """Picking rows picks those markups on the page — all of them."""
        if self._echoing:
            return
        keys = self.selected_keys()
        if len(keys) == 1:
            self.markupPicked.emit(*keys[0])
        elif keys:
            self.markupsPicked.emit(keys)

    def follow_the_canvas(self) -> None:
        """Pick out the rows for whatever is selected on the page.

        The list and the drawing are two views of one thing, so picking a
        markup on either should show it on the other.
        """
        scene = self.window.view.scene() if self.window.view else None
        wanted = {item.uid for item in scene.selectedItems()} if scene else set()
        self._echoing = True
        try:
            if self._nodes and self._follow_only_the_changes(wanted):
                return
            first = None
            for index in range(self.tree.topLevelItemCount()):
                top = self.tree.topLevelItem(index)
                nodes = [top] + [top.child(c) for c in range(top.childCount())]
                for node in nodes:
                    data = node.data(0, Qt.UserRole)
                    if not data:
                        continue
                    chosen = data[1] in wanted
                    if node.isSelected() != chosen:
                        # only the ones that change: telling Qt again for
                        # four hundred rows was a tenth of a second
                        node.setSelected(chosen)
                    if chosen and first is None:
                        first = node
            if first is not None:
                # up or down to the row only: a click on a row's Comment cell
                # threw the list back to its first column, under the pointer
                # that was about to click the cell again to edit it
                across = self.tree.horizontalScrollBar().value()
                self.tree.scrollToItem(first)
                self.tree.horizontalScrollBar().setValue(across)
        finally:
            self._echoing = False

    def _follow_only_the_changes(self, wanted: set) -> bool:
        """Pick out and let go of only the rows whose picking changes —
        found by the markup, not by going through every row of the list (a
        thousand rows, twice for every markup placed or picked)."""
        nodes = {key[1]: node for key, node in self._nodes.items()}
        if any(uid in wanted and node.treeWidget() is not self.tree
               for uid, node in nodes.items()):
            return False
        picked = set()
        for node in self.tree.selectedItems():
            data = node.data(0, Qt.UserRole)
            if not data:
                return False                       # (a heading picked: read it all)
            picked.add(data[1])
        for uid in wanted ^ picked:
            node = nodes.get(uid)
            if node is not None:
                node.setSelected(uid in wanted)
        chosen = [nodes[uid] for uid in wanted if uid in nodes]
        if chosen:
            first = min(chosen, key=self._place_in_the_list)
            across = self.tree.horizontalScrollBar().value()
            self.tree.scrollToItem(first)
            self.tree.horizontalScrollBar().setValue(across)
        return True

    def _place_in_the_list(self, node) -> tuple:
        parent = node.parent()
        if parent is None:
            return (self.tree.indexOfTopLevelItem(node), -1)
        return (self.tree.indexOfTopLevelItem(parent), parent.indexOfChild(node))

    # -- changing several at once -------------------------------------------
    def _row_menu(self, point) -> QMenu:
        menu = QMenu(self)
        menu.setProperty("cf_context", "markuprow")
        chosen = self.selected_markups()
        if not chosen:
            return menu
        menu.addAction(f"{len(chosen)} selected").setEnabled(False)
        menu.addAction("Colour…", lambda: self.batch_colour("stroke"))
        menu.addAction("Fill…", lambda: self.batch_colour("fill"))
        menu.addAction("No fill", lambda: self.batch_style(
            lambda style: setattr(style, "fill", ""), "Fill"))
        width = menu.addMenu("Width")
        for value in (0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0):
            width.addAction(f"{value:g} pt", lambda v=value: self.batch_style(
                lambda style: setattr(style, "width", v), "Line width"))
        lines = menu.addMenu("Line style")
        from ..items import linestyles
        for name in DASH_ARRAYS:
            lines.addAction(name, lambda n=name: self.batch_style(
                lambda style: linestyles.apply(style, n), "Line style"))
        size = menu.addMenu("Font size")
        for value in (6, 8, 10, 12, 14, 18, 24):
            size.addAction(f"{value} pt", lambda v=value: self.batch_style(
                lambda style: setattr(style, "font_size", float(v)), "Font size"))
        opacity = menu.addMenu("Opacity")
        for value in (100, 75, 50, 25):
            opacity.addAction(f"{value}%", lambda v=value: self.batch_style(
                lambda style: setattr(style, "opacity", v / 100.0), "Opacity"))
        menu.addSeparator()
        menu.addAction("Lock / unlock", self.batch_lock)
        menu.addAction("Hide", self.batch_hide)
        menu.addAction("Delete", self.batch_delete)
        if point is not None:
            menu.popup(self.tree.viewport().mapToGlobal(point))
        return menu

    def batch_colour(self, field: str) -> None:
        from PySide6.QtGui import QCursor
        from .colorpicker import choose
        chosen = self.selected_markups()
        if not chosen:
            return
        colour = choose(QCursor.pos(), getattr(chosen[0].style, field) or "#e03131",
                        allow_none=(field != "stroke"), parent=self)
        if colour is None:
            return
        self.batch_style(lambda style: setattr(style, field, colour),
                         "Colour" if field == "stroke" else "Fill")

    def _change(self, description: str, change) -> None:
        chosen = self.selected_markups()
        if not chosen:
            return
        view = self.window.view
        keys = self.selected_keys()
        view.begin_snapshot(view.all_frames())
        for item in chosen:
            change(item)
        view.commit_snapshot(f"{description} ({len(chosen)})")
        self.window.refresh_lists()
        self._reselect(keys)

    def batch_style(self, mutate, description: str) -> None:
        def change(item):
            mutate(item.style)
            if hasattr(item, "apply_style"):
                item.apply_style()
            item.touch()
            item.update()
        self._change(description, change)

    def batch_lock(self) -> None:
        chosen = self.selected_markups()
        locking = not all(item.locked for item in chosen)

        def change(item):
            item.locked = locking
            item.update()
        self._change("Lock" if locking else "Unlock", change)

    def batch_hide(self) -> None:
        def change(item):
            item.hidden = True
            item.setSelected(False)
            item.setVisible(False)
        self._change("Hide", change)

    def batch_delete(self) -> None:
        from .scene import detach
        self._change("Delete", detach)

    def _reselect(self, keys) -> None:
        wanted = {uid for _page, uid in keys}
        self._echoing = True
        try:
            for index in range(self.tree.topLevelItemCount()):
                top = self.tree.topLevelItem(index)
                for node in [top] + [top.child(c) for c in range(top.childCount())]:
                    data = node.data(0, Qt.UserRole)
                    node.setSelected(bool(data) and data[1] in wanted)
        finally:
            self._echoing = False

    def export_csv(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "Export markups", "markups.csv",
                                              "CSV files (*.csv)")
        if not path:
            return
        from . import saving

        def write(target):
            with open(target, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(self.COLUMNS)
                writer.writerows(getattr(self, "_rows", []))
        # as every save: why it couldn't be, Try Again or Save As… (it raised)
        done = saving.write_until_done(self.window, path, write, "Export markups",
                                       "CSV files (*.csv)")
        if done is not None:
            self.window.status_hint.setText(f"Saved {done[0]}")


_SWATCHES: dict = {}


def _swatch(colour: str) -> QIcon:
    """A colour's square, made once for each colour."""
    found = _SWATCHES.get(colour)
    if found is not None:
        return found

    def draw(painter: QPainter) -> None:
        painter.fillRect(QRectF(0, 0, 12, 12), QColor(colour))
    found = _SWATCHES[colour] = drawn_icon(draw, 12, 12)
    return found


def _icon_for(item) -> str:
    if isinstance(item, MeasureItem):
        return "measure_length"
    if isinstance(item, CountItem):
        return "count"
    if isinstance(item, StampItem):
        return "stamp"
    if isinstance(item, NoteItem):
        return "note"
    if isinstance(item, CalloutItem):
        return "cloud" if item.shape_kind == "cloud" else "callout"
    if isinstance(item, TextItem):
        return "text"
    if isinstance(item, RectItem):
        if getattr(item, "to_scale", False):
            return "sketch_ellipse" if item.kind == "ellipse" else "sketch_rect"
        return {"ellipse": "ellipse", "cloud": "cloud", "highlight": "highlight"}.get(
            item.kind, "rect")
    if isinstance(item, PolyItem):
        return {"ink": "pen", "highlighter": "highlighter", "arrow": "arrow",
                "polygon": "polygon", "cloud": "cloud"}.get(item.kind, "line")
    return "select"


# ---------------------------------------------------------------------------
# Bookmarks
# ---------------------------------------------------------------------------

class BookmarksPanel(QWidget):
    """Named places in the document, in page order.

    The same list the contents block prints and the exported PDF gets as its
    outline, so what you navigate by and what a reader navigates by are the
    same thing.
    """

    bookmarkActivated = Signal(int, float)

    def __init__(self, window):
        super().__init__()
        self.window = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Bookmark", "Page"])
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.itemDoubleClicked.connect(self._activate)
        layout.addWidget(self.tree, 1)

        from .widgets import FlowLayout
        buttons = FlowLayout()           # wraps when the panel is narrow
        self._needs_one = []
        for label, tip, slot in (
                ("Add", "Bookmark where you are now", self.add_here),
                ("Rename", "Rename the selected bookmark", self.rename),
                ("Delete", "Remove the selected bookmark", self.remove),
                ("Contents", "Put a table of contents on the page",
                 self.insert_contents)):
            button = QPushButton(label)
            button.setToolTip(tip)
            button.clicked.connect(slot)
            buttons.addWidget(button)
            if slot in (self.rename, self.remove):
                self._needs_one.append(button)
        layout.addLayout(buttons)
        # Rename and Delete want a bookmark picked out (F-36: they were
        # offered with an empty list)
        self.tree.currentItemChanged.connect(lambda *_: self._enable())
        self._enable()

    def _enable(self) -> None:
        for button in self._needs_one:
            button.setEnabled(self.tree.currentItem() is not None)

    # -- display -----------------------------------------------------------
    def rebuild(self, document=None) -> None:
        document = document or self.window.document
        # built again after a bookmark is added, renamed or deleted here: the
        # list stays scrolled where it was, the row picked where it was
        # (the user, 2026-10-20)
        kept = KeptPlace(self.tree, self)
        current = self.tree.currentItem()
        row = self.tree.indexOfTopLevelItem(current) if current is not None else -1
        self.tree.clear()
        for mark, index in document.contents_entries():
            node = QTreeWidgetItem([("    " * mark.level) + mark.title,
                                    str(index + 1)])
            node.setData(0, Qt.UserRole, mark)
            self.tree.addTopLevelItem(node)
        if row >= 0 and self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(
                min(row, self.tree.topLevelItemCount() - 1)))
        kept.restore()
        self._enable()

    def _selected(self):
        node = self.tree.currentItem()
        return node.data(0, Qt.UserRole) if node is not None else None

    def _activate(self, node, _column: int = 0) -> None:
        mark = node.data(0, Qt.UserRole)
        if mark is None:
            return
        index = self.window.document.page_index_of(mark.page_uid)
        if index >= 0:
            self.bookmarkActivated.emit(index, mark.y)

    # -- editing -----------------------------------------------------------
    def add_here(self) -> None:
        self.window.add_bookmark_here()

    def rename(self) -> None:
        mark = self._selected()
        if mark is None:
            return
        title, accepted = QInputDialog.getText(self, "Rename bookmark",
                                               "Name", text=mark.title)
        if accepted and title.strip():
            self.window.change_bookmarks(
                "Rename bookmark", lambda: setattr(mark, "title", title.strip()))

    def remove(self) -> None:
        mark = self._selected()
        if mark is None:
            return
        self.window.change_bookmarks(
            "Delete bookmark", lambda: self.window.document.bookmarks.remove(mark))

    def insert_contents(self) -> None:
        self.window.insert_contents_block()


#: Revu's ways of showing a tool set: pictures in a grid, one line each, or
#: a picture with its name and what it is.
SYMBOL, LIST, DETAIL = "symbol", "list", "detail"
VIEW_NAMES = {SYMBOL: "Symbol", LIST: "List", DETAIL: "Detail"}


def _kind_name(payload: dict) -> str:
    """What a kept tool is, in the words the tool bar uses."""
    from . import toolsets
    from .tools import TOOLS
    if payload.get("type") == toolsets.GROUP:
        return f"Group of {len(payload.get('items', []))}"
    kind = str(payload.get("kind") or payload.get("type") or "")
    tool = next((t for t in TOOLS if t.key == kind), None)
    return tool.label if tool is not None else kind.replace("_", " ").title()


class _ToolRowDelegate(QStyledItemDelegate):
    """A tool's row in List view (a small picture and its name) and in Detail
    view (its picture, its name and, under it, what it is and how it comes
    down). Set headers are drawn by their own bar."""

    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel

    def _mode(self, index):
        return index.data(ToolSetsPanel.VIEW_ROLE)

    def sizeHint(self, option, index):
        mode = self._mode(index)
        if mode == LIST:
            return QSize(option.rect.width(), 24)
        if mode == DETAIL:
            return QSize(option.rect.width(), max(self.panel.tool_size + 10, 40))
        return super().sizeHint(option, index)

    def paint(self, painter, option, index):
        mode = self._mode(index)
        if index.data(ToolSetsPanel.ENTRY_ROLE) == -1:
            return                        # a set's row: its own bar draws it
        if mode not in (LIST, DETAIL):
            super().paint(painter, option, index)
            return
        from PySide6.QtWidgets import QStyle
        painter.save()
        rect = option.rect
        palette = option.palette
        if option.state & QStyle.State_Selected:
            painter.fillRect(rect, palette.highlight())
            ink = palette.highlightedText().color()
        else:
            if option.state & QStyle.State_MouseOver:
                painter.fillRect(rect, palette.alternateBase())
            ink = palette.text().color()
        side = 18 if mode == LIST else self.panel.tool_size
        picture = index.data(Qt.DecorationRole)
        box = QRect(rect.left() + 6, rect.top() + (rect.height() - side) // 2, side, side)
        # on Revu's light tile, as in Symbol view: line work drawn in dark
        # colours is lost on the dark panel otherwise
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#e4e5e6"))
        painter.drawRoundedRect(QRectF(box.adjusted(-2, -2, 2, 2)), 3, 3)
        if isinstance(picture, QIcon):
            picture.paint(painter, box)
        text_left = box.right() + 8
        label = str(index.data(ToolSetsPanel.LABEL_ROLE) or index.data(Qt.DisplayRole) or "")
        font = QFont(option.font)
        painter.setPen(ink)
        if mode == LIST:
            painter.setFont(font)
            painter.drawText(QRect(text_left, rect.top(), rect.right() - text_left - 4,
                                   rect.height()), Qt.AlignVCenter | Qt.AlignLeft,
                             option.fontMetrics.elidedText(label, Qt.ElideRight,
                                                           rect.right() - text_left - 4))
        else:
            half = rect.height() // 2
            font.setBold(True)
            painter.setFont(font)
            width = rect.right() - text_left - 4
            painter.drawText(QRect(text_left, rect.top() + 2, width, half - 2),
                             Qt.AlignBottom | Qt.AlignLeft,
                             QFontMetrics(font).elidedText(label, Qt.ElideRight, width))
            small = QFont(option.font)
            small.setPointSizeF(max(option.font.pointSizeF() - 1.0, 6.0))
            painter.setFont(small)
            faded = QColor(ink)
            faded.setAlphaF(0.65)
            painter.setPen(faded)
            painter.drawText(QRect(text_left, rect.top() + half + 1, width, half - 3),
                             Qt.AlignTop | Qt.AlignLeft,
                             QFontMetrics(small).elidedText(
                                 str(index.data(ToolSetsPanel.DESC_ROLE) or ""),
                                 Qt.ElideRight, width))
        painter.restore()


class _ToolGrid(QListWidget):
    """A tool set's tools as Bluebeam's Symbol view shows them: a grid of
    pictures, the first nine of My Tools numbered for their keys."""

    def __init__(self, panel, group_name: str):
        super().__init__()
        self.panel = panel
        self.group_name = group_name
        self.setObjectName("toolGrid")
        self.setViewMode(QListView.IconMode)
        self.setMovement(QListView.Static)
        self.setResizeMode(QListView.Adjust)
        self.setWrapping(True)
        self.setSpacing(3)
        self.setFrameShape(QListWidget.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.itemClicked.connect(self._clicked)

    def _clicked(self, item) -> None:
        self.panel.select_entry(self.group_name, item.data(Qt.UserRole))
        self.panel.use_selected()

    def _menu(self, point) -> None:
        item = self.itemAt(point)
        if item is not None:
            self.panel.select_entry(self.group_name, item.data(Qt.UserRole))
        else:
            self.panel.select_set(self.group_name)
        self.panel.build_menu().exec(self.viewport().mapToGlobal(point))

    def cell(self) -> int:
        return self.iconSize().width() + 10

    def fit(self, width: int) -> bool:
        """Tall enough for every row of tools at *width*, no taller. Whether
        the height changed."""
        cell = self.cell()
        self.setGridSize(QSize(cell, cell))
        inner = max(width - 2 * self.frameWidth() - 2, cell)
        per_row = max(1, inner // cell)
        rows = max(1, -(-self.count() // per_row)) if self.count() else 1
        height = rows * cell + 2 * self.frameWidth() + 4
        if height == self.height() and self.minimumHeight() == height:
            return False
        self.setFixedHeight(height)
        return True

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # laid out at its real width: as many rows as that needs (sized to a
        # guess before the panel had its width, a set of seven showed three)
        if event.size().width() != event.oldSize().width() and self.fit(event.size().width()):
            header = self.parentWidget()
            if isinstance(header, _SetHeader):
                QTimer.singleShot(0, header, header.sync)


class _SetHeader(QWidget):
    """A tool set's bar, as Bluebeam's: the chevron that rolls it up, its
    name, its gear (the set's own menu) — and, in Symbol view, its tools."""

    def __init__(self, panel, header_item, group, symbols: bool):
        super().__init__()
        self.panel = panel
        self.item = header_item
        self.group_name = group.name
        self.setObjectName("toolSetHeader")
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        bar = self.bar = QWidget()
        bar.setObjectName("toolSetBar")
        line = QHBoxLayout(bar)
        line.setContentsMargins(4, 2, 2, 2)
        line.setSpacing(4)
        self.chevron = QToolButton()
        self.chevron.setObjectName("toolSetChevron")
        self.chevron.setProperty("cf_data", True)     # one set's: not a command of its own
        self.chevron.setAutoRaise(True)
        self.chevron.clicked.connect(self._toggle)
        line.addWidget(self.chevron)
        self.title = QLabel(f"{group.name}  ({len(group.entries)})")
        self.title.setObjectName("toolSetName")
        line.addWidget(self.title, 1)
        self.gear = QToolButton()
        self.gear.setObjectName("toolSetGear")
        self.gear.setProperty("cf_data", True)        # its menu's entries are the commands
        self.gear.setAutoRaise(True)
        self.gear.setIcon(icon("gear", 16))
        self.gear.setToolTip(f"“{group.name}”: its view, its tools, its name")
        self.gear.setPopupMode(QToolButton.InstantPopup)
        self.gear.clicked.connect(self._gear)
        line.addWidget(self.gear)
        column.addWidget(bar)
        self.grid = None
        if symbols:
            self.grid = _ToolGrid(panel, group.name)
            side = panel.tool_size
            self.grid.setIconSize(QSize(side, side))
            from . import toolsets
            numbered = group.name == toolsets.MY_TOOLS
            for position, entry in enumerate(group.entries):
                picture = entry_thumbnail(entry, side, side)
                if numbered and position < 9:
                    _badge(picture, str(position + 1))
                tool = QListWidgetItem(QIcon(picture), "")
                tool.setToolTip(entry.label)
                tool.setData(Qt.UserRole, position)
                self.grid.addItem(tool)
            column.addWidget(self.grid)
        self.sync()

    def sync(self) -> None:
        import shiboken6
        if not (shiboken6.isValid(self) and shiboken6.isValid(self.item)):
            return                    # the chest was rebuilt in the meantime
        open_ = self.item.isExpanded()
        self.chevron.setArrowType(Qt.DownArrow if open_ else Qt.RightArrow)
        height = self.bar.sizeHint().height()
        if self.grid is not None:
            shown = open_ and self.grid.count() > 0
            self.grid.setVisible(shown)
            self.grid.fit(self.panel.tree.viewport().width())
            if shown:
                height += self.grid.height()
        if self.item.sizeHint(0).height() != height:
            self.item.setSizeHint(0, QSize(10, height))

    def _toggle(self) -> None:
        self.item.setExpanded(not self.item.isExpanded())
        self.sync()

    def _gear(self) -> None:
        self.panel.select_set(self.group_name)
        self.panel.build_set_menu().exec(self.gear.mapToGlobal(self.gear.rect().bottomLeft()))


def _badge(picture, text: str) -> None:
    """Bluebeam's little number on a My Tools tool: the key that picks it up."""
    from PySide6.QtGui import QPainter
    painter = QPainter(picture)
    painter.setRenderHint(QPainter.Antialiasing, True)
    size = max(9, picture.width() // 3)
    box = QRectF(picture.width() - size, 0, size, size)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#3c3e40"))
    painter.drawRect(box)
    font = painter.font()
    font.setPixelSize(max(7, size - 3))
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(box, Qt.AlignCenter, text)
    painter.end()


class ToolSetsPanel(QWidget):
    """Bluebeam's tool chest: every set you have, all showing at once.

    Bluebeam does not make you choose a set before you can see what is in it —
    the sets stack down the panel, each one named, each one able to be rolled
    up when it is in the way. That is what this is. Steel sections, weld
    symbols and review stamps can all be on screen together, and the one you
    want is the one you can see.

    Clicking a tool picks it up: it goes on the pointer and the next click on
    the page puts it down. Everything else — renaming, removing, starting a
    set, importing one, and whether a tool comes back as a copy or as a set of
    properties to draw again with — is on the right-click menu, where it is
    out of the way until it is wanted.
    """

    SET_ROLE = Qt.UserRole + 1          # which set a row belongs to
    ENTRY_ROLE = Qt.UserRole + 2        # which tool within it, or -1 for the set
    VIEW_ROLE = Qt.UserRole + 3         # the set's view: List or Detail rows
    LABEL_ROLE = Qt.UserRole + 4        # the tool's name, as the row shows it
    DESC_ROLE = Qt.UserRole + 5         # what it is and how it comes down

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.groups: list = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        from ..settings import app_settings
        # Bluebeam's tool size slider, and which sets are in Detail view
        self.tool_size = int(app_settings().value("toolchest/size", 32) or 32)
        import json
        try:
            self.views = dict(json.loads(app_settings().value("toolchest/views", "") or "{}"))
        except (ValueError, TypeError):
            self.views = {}
        for name in app_settings().value("toolchest/detail", []) or []:
            self.views.setdefault(name, DETAIL)         # kept from before List
        self.clipboard = None                           # a tool copied, to paste

        # Bluebeam's "Tool Chest ▾": the sets, and making or bringing in one
        self.chest_button = QToolButton()
        self.chest_button.setProperty("cf_data", True)   # its menu's entries are the commands
        self.chest_button.setObjectName("toolChestMenu")
        self.chest_button.setText("Tool Sets ▾")
        self.chest_button.setPopupMode(QToolButton.InstantPopup)
        self.chest_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.chest_button.clicked.connect(self._chest_menu)
        layout.addWidget(self.chest_button)

        self.tree = QTreeWidget()
        self.tree.setObjectName("toolChestTree")
        self.tree.setHeaderHidden(True)
        self.tree.setIconSize(QSize(48, 34))
        self.tree.setRootIsDecorated(False)
        self.tree.setIndentation(8)
        self.tree.setUniformRowHeights(False)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setDragDropMode(QAbstractItemView.InternalMove)
        self.tree.setDefaultDropAction(Qt.MoveAction)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu_at)
        self.tree.itemClicked.connect(self._clicked)
        self.tree.itemDoubleClicked.connect(lambda *_: self.use_selected())
        self.tree.currentItemChanged.connect(lambda *_: self.refresh_buttons())
        self.tree.model().rowsMoved.connect(self._rows_moved)
        # the sets as wide as the panel, however wide it is made (a gap down
        # the right of every set, 2026-10-14)
        # (set by hand on every resize: a hidden header does not stretch its
        # one column again once a scroll bar has come and gone)
        self.tree.header().setStretchLastSection(False)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tree.setMouseTracking(True)
        self.tree.setItemDelegate(_ToolRowDelegate(self))
        self.tree.viewport().installEventFilter(self)
        layout.addWidget(self.tree, 1)

        self.hint = QLabel("")
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color:#6b7280;")
        layout.addWidget(self.hint)

        from PySide6.QtWidgets import QSlider
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setObjectName("toolSize")
        self.size_slider.setRange(20, 64)
        self.size_slider.setValue(self.tool_size)
        self.size_slider.setToolTip("How big the tools are drawn")
        self.size_slider.valueChanged.connect(self._resize_tools)
        layout.addWidget(self.size_slider)

        # Kept so the rest of the window can ask about the state of a tool
        # without knowing how the panel is laid out.
        self.entry_buttons: dict = {}
        self.rebuild()

    # -- building ----------------------------------------------------------
    def rebuild(self, keep: str = "") -> None:
        """Read every set back and redraw the whole chest."""
        from . import toolsets

        wanted = keep or self.current_set_name()
        rolled = self.rolled_up()
        # built again for a change made here (a tool's mode, the tool size):
        # where it was scrolled, the focus kept; a set asked for is shown
        kept = KeptPlace(self.tree, self) if not keep else None
        self.groups = toolsets.load_toolsets()
        self.tree.blockSignals(True)
        self.tree.clear()
        self.headers: dict = {}
        for group in self.groups:
            header = QTreeWidgetItem([f"{group.name}  ({len(group.entries)})"])
            header.setData(0, self.SET_ROLE, group.name)
            header.setData(0, self.ENTRY_ROLE, -1)
            header.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            font = header.font(0)
            font.setBold(True)
            header.setFont(0, font)
            header.setForeground(0, QColor(0, 0, 0, 0))   # the bar says it
            self.tree.addTopLevelItem(header)
            self._fill(header, group)
            header.setExpanded(group.name not in rolled)
            view = self.view_of(group.name)
            symbols = view == SYMBOL
            for index in range(header.childCount()):
                child = header.child(index)
                child.setHidden(symbols)                  # Symbol view: the grid instead
                child.setData(0, self.VIEW_ROLE, view)
            bar = _SetHeader(self, header, group, symbols)
            self.tree.setItemWidget(header, 0, bar)
            self.headers[group.name] = bar
            header.setHidden(group.hidden)     # unticked in Manage Tool Sets
        if all(group.hidden for group in self.groups):
            # not an empty chest with nothing to say (F-36): how to get the
            # sets back
            note = QTreeWidgetItem(["Every tool set is hidden — tick one in the "
                                    "Tool Chest menu, or Manage Tool Sets…"
                                    if self.groups else
                                    "No tool sets yet — New Tool Set… in the Tool Chest menu"])
            note.setFlags(Qt.ItemIsEnabled)
            note.setData(0, self.ENTRY_ROLE, -2)
            note.setForeground(0, QColor("#868e96"))
            note.setToolTip(0, "The Tool Chest menu is the gear at the top of this panel")
            self.tree.addTopLevelItem(note)
        self.tree.blockSignals(False)
        if not getattr(self, "_watching_expansion", False):
            self.tree.itemExpanded.connect(self._sync_header)
            self.tree.itemCollapsed.connect(self._sync_header)
            self._watching_expansion = True
        if kept is not None:
            header = self.header_for(wanted) if wanted else None
            if header is not None and self.tree.currentItem() is None:
                self.tree.setCurrentItem(header)
            self.fit_width()
            kept.restore()
        elif wanted:
            self.show_set(wanted)
            self.fit_width()
        self.refresh_buttons()

    def _fill(self, header, group) -> None:
        from . import toolsets

        numbered = group.name == toolsets.MY_TOOLS
        for position, entry in enumerate(group.entries):
            prefix = f"{position + 1}.  " if numbered and position < 9 else ""
            mode_tag = "  · Property" if entry.mode == toolsets.PROPERTIES else ""
            row = QTreeWidgetItem([f"{prefix}{entry.label}{mode_tag}"])
            row.setIcon(0, QIcon(entry_thumbnail(entry)))
            row.setData(0, self.LABEL_ROLE, f"{prefix}{entry.label}")
            how = ("Properties Mode" if entry.mode == toolsets.PROPERTIES
                   else "Drawing Mode" + (" · Scale" if entry.scaled else ""))
            row.setData(0, self.DESC_ROLE, f"{_kind_name(entry.payload)} · {how}")
            row.setData(0, self.SET_ROLE, group.name)
            row.setData(0, self.ENTRY_ROLE, position)
            row.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
            row.setToolTip(0,
                           "Put back exactly what was added" if entry.mode == toolsets.COPY
                           else "Draw a new one with these properties")
            header.addChild(row)

    def rolled_up(self) -> set:
        """The sets that are currently collapsed, so a rebuild keeps them so."""
        closed = set()
        for index in range(self.tree.topLevelItemCount()):
            header = self.tree.topLevelItem(index)
            if not header.isExpanded():
                closed.add(header.data(0, self.SET_ROLE))
        return closed

    # -- what is selected --------------------------------------------------
    def current_set_name(self) -> str:
        row = self.tree.currentItem()
        return row.data(0, self.SET_ROLE) if row is not None else ""

    def current_set(self):
        name = self.current_set_name()
        return next((g for g in self.groups if g.name == name), None)

    def current_entry(self):
        row = self.tree.currentItem()
        group = self.current_set()
        if row is None or group is None:
            return None
        index = row.data(0, self.ENTRY_ROLE)
        if index is None or index < 0 or index >= len(group.entries):
            return None
        return group.entries[index]

    def header_for(self, name: str):
        for index in range(self.tree.topLevelItemCount()):
            header = self.tree.topLevelItem(index)
            if header.data(0, self.SET_ROLE) == name:
                return header
        return None

    def show_set(self, name: str) -> None:
        """Put the cursor back on a set, leaving it rolled up if it was."""
        header = self.header_for(name)
        if header is None:
            return
        if self.tree.currentItem() is None:
            self.tree.setCurrentItem(header)
        self.tree.scrollToItem(header)

    def select_set(self, name: str) -> None:
        """Open a set and put the cursor on it — for one just made or brought in."""
        header = self.header_for(name)
        if header is None:
            return
        header.setExpanded(True)
        self.tree.setCurrentItem(header)
        self.tree.scrollToItem(header)

    def select_entry(self, set_name: str, index: int) -> None:
        header = self.header_for(set_name)
        if header is not None and 0 <= index < header.childCount():
            header.setExpanded(True)
            self.tree.setCurrentItem(header.child(index))

    def refresh_buttons(self) -> None:
        """Say what clicking would do, in the line under the chest."""
        from . import toolsets

        entry = self.current_entry()
        group = self.current_set()
        if entry is None:
            self.hint.setText(
                "Right-click for a new set, or to bring one in from Bluebeam"
                if group is None else
                "Click a tool to pick it up · right-click for more")
            return
        numbered = group is not None and group.name == toolsets.MY_TOOLS
        how = ("comes back exactly as it was" if entry.mode == toolsets.COPY
               else "draws a new one with its properties")
        extra = " · the first nine are on the number keys" if numbered else ""
        self.hint.setText(f"“{entry.label}” {how}{extra}")

    # -- using a tool ------------------------------------------------------
    def _clicked(self, row, _column) -> None:
        """One click picks the tool up, so the next click on the page puts it down."""
        if row is None or row.data(0, self.ENTRY_ROLE) in (None, -1, -2):
            return
        self.use_selected()

    def use_selected(self) -> None:
        entry = self.current_entry()
        if entry is not None:
            from .widgets import focus_kept
            with focus_kept(unless=self.window.view):    # the chest keeps the keys
                self.window.use_tool_entry(entry)

    def add_selection(self) -> None:
        self.window.add_to_toolset(None, into=self.current_set_name())

    def toggle_mode(self) -> None:
        from . import toolsets

        entry = self.current_entry()
        group = self.current_set()
        if entry is None or not toolsets.can_be_properties(entry.payload):
            return
        entry.mode = (toolsets.PROPERTIES if entry.mode == toolsets.COPY
                      else toolsets.COPY)
        index = group.entries.index(entry)
        self._store()
        self.select_entry(group.name, index)

    def set_mode(self, mode: str) -> None:
        """Revu's Drawing Mode (put down exactly) or Properties Mode (draw
        a fresh one with its look)."""
        from . import toolsets
        entry, group = self.current_entry(), self.current_set()
        if entry is None or entry.mode == mode:
            return
        if mode == toolsets.PROPERTIES and not toolsets.can_be_properties(entry.payload):
            return
        entry.mode = mode
        index = group.entries.index(entry)
        self._store()
        self.select_entry(group.name, index)

    def toggle_scale(self) -> None:
        entry, group = self.current_entry(), self.current_set()
        if entry is None:
            return
        entry.scaled = not entry.scaled
        index = group.entries.index(entry)
        self._store()
        self.select_entry(group.name, index)

    def move_entry(self, step: int) -> None:
        entry, group = self.current_entry(), self.current_set()
        if entry is None:
            return
        index = group.entries.index(entry)
        target = index + step
        if not 0 <= target < len(group.entries):
            return
        group.entries[index], group.entries[target] = group.entries[target], group.entries[index]
        self._store()
        self.select_entry(group.name, target)

    def copy_entry(self) -> None:
        from copy import deepcopy
        entry = self.current_entry()
        if entry is not None:
            self.clipboard = deepcopy(entry)

    def paste_entry(self) -> None:
        from copy import deepcopy
        group = self.current_set()
        if group is None or self.clipboard is None:
            return
        group.entries.append(deepcopy(self.clipboard))
        self._store()
        self.select_entry(group.name, len(group.entries) - 1)

    def rename_entry(self) -> None:
        entry = self.current_entry()
        group = self.current_set()
        if entry is None:
            return
        name, accepted = QInputDialog.getText(self, "Rename tool", "Name",
                                              text=entry.label)
        if accepted and name.strip():
            index = group.entries.index(entry)
            entry.label = name.strip()
            self._store()
            self.select_entry(group.name, index)

    def remove_entry(self) -> None:
        entry = self.current_entry()
        group = self.current_set()
        if entry is None or group is None:
            return
        group.entries.remove(entry)
        self._store()

    # -- the sets ----------------------------------------------------------
    def new_set(self) -> None:
        from . import toolsets

        name, accepted = QInputDialog.getText(self, "New tool set", "Name")
        name = name.strip()
        if not accepted or not name:
            return
        if any(group.name == name for group in self.groups):
            QMessageBox.information(self, "New tool set",
                                    f"There is already a set called “{name}”.")
            return
        self.groups.append(toolsets.ToolSet(name))
        toolsets.save_toolsets(self.groups)
        self.rebuild(keep=name)
        self.select_set(name)

    def rename_set(self) -> None:
        from . import toolsets

        group = self.current_set()
        if group is None or group.name == toolsets.MY_TOOLS:
            QMessageBox.information(self, "Rename", "My Tools keeps its name.")
            return
        name, accepted = QInputDialog.getText(self, "Rename tool set", "Name",
                                              text=group.name)
        if accepted and name.strip():
            group.name = name.strip()
            toolsets.save_toolsets(self.groups)
            self.rebuild(keep=group.name)

    def delete_set(self) -> None:
        from . import toolsets

        group = self.current_set()
        if group is None or group.name == toolsets.MY_TOOLS:
            QMessageBox.information(self, "Delete", "My Tools is always there.")
            return
        if QMessageBox.question(self, "Delete tool set",
                                f"Delete “{group.name}” and its "
                                f"{len(group.entries)} tool(s)?") != QMessageBox.Yes:
            return
        self.groups.remove(group)
        toolsets.save_toolsets(self.groups)
        self.rebuild()

    def import_set(self) -> None:
        self.window.import_toolset()

    # -- Bluebeam's menus and views ---------------------------------------
    def _sync_header(self, item) -> None:
        bar = self.headers.get(item.data(0, self.SET_ROLE)) if hasattr(self, "headers") else None
        if bar is not None:
            bar.sync()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        for bar in getattr(self, "headers", {}).values():
            bar.sync()

    def _resize_tools(self, value: int) -> None:
        from ..settings import app_settings
        self.tool_size = int(value)
        app_settings().setValue("toolchest/size", self.tool_size)
        self.rebuild()

    def view_of(self, name: str) -> str:
        return self.views.get(name, SYMBOL)

    def set_view(self, name: str, view: str) -> None:
        """Revu's Symbol, List or Detail view for one set."""
        import json
        from ..settings import app_settings
        if view == SYMBOL:
            self.views.pop(name, None)
        else:
            self.views[name] = view
        app_settings().setValue("toolchest/views", json.dumps(self.views))
        app_settings().remove("toolchest/detail")
        self.rebuild(keep=name)

    def set_detail(self, name: str, detail: bool) -> None:
        self.set_view(name, DETAIL if detail else SYMBOL)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.tree.viewport() and event.type() == QEvent.Resize:
            self.fit_width()
        return super().eventFilter(watched, event)

    def fit_width(self) -> None:
        """Every set as wide as the panel, and each grid as tall as its tools."""
        width = self.tree.viewport().width()
        if self.tree.columnWidth(0) != width:
            self.tree.setColumnWidth(0, width)
        for bar in getattr(self, "headers", {}).values():
            bar.sync()

    def build_set_menu(self) -> QMenu:
        """A set's gear: Symbol, List or Detail, and what the right-click offers."""
        menu = QMenu(self)
        menu.setProperty("cf_context", "chesttool")
        group = self.current_set()
        if group is not None:
            for view in (SYMBOL, LIST, DETAIL):
                shown = menu.addAction(VIEW_NAMES[view],
                                       lambda _c=False, n=group.name, v=view: self.set_view(n, v))
                shown.setCheckable(True)
                shown.setChecked(self.view_of(group.name) == view)
            menu.addSeparator()
        for action in self.build_menu().actions():
            action.setParent(menu)
            menu.addAction(action)
        return menu

    def build_chest_menu(self) -> QMenu:
        """Revu's Tool Chest menu: a tick for each set the chest shows, then
        managing, making and bringing in sets."""
        menu = QMenu(self)
        menu.setProperty("cf_context", "chest")
        for group in self.groups:
            shown = menu.addAction(group.name)
            shown.setProperty("cf_data", True)     # a set's name: data, not a command
            shown.setCheckable(True)
            shown.setChecked(not group.hidden)
            shown.toggled.connect(lambda on, n=group.name: self.set_shown(n, on))
        menu.addSeparator()
        menu.addAction("Manage Tool Sets…", self.window.manage_toolsets)
        menu.addAction("New Tool Set…", self.new_set)
        menu.addAction("Import Tool Set…", self.import_set)
        return menu

    def _chest_menu(self) -> None:
        self.build_chest_menu().exec(
            self.chest_button.mapToGlobal(self.chest_button.rect().bottomLeft()))

    def set_shown(self, name: str, shown: bool) -> None:
        """Show a set in the chest, or keep it without showing it."""
        from . import toolsets

        group = next((g for g in self.groups if g.name == name), None)
        if group is None or group.hidden == (not shown):
            return
        group.hidden = not shown
        toolsets.save_toolsets(self.groups)
        self.rebuild()
        if shown:
            self.select_set(name)

    # -- the right-click menu ----------------------------------------------
    def _menu_at(self, point) -> None:
        row = self.tree.itemAt(point)
        if row is not None:
            self.tree.setCurrentItem(row)
        self.build_menu().exec(self.tree.viewport().mapToGlobal(point))

    def build_menu(self) -> QMenu:
        """Everything that used to be a row of buttons."""
        from . import toolsets

        menu = QMenu(self)
        menu.setProperty("cf_context", "chesttool")
        entry = self.current_entry()
        group = self.current_set()
        if entry is not None:
            menu.addAction("Use Tool", self.use_selected)
            menu.addSeparator()
            # Revu's two modes, one ticked
            exact = menu.addAction("Drawing Mode", lambda: self.set_mode(toolsets.COPY))
            exact.setCheckable(True)
            exact.setChecked(entry.mode == toolsets.COPY)
            exact.setToolTip("Put the markup down exactly as it was kept")
            draw = menu.addAction("Properties Mode", lambda: self.set_mode(toolsets.PROPERTIES))
            draw.setCheckable(True)
            draw.setChecked(entry.mode == toolsets.PROPERTIES)
            draw.setEnabled(toolsets.can_be_properties(entry.payload))
            draw.setToolTip("Draw a fresh markup using this stored style")
            if not draw.isEnabled():
                draw.setToolTip("This one only makes sense put back as it was")
            scale = menu.addAction("Scale", self.toggle_scale)
            scale.setCheckable(True)
            scale.setChecked(entry.scaled)
            scale.setEnabled(entry.mode == toolsets.COPY and bool(entry.mm_per_pt))
            scale.setToolTip("Keep its real size on a page of another scale"
                             if scale.isEnabled() else
                             "Kept from a page with no scale, or drawn fresh: "
                             "nothing to scale it from")
            menu.addSeparator()
            group_entries = group.entries if group is not None else []
            index = group_entries.index(entry) if entry in group_entries else -1
            up = menu.addAction("Move Up", lambda: self.move_entry(-1))
            up.setEnabled(index > 0)
            down = menu.addAction("Move Down", lambda: self.move_entry(1))
            down.setEnabled(0 <= index < len(group_entries) - 1)
            menu.addAction("Copy", self.copy_entry)
            menu.addSeparator()
            menu.addAction("Rename…", self.rename_entry)
            menu.addAction("Remove", self.remove_entry)
            menu.addSeparator()
        if group is not None:
            paste = menu.addAction("Paste", self.paste_entry)
            paste.setEnabled(self.clipboard is not None)
            paste.setToolTip(f"Put the copied tool in “{group.name}”")
            add = menu.addAction("Add Selection", self.add_selection)
            add.setToolTip(f"Keep what is selected on the page in “{group.name}”")
            rename = menu.addAction("Rename Tool Set…", self.rename_set)
            rename.setToolTip(f"Rename “{group.name}”")
            delete = menu.addAction("Delete Tool Set", self.delete_set)
            delete.setToolTip(f"Delete “{group.name}” and everything in it")
            menu.addSeparator()
        menu.addAction("New Tool Set…", self.new_set)
        imported = menu.addAction("Import Tool Set…", self.import_set)
        imported.setToolTip("Import a Bluebeam tool set (.btx) as a new set")
        return menu

    # -- order -------------------------------------------------------------
    def _rows_moved(self, parent, start, _end, destination, row) -> None:
        """A tool dragged up or down changes the order its set keeps it in."""
        from . import toolsets

        source = self.tree.itemFromIndex(parent) if parent.isValid() else None
        target = self.tree.itemFromIndex(destination) if destination.isValid() else None
        if source is None or target is None or source is not target:
            # Dragged from one set into another: rebuild from what the tree
            # now shows rather than trying to work out what moved where.
            self._reorder_from_tree()
            return
        group = next((g for g in self.groups
                      if g.name == source.data(0, self.SET_ROLE)), None)
        if group is None or not (0 <= start < len(group.entries)):
            return
        landing = row - 1 if row > start else row
        entry = group.entries.pop(start)
        group.entries.insert(max(0, min(landing, len(group.entries))), entry)
        toolsets.save_toolsets(self.groups)
        self.rebuild()
        self.select_entry(group.name, landing)

    def _reorder_from_tree(self) -> None:
        """Take the order and the membership straight off the tree."""
        from . import toolsets

        by_name = {group.name: group for group in self.groups}
        old = {group.name: list(group.entries) for group in self.groups}
        for top in range(self.tree.topLevelItemCount()):
            header = self.tree.topLevelItem(top)
            group = by_name.get(header.data(0, self.SET_ROLE))
            if group is None:
                continue
            entries = []
            for index in range(header.childCount()):
                child = header.child(index)
                came_from = old.get(child.data(0, self.SET_ROLE), [])
                position = child.data(0, self.ENTRY_ROLE)
                if position is not None and 0 <= position < len(came_from):
                    entries.append(came_from[position])
            group.entries = entries
        toolsets.save_toolsets(self.groups)
        self.rebuild()

    def _store(self) -> None:
        from . import toolsets

        toolsets.save_toolsets(self.groups)
        self.rebuild()


def _untinted(pixmap) -> QIcon:
    """A page thumbnail that stays readable when its row is the current one:
    the same picture for the selected state, so Qt doesn't wash it blue (the
    row's own highlight says which page is current)."""
    # a thin grey edge, as Bluebeam's thumbnails have: a blank page is white
    # on the white list and otherwise can't be seen at all
    framed = QPixmap(pixmap)
    from PySide6.QtGui import QPainter
    painter = QPainter(framed)
    painter.setPen(QColor("#a6abb2"))
    painter.drawRect(0, 0, framed.width() - 1, framed.height() - 1)
    painter.end()
    icon = QIcon()
    for mode in (QIcon.Normal, QIcon.Selected, QIcon.Active):
        icon.addPixmap(framed, mode)
    return icon


def entry_thumbnail(entry, width: int = 48, height: int = 34,
                    max_scale: float = 1.6) -> QPixmap:
    """Draw a tool set entry as the thing it actually is.

    A row that says "Rectangle (properties)" tells you nothing you can pick out
    of a list of eleven rectangles. A small picture of the markup — in its own
    colours, with its own line thickness, with its own words in it — tells you
    everything at a glance. An entry kept as properties has no contents to
    draw, so it is drawn as a plain example of that kind of markup wearing the
    properties that were stored.
    """
    from ..items.base import build_item
    from . import toolsets

    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.transparent)
    payload = entry.payload
    parts = (payload.get("items") or []) if payload.get("type") == toolsets.GROUP \
        else [payload]
    items = []
    for data in parts:
        try:
            item = build_item(dict(data))
        except Exception:
            item = None
        if item is None:
            continue
        if entry.mode == toolsets.PROPERTIES:
            _fill_example(item)
        items.append(item)
    if not items:
        return icon(_icon_for_type(entry.type_name), max(width, height)).pixmap(
            width, height)

    bounds = QRectF()
    for item in items:
        rect = item.local_rect().translated(item.pos())
        bounds = rect if bounds.isNull() else bounds.united(rect)
    if bounds.width() <= 0 or bounds.height() <= 0:
        bounds = QRectF(bounds.left(), bounds.top(), max(bounds.width(), 10.0),
                        max(bounds.height(), 10.0))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    margin = 3.0
    scale = min((width - 2 * margin) / bounds.width(),
                (height - 2 * margin) / bounds.height(), max_scale)
    painter.translate(width / 2, height / 2)
    painter.scale(scale, scale)
    painter.translate(-bounds.center())
    for item in items:
        painter.save()
        painter.translate(item.pos())
        try:
            item.paint_visible(painter)
        except Exception:
            pass
        painter.restore()
    painter.end()
    for item in items:
        item.setParentItem(None)
    return pixmap


def _fill_example(item) -> None:
    """Give a properties-only entry something to show.

    There is nothing in it — that is the point of the mode — so it is drawn as
    a plain example of its kind: a box of the right shape, a couple of words,
    a line. The colours, thickness and font are the stored ones, which are
    what the entry is really about.
    """
    if hasattr(item, "set_text") and not (item.text() if hasattr(item, "text") else ""):
        item.set_text("Aa")
    if hasattr(item, "points") and len(getattr(item, "points", [])) < 2:
        item.points = [QPointF(0, 18), QPointF(40, 0)]
    if hasattr(item, "set_local_rect") and item.local_rect().width() < 4:
        item.set_local_rect(QRectF(0, 0, 44, 26))


def _icon_for_type(type_name: str) -> str:
    """The tool icon that goes with a serialised markup's type."""
    return {"rect": "rect", "poly": "line", "text": "text", "callout": "callout",
            "checkbox": "checkbox",
            "note": "note", "stamp": "stamp", "image": "image",
            "measure": "measure_length",
            "count": "count", "contents": "page"}.get(type_name, "select")


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

class PropertySection(QGroupBox):
    """A section of Bluebeam's Properties panel — General, Appearance,
    Layout, Options…: its title with a chevron, open or folded by a click on
    it, and kept folded for the rest of the session."""

    folded: set = set()

    def __init__(self, title: str):
        super().__init__(title)
        self.setObjectName("propSection")
        self.setCheckable(True)
        # folded from its title with the mouse or Tab and Space; a click on a
        # button inside it (Add Option) leaves the focus where it was rather
        # than handing it to the section (the user, 2026-10-20)
        self.setFocusPolicy(Qt.TabFocus)
        self.setChecked(title not in PropertySection.folded)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(2, 2, 2, 6)
        self.body = QWidget()
        outer.addWidget(self.body)
        self.form = QFormLayout(self.body)
        self.form.setContentsMargins(4, 4, 4, 0)
        self.form.setHorizontalSpacing(8)
        self.form.setVerticalSpacing(5)
        self.form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.body.setVisible(self.isChecked())
        self.toggled.connect(self._fold)

    def _fold(self, on: bool) -> None:
        self.body.setVisible(on)
        if on:
            PropertySection.folded.discard(self.title())
        else:
            PropertySection.folded.add(self.title())


def _spin(value: float, low: float, high: float, decimals: int = 2, step: float = 1.0,
          suffix: str = "") -> QDoubleSpinBox:
    """A number as Bluebeam's panel shows one: right-aligned in its box."""
    box = QDoubleSpinBox()
    box.setRange(low, high)
    box.setDecimals(decimals)
    box.setSingleStep(step)
    box.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if suffix:
        box.setSuffix(suffix)
    box.setValue(value)
    return box


def _percent(fraction: float, name: str = "") -> QSpinBox:
    """An opacity, 0 to 100, as Bluebeam's."""
    box = QSpinBox()
    box.setRange(0, 100)
    box.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    box.setValue(int(round(float(fraction) * 100)))
    if name:
        box.setObjectName(name)
    return box


def _row(*widgets, stretch_first: bool = False) -> QWidget:
    holder = QWidget()
    line = QHBoxLayout(holder)
    line.setContentsMargins(0, 0, 0, 0)
    line.setSpacing(6)
    for n, widget in enumerate(widgets):
        line.addWidget(widget, 1 if (stretch_first and n == 0) else 0)
    if not stretch_first:
        line.addStretch(1)
    return holder


class PropertiesPanel(QScrollArea):
    """Context-sensitive editor for whatever is selected."""

    changed = Signal(str)

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setObjectName("propertiesPanel")     # the theme's Revu-style number boxes
        self.setFocusPolicy(Qt.TabFocus)          # (a click between controls keeps the focus)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._items: list[MarkupItem] = []
        self._building = False
        self._cells = None          # the Cells section's controls, while a table is open
        # A markup style being edited (markupstyles.py): its sample markup is
        # shown, and each change is handed back instead of being an undo step.
        self._style_edit = None
        self._style_title = ""
        self.body = QWidget()
        self.setWidget(self.body)
        self.layout = QVBoxLayout(self.body)
        self.layout.setSizeConstraint(QLayout.SetMinimumSize)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(8)
        self.show_items([])

    # -- construction ------------------------------------------------------
    def show_items(self, items: list[MarkupItem], style_edit=None) -> None:
        """Build the panel for *items*.

        Building it sends a few thousand events (each widget is made,
        polished, laid out), and every one of them used to pass through the
        application's event filters in Python on the way — twice the time of
        the building itself, and a click on a markup stalled for a tenth of
        a second (novice finding 25). Nothing typed or clicked can arrive
        while the panel is being built, so those filters stand aside for it."""
        application = QApplication.instance()
        window = self.window
        if (application is None or getattr(self, "_filters_aside", False)
                or getattr(window, "_presenting", None) is not None):
            # (the call within; or presenting, whose own key filter must keep
            # its place in front of the window's)
            self._show_items(items, style_edit)
            self._drop_the_unused_font_list()
            return
        filters = [watcher for watcher in (
            window if getattr(window, "_filters_the_application", False) else None,
            getattr(application, "_wheel_filter", None)) if watcher is not None]
        for watcher in filters:
            application.removeEventFilter(watcher)
        self._filters_aside = True
        try:
            self._show_items(items, style_edit)
            self._drop_the_unused_font_list()
        finally:
            self._filters_aside = False
            for watcher in filters:
                application.installEventFilter(watcher)

    def _show_items(self, items: list[MarkupItem], style_edit=None) -> None:
        wanted = [i for i in items if isinstance(i, MarkupItem)]
        # The same markups shown again — a change made here, or on the
        # toolbar, that the panel is built afresh for: it stays scrolled where
        # it was and the control in use keeps the focus (the user,
        # 2026-10-20: the Checkbox panel jumped to its top as an option was
        # ticked). Another selection starts at the top.
        same = bool(wanted) and len(wanted) == len(self._items) \
            and all(a is b for a, b in zip(wanted, self._items)) \
            and (style_edit is None) == (self._style_edit is None)
        self._kept = KeptPlace(self, self.body) if same else None
        self._items = wanted
        if not self._items and style_edit is None:
            styles = getattr(self.window, "markup_styles", None)
            held = styles.panel_sample() if styles is not None else None
            if held is not None:
                item, self._style_title, changed = held
                self.show_items([item], style_edit=changed)
                return
        self._style_edit = style_edit
        at_once = not self._building and self._may_take_apart_at_once()
        self._keep_the_font_list(at_once)
        self._building = True
        self._cells = None
        while self.layout.count():
            child = self.layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.hide()
                if at_once:
                    # Built again for a click or a key on the canvas: nothing
                    # of the old panel is part way through anything, so it is
                    # taken apart now. Given no parent first, every control
                    # in it had the application's style sheet worked out
                    # again — half the time of building the panel, on every
                    # markup placed or picked (the user, 2026-10-21).
                    shiboken6.delete(widget)
                    continue
                # Hide before unparenting, then unparent before deleting:
                # deleteLater() only runs on the next trip through the event
                # loop, so until then an old child would keep painting over its
                # replacement — and a *visible* widget given no parent becomes a
                # floating top-level window. (A control of the old panel may
                # be the one whose change is being shown: it has to outlive
                # the change.)
                widget.setParent(None)
                widget.deleteLater()
        if not self._items:
            hint = QLabel("Nothing selected.\n\nPick a markup on the page to edit its "
                          "appearance, or choose a tool to draw a new one.")
            hint.setWordWrap(True)
            hint.setStyleSheet("color:#6b7280;")
            self.layout.addWidget(hint)
            self._add_workbook(with_sheet=True)
            self.layout.addStretch(1)
            self._settle()
            self._building = False
            return

        first = self._items[0]
        # Bluebeam's heading: the markup's icon and "<Type> Properties"
        heading = QLabel(self._style_title if self._style_edit is not None
                         else f"{first.display_name()} Properties" if len(self._items) == 1
                         else f"{len(self._items)} Markups Properties")
        heading.setObjectName("propHeading")
        font = heading.font()
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() + 1.5)
        heading.setFont(font)
        self.layout.addWidget(heading)

        if self._style_edit is not None:
            # a style: how it looks, not what it is or where
            self._add_style_sections(first)
            return
        self._add_metadata(first)
        if all(getattr(i, "IS_CALC", False) and getattr(i, "region", None) is not None
               for i in self._items):
            self._add_equation(first)
        if all(getattr(i, "TYPE", "") == "calc_block" for i in self._items):
            self._add_block(first)
        if len(self._items) == 1 and getattr(first, "TYPE", "") in ("table", "sheet_run"):
            if getattr(first, "TYPE", "") == "sheet_run":
                # a worksheet: its workbook first, then itself (the user,
                # 2026-10-24: "a better property panel for workbook and
                # work sheets")
                self._add_workbook()
            self._add_table(first)
            if self.window.view.tables.item is first:
                # open for its cells: the selected cells' look, as the
                # Properties toolbar's table controls give it
                self._add_cells(first)
        if len(self._items) == 1 and getattr(first, "TYPE", "") == "chart":
            self._add_chart(first)
        appearance = common_capabilities(self._items)
        texts = all(getattr(i, "HAS_TEXT", False) or isinstance(i, (StampItem, CountItem, MeasureItem))
                    or getattr(i, "to_scale", False) for i in self._items)
        # line ends only where every markup has a line with two ends (Revu's):
        # not a closed shape, the pen or the highlighter
        ends = ARROW_SIZE in appearance
        if appearance - {"font"} or texts or ends:
            self._add_appearance(first, appearance)
            if ends:
                self._add_arrows(first)
            self._add_captions(self._group("Appearance"))
            if texts:
                self._add_text(first, compact=not getattr(first, "HAS_TEXT", False))
        if len(self._items) == 1:
            if isinstance(first, MeasureItem):
                self._add_measure(first)
            elif isinstance(first, CountItem):
                self._add_count(first)
            elif isinstance(first, StampItem):
                self._add_stamp(first)
            elif isinstance(first, ContentsItem):
                self._add_contents(first)
            elif getattr(first, "TYPE", "") == "checkbox":
                from . import checkboxes
                checkboxes.add_section(self, first)
            elif isinstance(first, NoteItem):
                self._add_note(first)
            elif isinstance(first, ImageItem):
                self._add_image(first)
            elif isinstance(first, SnapshotItem):
                form = self._group("Snapshot")
                keep = QCheckBox("Keep Ratio")
                keep.setChecked(first.keep_aspect)
                keep.toggled.connect(lambda on: self._apply(
                    lambda i: setattr(i, "keep_aspect", on), "Snapshot ratio"))
                form.addRow("", keep)
                form.addRow("Source Page:", QLabel(str(first.source_page)))
                colours = QPushButton("Colour Processing…")
                colours.clicked.connect(lambda: self.window.change_colors(first))
                form.addRow("", colours)
            elif isinstance(first, RectItem) and first.kind in ("rect", "ellipse"):
                self._add_size(first)
        if len(self._items) > 1 and any(getattr(i, "style", None) is not None
                                        for i in self._items):
            # Revu's Change Multiple Colors, in Appearance for a selection
            colours = QPushButton("Change Colours…")
            colours.setObjectName("changeMultipleColors")
            colours.setToolTip("Change one colour the selected markups use to another")
            colours.clicked.connect(lambda: self.window.change_multiple_colors(list(self._items)))
            self._group("Appearance").addRow("", colours)
        if len(self._items) == 1 and not getattr(first, "SHEET_RUN", False):
            # (a spreadsheet's cells are the page's: not placed, nor kept as a tool)
            self._add_geometry(first)
            if isinstance(first, PolyItem) and first.broken:
                self._add_breaks(first)
            self._add_defaults(first)
        self._fit_width()
        self.layout.addStretch(1)
        self._settle()
        self._building = False

    #: the Font list of the panel as last built, and what it was connected to
    _font_in_use = None
    #: that list, kept for the next panel (_keep_the_font_list)
    _font_kept = None

    def _keep_the_font_list(self, at_once: bool) -> None:
        """Take the Font list out of the panel about to be taken apart, to be
        used again: a font list reads every font on the computer as it is
        made — on a Windows machine with hundreds, the slowest control of
        the panel, made again for every markup picked or placed. Only when
        the panel is taken apart at once: otherwise its change may be what
        is being shown, and it goes with the rest."""
        held, self._font_in_use = self._font_in_use, None
        self._font_kept = None
        if held is None:
            return
        family, slot = held
        if not at_once or not shiboken6.isValid(family):
            return
        try:
            family.currentFontChanged.disconnect(slot)
        except (RuntimeError, TypeError):
            return
        family.hide()
        family.setParent(self)
        self._font_kept = family

    def _drop_the_unused_font_list(self) -> None:
        """A kept Font list the new panel had no use for goes now."""
        family, self._font_kept = self._font_kept, None
        if family is not None and shiboken6.isValid(family):
            shiboken6.delete(family)

    def _font_list(self) -> QFontComboBox:
        family, self._font_kept = self._font_kept, None
        if family is not None and shiboken6.isValid(family):
            family.show()
            return family
        return QFontComboBox()

    @staticmethod
    def _may_take_apart_at_once() -> bool:
        """Whether the panel's old controls can be deleted now: only while
        the canvas is handling a button or a key, or the window catches up of
        its own accord (view.clear_of_the_panels) — never from a control of
        the panel's own, still busy saying what changed."""
        from .view import is_clear_of_the_panels
        return is_clear_of_the_panels()

    def _add_style_sections(self, first) -> None:
        """Appearance, line ends and text: what a markup style is made of."""
        appearance = common_capabilities([first])
        texts = getattr(first, "HAS_TEXT", False) or isinstance(
            first, (StampItem, CountItem, MeasureItem)) or getattr(first, "to_scale", False)
        ends = ARROW_SIZE in appearance
        if appearance - {"font"} or texts or ends:
            self._add_appearance(first, appearance)
            if ends:
                self._add_arrows(first)
            self._add_captions(self._group("Appearance"))
            if texts:
                self._add_text(first, compact=not getattr(first, "HAS_TEXT", False))
        if getattr(first, "TYPE", "") == "checkbox":
            # a Checkbox style keeps its box, mark and Multiple Selection
            from . import checkboxes
            checkboxes.add_section(self, first, look_only=True)
        self._fit_width()
        self.layout.addStretch(1)
        self._settle()
        self._building = False

    def _fit_width(self) -> None:
        """Everything fits the panel's width, as Bluebeam's does: lists shrink
        to what they must show rather than pushing the panel sideways."""
        for combo in self.body.findChildren(QComboBox):
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(4)
            combo.setMinimumWidth(0)
        for edit in self.body.findChildren(QLineEdit):
            edit.setMinimumWidth(0)
        # A number typed in applies on Enter or on leaving the box, as Revu's
        # do: one undo step, and no half-typed value drawn on the way. The
        # arrows and the wheel still apply at once (F-06).
        for spin in self.body.findChildren(QAbstractSpinBox):
            spin.setKeyboardTracking(False)

    def _settle(self) -> None:
        """Re-lay-out the rebuilt form and scroll back to the top — or, for
        the same markups shown again, to where it was.

        Without this the scroll area keeps the geometry of the *previous*
        selection for one more event loop turn, which leaves the panel showing
        empty space below content that is no longer there.
        """
        for group in self.body.findChildren(QGroupBox):
            if group.layout() is not None:
                group.layout().activate()
            group.setMinimumHeight(group.sizeHint().height())
        self.layout.invalidate()
        self.layout.activate()
        # A resizable scroll area can shrink every group to the viewport
        # height, clipping spin boxes into thin strips. Keep the form's own
        # height and let the panel scroll instead.
        self.body.setMinimumHeight(self.layout.sizeHint().height())
        self.body.adjustSize()
        kept, self._kept = getattr(self, "_kept", None), None
        if kept is not None:
            kept.restore()
            return
        self.verticalScrollBar().setValue(0)
        self.horizontalScrollBar().setValue(0)

    def _group(self, title: str) -> QFormLayout:
        """A section of the panel, as Bluebeam's: its form to fill in. A
        section asked for twice (Appearance, then the text in it) is the one."""
        for section in self.body.findChildren(PropertySection):
            if section.title() == title and section.parent() is self.body:
                return section.form
        section = PropertySection(title)
        self.layout.addWidget(section)
        return section.form

    def _hatch_chosen(self, combo, style) -> None:
        """A pattern picked, or Manage… — which opens Hatch Patterns and leaves
        the markup's pattern as it was."""
        from .hatchpatterns import MANAGE
        if combo.currentData() == MANAGE:
            combo.blockSignals(True)
            combo.setCurrentIndex(hatch_index(combo, style.hatch))
            combo.blockSignals(False)
            QTimer.singleShot(0, self.window.manage_hatches)
            return
        self._apply(lambda i: setattr(i.style, "hatch", combo.currentData()), "Hatch")

    def _apply(self, setter, description: str, coalesce: bool = False) -> None:
        """Change every selected item, and record one undo step for it.

        *coalesce* is for the controls that send a value continuously — a
        slider being dragged, a spin box being held down. Those belong in the
        undo history as the one change they are, not as every value passed
        through on the way.
        """
        if self._building:
            return
        self._finish_typing()
        if self._style_edit is not None:
            # a markup style is settings, not part of the document's undo
            for item in self._items:
                setter(item)
                if hasattr(item, "apply_style"):
                    item.apply_style()
            self._style_edit(self._items[0])
            self.changed.emit(description)
            return
        self.window.view.begin_snapshot()
        for item in self._items:
            setter(item)
            item.touch()
            item.prepareGeometryChange()
            if hasattr(item, "apply_style"):
                item.apply_style()
            item.update()
        self.window.view.commit_snapshot(description, coalesce=coalesce)
        self.changed.emit(description)

    def _finish_typing(self) -> None:
        """An equation shown while it is typed in (mainwindow.panel_subjects)
        is left first, so its typing is a step of its own and the panel's
        change another; it stays picked, and shown."""
        calc = self.window.view.calc
        if self._style_edit is None and calc.editing() and calc.item in self._items:
            calc.leave()
            self._items = [i for i in self._items if i.scene() is not None]
            for item in self._items:
                item.setSelected(True)

    @staticmethod
    def _typing_run(field):
        """The undo run of typing into *field*.

        Every keystroke shows at once, but the typing is one undo step, as in
        Revu, however slowly it is typed (exercise round 1, F-06). Enter or
        leaving the field ends the run; the next typing there is a new step.
        """
        run = [object()]
        if isinstance(field, QLineEdit):
            field.editingFinished.connect(lambda: run.__setitem__(0, object()))
        return lambda: run[0]

    def _slide(self, setter, description: str) -> None:
        """A change from a slider or a spin box: part of one continuous run."""
        self._apply(setter, description, coalesce=True)

    def _add_equation(self, first) -> None:
        """Decision 20: an equation's settings, as on its right-click menu."""
        from ..calc.docsheet import sheet_for
        from . import calcmenu

        items = list(self._items)
        region = first.region

        def change(description, apply):
            if not self._building:
                calcmenu.change(self.window, items, description, apply, refresh=False)

        if region.plot is not None:
            form = self._group("Plot")
            for title, attr in (("Grid", "grid"), ("Axes", "axes"), ("Graph by points", "points")):
                box = QCheckBox(title)
                box.setChecked(getattr(region.plot, attr))
                box.toggled.connect(lambda on, a=attr, t=title: change(
                    t, lambda r: setattr(r.plot, a, on)))
                form.addRow("", box)
            more = QPushButton("Plot settings…")
            more.clicked.connect(lambda: calcmenu.plot_settings(self.window, first))
            form.addRow("", more)
            return
        if region.kind != "math":
            return
        import dataclasses
        worksheet = sheet_for(self.window.document).worksheet
        fmt = region.fmt or worksheet.format

        def set_fmt(**changes):
            def apply(r):
                made = dataclasses.replace(r.fmt or worksheet.format, **changes)
                r.fmt = None if made == worksheet.format else made
            return apply

        # the variable's own settings first, as on its right-click menu (the
        # user, 2026-10-16): Decimal Places, Significant Figures and Global
        form = self._group("Result")
        names = sorted(getattr(region, "defined_vars", ()) or ())
        if names:
            defines = QLabel(", ".join(names))
            defines.setObjectName("equationDefines")
            defines.setToolTip("The variables this equation defines (typed in the equation)")
            defines.setWordWrap(True)
            form.addRow("Variable:", defines)
        decimals = QSpinBox()
        decimals.setObjectName("equationDecimals")
        decimals.setRange(0, 15)
        decimals.setValue(fmt.decimals)
        decimals.valueChanged.connect(lambda n: change(
            f"Decimal places: {n}", set_fmt(decimals=n)))
        form.addRow("Decimal Places:", decimals)
        significant = QCheckBox("Significant Figures")
        significant.setObjectName("equationSignificant")
        significant.setToolTip("Decimal Places counts significant figures, not places "
                               "after the point")
        significant.setChecked(fmt.significant)
        significant.toggled.connect(lambda on: change(
            "Significant figures", set_fmt(significant=on)))
        form.addRow("", significant)
        # the menu's Global (the user, 2026-10-22: "read by later calc
        # section" was confusing)
        made_global = QCheckBox("Global")
        made_global.setObjectName("equationGlobal")
        made_global.setToolTip("Equations after a section break can use this too")
        made_global.setChecked(region.is_global)
        made_global.toggled.connect(lambda on: change(
            "Make global" if on else "Make local", lambda r: setattr(r, "is_global", on)))
        form.addRow("", made_global)
        zeros = QCheckBox("Trailing Zeros")
        zeros.setObjectName("equationTrailingZeros")
        zeros.setChecked(fmt.trailing_zeros)
        zeros.toggled.connect(lambda on: change("Trailing Zeros", set_fmt(trailing_zeros=on)))
        form.addRow("", zeros)
        threshold = QSpinBox()
        threshold.setObjectName("equationThreshold")
        threshold.setRange(0, 15)
        threshold.setValue(fmt.threshold)
        threshold.setToolTip("Exponential Threshold: longer numbers are shown with a "
                             "power of ten")
        threshold.valueChanged.connect(lambda n: change(
            f"Exponential threshold: {n}", set_fmt(threshold=n)))
        # the menu's words, on two lines if need be (the panel keeps its width)
        named = QLabel("Exponential Threshold:")
        named.setWordWrap(True)
        named.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        named.setMaximumWidth(QFontMetrics(named.font()).horizontalAdvance("Decimal Places:")
                              + 4)
        form.addRow(named, threshold)
        fractions = QComboBox()
        fractions.setObjectName("equationFractions")
        for key, title in (("decimal", "Decimal"), ("fraction", "Fraction"), ("auto", "Auto")):
            fractions.addItem(title, key)
        fractions.setCurrentIndex(max(fractions.findData(fmt.fractions), 0))
        fractions.currentIndexChanged.connect(lambda _i: change(
            "Fractions", set_fmt(fractions=fractions.currentData())))
        form.addRow("Fractions:", fractions)
        rounding = QComboBox()
        rounding.setObjectName("equationRounding")
        rounding.addItem("Half to Even", True)
        rounding.addItem("Away from Zero", False)
        rounding.setCurrentIndex(0 if fmt.half_even else 1)
        rounding.currentIndexChanged.connect(lambda _i: change(
            "Rounding", set_fmt(half_even=rounding.currentData())))
        form.addRow("Rounding:", rounding)
        if region.editor.evaluate:
            # SMath's unit placeholder after the result, typed here too
            from .unitbox import UnitField
            unit = UnitField(self._unit_words(region.editor.unit))
            unit.setObjectName("equationUnit")
            unit.setToolTip("Result Unit: the result is shown in it (kN, kN*m, MPa), as "
                            "typed into the placeholder after the result. Blank: as worked out")
            unit.editingFinished.connect(lambda: self._equation_unit(items, unit))
            form.addRow("Result Unit:", unit)
        default = QPushButton("Document default")
        default.setToolTip("Show the result as Preferences says, like the rest")
        default.clicked.connect(lambda: change("Result format: default",
                                               lambda r: setattr(r, "fmt", None)))
        form.addRow("", default)

        form = self._group("Equation")
        size = QDoubleSpinBox()
        size.setObjectName("equationFontSize")
        size.setRange(4, 72)
        size.setSuffix(" pt")
        size.setValue(region.font_size)
        size.valueChanged.connect(lambda value: change(
            "Font size", lambda r: setattr(r, "font_size", float(value))))
        form.addRow("Size:", size)
        colour = ColorButton(region.color, label="Colour")
        colour.colorChanged.connect(lambda value: change(
            "Colour", lambda r: setattr(r, "color", value or "#000000")))
        form.addRow("Colour:", colour)
        background = ColorButton(region.bg_color, label="Background")
        background.colorChanged.connect(lambda value: change(
            "Background", lambda r: setattr(r, "bg_color", value or "#ffffff")))
        form.addRow("Background:", background)
        for title, attr, on in (("Bold", "bold", region.bold),
                                ("Italic", "italic", region.italic),
                                ("Underline", "underline", region.underline),
                                ("Border", "border", region.border),
                                ("Display Input Data", "show_input", region.show_input),
                                ("Ignore Units", "ignore_units", region.ignore_units)):
            box = QCheckBox(title)
            box.setChecked(on)
            box.toggled.connect(lambda value, a=attr, t=title: change(
                t, lambda r: setattr(r, a, value)))
            form.addRow("", box)
        disabled = QCheckBox("Disable Evaluation")
        disabled.setChecked(not region.enabled)
        disabled.toggled.connect(lambda value: change(
            "Disable Evaluation", lambda r: setattr(r, "enabled", not value)))
        form.addRow("", disabled)
        from .condformat import open_equation_rules
        rules = QPushButton("Conditional Formatting…")
        rules.setObjectName("equationConditionalFormatting")
        rules.setToolTip("Colour the result by its value, as the right-click menu's")
        rules.clicked.connect(lambda: open_equation_rules(self.window, items))
        form.addRow("", rules)

    @staticmethod
    def _unit_words(row) -> str:
        """The result unit as typed in the panel: kN*m, without SMath's marks."""
        return "" if row.is_empty() else row.text().replace("'", "")

    def _equation_unit(self, items, box) -> None:
        """Result Unit typed in the panel: the unit placeholder after the
        result, as if typed there (SMath's), one undo step."""
        from ..calc.editor import Cursor
        from ..calc.engine.model import Row
        from . import calcmenu
        import re

        from ..calc.engine.units import is_unit
        text = box.unit_text()
        if self._building or self._unit_words(items[0].region.editor.unit) == text:
            return
        # as a unit comes into SMath's box from its list: 'kN, a unit's name
        # marked; a document's own unit (kip_s := 5'kN) stays a name
        typed = re.sub(r"(?<![\w'])([^\W\d][\w°]*)",
                       lambda m: ("'" if is_unit(m.group(1)) else "") + m.group(1), text)

        def apply(region):
            editor = region.editor
            history = (list(editor._undo), list(editor._redo))
            editor.unit = Row()
            editor._fix_parents(editor.unit)
            if typed:
                editor.set_cursor(editor.unit, 0)
                editor.type(typed)
            editor.cursor = Cursor(editor.root, len(editor.root))
            editor.in_unit = False
            editor._undo, editor._redo = history
            editor.version += 1
        calcmenu.change(self.window, items, "Result unit", apply, refresh=False)

    def _add_geometry(self, item) -> None:
        """Bluebeam's Layout: where it is, how big and which way it is
        turned, as numbers with the unit beside them — in the rulers' units
        (mm, cm, in, pt), measured from the top-left corner of the paper."""
        from ..items.shapes import PAPER_UNITS, paper_unit

        per_unit, unit_name, digits = PAPER_UNITS[paper_unit()]
        form = self._group("Layout")
        rect = item.local_rect().normalized()
        rows = [
            ("X:", item.pos().x(), lambda i, v: i.setPos(v, i.pos().y()), False),
            ("Y:", item.pos().y(), lambda i, v: i.setPos(i.pos().x(), v), False),
        ]
        if item.RESIZABLE and rect.width() > 0 and rect.height() > 0:
            # Revu's names: the size on the paper, not what it measures —
            # a measurement's own value is in its Measurement section, in
            # the page scale's units (novice finding 26, audit G2)
            rows += [
                ("Document Width:", rect.width(), self._set_width, True),
                ("Document Height:", rect.height(), self._set_height, True),
            ]
        smallest = 10.0 ** -digits
        reach = 20000.0 * (72.0 / 25.4) / per_unit        # 20 m of paper
        for label, value, setter, is_size in rows:
            box = _spin(value / per_unit, smallest if is_size else -reach, reach,
                        digits, 1.0)
            box.setObjectName("layout" + label.rstrip(":").split()[-1])
            box.setToolTip(f"{value:.1f} pt on the paper" if is_size else f"{value:.1f} pt")
            box.valueChanged.connect(
                lambda number, apply=setter:
                self._slide(lambda i: apply(i, number * per_unit),
                            "Position and size"))
            form.addRow(label, _row(box, QLabel(unit_name), stretch_first=True))

        if item.ROTATABLE:
            turn = _spin(item.rotation(), -360.0, 360.0, 1, 1.0)
            turn.setObjectName("layoutRotation")
            turn.setWrapping(True)
            turn.valueChanged.connect(lambda angle: self._slide(
                lambda i: i.set_item_rotation(angle), "Rotation"))
            form.addRow("Rotation:", _row(turn, QLabel("°"), stretch_first=True))

    @staticmethod
    def _set_width(item, points: float) -> None:
        rect = item.local_rect().normalized()
        item.set_local_rect(QRectF(rect.x(), rect.y(), max(points, 0.1),
                                   rect.height()))

    @staticmethod
    def _set_height(item, points: float) -> None:
        rect = item.local_rect().normalized()
        item.set_local_rect(QRectF(rect.x(), rect.y(), rect.width(),
                                   max(points, 0.1)))

    # -- sections ----------------------------------------------------------
    def _add_appearance(self, first: MarkupItem, controls: set[str]) -> None:
        """Bluebeam's Appearance section, in its order and with its names:
        Color, Fill Color (Highlight), Hatch and its Scale, Opacity, Fill
        Opacity, Line Width, Style, a cloud's Size and Invert. CalcForge's own
        (hatch opacity, dash spacing, corner radius) sit beside the setting
        they belong to."""
        form = self._group("Appearance")
        style = first.style

        if controls == {OPACITY}:
            opacity = _percent(style.opacity, "overallOpacity")
            opacity.valueChanged.connect(lambda value: self._slide(
                lambda i: setattr(i.style, "opacity", value / 100.0), "Opacity"))
            form.addRow("Opacity:", opacity)
            return

        if STROKE in controls:
            stroke = ColorButton(style.stroke, allow_none=True, label="Colour")
            stroke.colorChanged.connect(lambda colour: self._apply(
                lambda i: setattr(i.style, "stroke", colour), "Line colour"))
            form.addRow("Colour:", _row(stroke))

        if ARROW_SIZE in controls and FILL not in controls and all(
                takes_end_fill(i) for i in self._items):
            # Revu's Fill Color on a line: what its filled ends are filled with
            end_fill = ColorButton(style.end_fill_colour(), allow_none=True,
                                   label="Fill Colour")
            end_fill.setObjectName("lineEndFill")
            end_fill.setToolTip("Fill Colour: what the line's filled ends — Closed, Round, "
                                "Square, Diamond — are filled with")
            end_fill.colorChanged.connect(lambda colour: self._apply(
                lambda i: setattr(i.style, "end_fill", colour or "none"), "Line-end colour"))
            form.addRow("Fill Colour:", _row(end_fill))

        if FILL in controls:
            fill = ColorButton(style.fill, allow_none=True, label="Fill Colour")
            fill.colorChanged.connect(lambda colour: self._apply(
                lambda i: setattr(i.style, "fill", colour), "Fill colour"))
            highlight = QCheckBox("Highlight")
            highlight.setObjectName("fillHighlight")
            highlight.setToolTip("The fill and hatch let what is under them show "
                                 "through, as a highlighter does")
            highlight.setChecked(style.blend == "multiply")
            highlight.toggled.connect(lambda on: self._apply(
                lambda i: setattr(i.style, "blend", "multiply" if on else "normal"),
                "Highlight"))
            form.addRow("Fill Colour:", _row(fill, highlight))

        # A hatch over the fill: how a section reads as concrete or as steel.
        if HATCH in controls:
            # Revu's: closed, only the sample across the box; names in the list
            hatch = PatternCombo()
            hatch.setObjectName("hatchPattern")
            big_pattern_dropdown(hatch, QSize(76, 22))
            hatch.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            hatch_colour = style.hatch_color or style.stroke
            fill_hatch_combo(hatch, hatch_colour, style.hatch or "")
            hatch.currentIndexChanged.connect(lambda _index: self._hatch_chosen(hatch, style))
            hatch_ink = ColorButton(style.hatch_color, label="Hatch colour")
            hatch_ink.setObjectName("hatchColour")
            hatch_ink.setToolTip("The hatch pattern's line colour")
            hatch_ink.colorChanged.connect(lambda colour: self._apply(
                lambda i: setattr(i.style, "hatch_color", colour), "Hatch colour"))
            form.addRow("Hatch:", _row(hatch, hatch_ink, stretch_first=True))
            # Bluebeam's Scale: 100 is the pattern as drawn, 200 twice as big
            from .widgets import UnboundedSpin
            scale = UnboundedSpin()
            scale.setObjectName("hatchScale")
            scale.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            scale.setValue(style.hatch_scale * 100)
            scale.setToolTip("The hatch pattern's scale: 100 as drawn, 50 half, 200 twice")
            scale.valueChanged.connect(lambda value: self._apply(
                lambda i: setattr(i.style, "hatch_scale", value / 100.0), "Hatch scale",
                coalesce=True))
            form.addRow("Scale:", scale)

        if OPACITY in controls:
            opacity = _percent(style.opacity, "overallOpacity")
            opacity.setToolTip("The whole markup: line, fill and hatch together")
            opacity.valueChanged.connect(lambda value: self._slide(
                lambda i: setattr(i.style, "opacity", value / 100.0), "Opacity"))
            form.addRow("Opacity:", opacity)

        if FILL_OPACITY in controls:
            fill_opacity = _percent(style.fill_opacity, "fillOpacity")
            fill_opacity.setToolTip("How solid the fill is (not the line or the hatch)")
            fill_opacity.valueChanged.connect(lambda value: self._slide(
                lambda i: setattr(i.style, "fill_opacity", value / 100.0), "Fill opacity"))
            form.addRow("Fill Opacity:", fill_opacity)

        if HATCH in controls:
            hatch_opacity = _percent(getattr(style, "hatch_opacity", 1.0), "hatchOpacity")
            hatch_opacity.setToolTip("How solid the hatch lines are (not the fill or the line)")
            hatch_opacity.valueChanged.connect(lambda value: self._slide(
                lambda i: setattr(i.style, "hatch_opacity", value / 100.0), "Hatch opacity"))
            form.addRow("Hatch Opacity:", hatch_opacity)

        if WIDTH in controls:
            width = _spin(style.width, 0.0, 40.0, 2, 0.25)
            width.setObjectName("lineWidth")
            width.setToolTip("Line width, in points")
            width.valueChanged.connect(lambda value: self._slide(
                lambda i: setattr(i.style, "width", value), "Line width"))
            form.addRow("Line Width:", width)

        if DASH in controls:
            # Revu's Style: the line itself across the whole box, no name
            line_style = PatternCombo()
            line_style.setObjectName("lineStyle")
            big_pattern_dropdown(line_style, QSize(76, 22))
            line_style.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            fill_line_style_combo(line_style, style.stroke, style.width, style.line_style,
                                  cloud=CLOUD in controls)
            line_style.currentIndexChanged.connect(
                lambda _index: self._line_style_chosen(line_style, style))
            form.addRow("Style:", line_style)
            spacing = _spin(style.dash_scale, 0.1, 50.0, 2, 0.25)
            spacing.setObjectName("dashSpacing")
            spacing.setPrefix("× ")
            spacing.setToolTip("How long the dashes, dots and gaps are — the "
                               "line's width does not change them")
            spacing.valueChanged.connect(lambda value: self._slide(
                lambda i: setattr(i.style, "dash_scale", value), "Dash spacing"))
            form.addRow("Spacing:", spacing)

        if CLOUD in controls:
            # Bluebeam's Size (no unit: the PDF's cloud intensity) and Invert
            size = _spin(float(getattr(first, "cloud_size", 2.0)), 0.1, 20.0, 2, 0.25)
            size.setObjectName("cloudSize")
            size.setToolTip("Size: how big the cloud's scallops are")
            size.valueChanged.connect(lambda value: self._apply(
                lambda i: (i.prepareGeometryChange(), setattr(i, "cloud_size", value)),
                "Cloud size", coalesce=True))
            invert = QCheckBox("Invert")
            invert.setObjectName("cloudInvert")
            invert.setToolTip("Turn the cloud's scallops inward")
            invert.setChecked(bool(getattr(first, "cloud_invert", False)))
            invert.toggled.connect(lambda on: self._apply(
                lambda i: (i.prepareGeometryChange(), setattr(i, "cloud_invert", bool(on))),
                "Cloud invert"))
            form.addRow("Size:", _row(size, invert, stretch_first=True))

        if CORNER in controls and len(self._items) == 1:
            radius = _spin(style.corner_radius, 0, 200, 1, 1.0, " pt")
            radius.setObjectName("cornerRadiusPanel")
            radius.setToolTip("How round the rectangle's corners are")
            radius.valueChanged.connect(lambda value: self._slide(
                lambda i: setattr(i.style, "corner_radius", value), "Corner radius"))
            form.addRow("Corner Radius:", radius)

    def _add_captions(self, form) -> None:
        """Revu's rows after Style for a measurement or a Sketch to Scale
        shape (the user's photo of a Sketch to Scale rectangle): Show Segment
        Values with Align to Segment / Align Horizontally under it, Show
        Caption with its Edit, Show Centroid. The words they write are in the
        markup's font, set in the rows below."""
        from PySide6.QtWidgets import QButtonGroup, QRadioButton
        from .propbar import sketched
        items = self._items
        first = items[0]

        def every(test) -> bool:
            return all(test(i) for i in items)

        def refreshed(item) -> None:
            item.prepareGeometryChange()
            item.refresh(page=self.window.current_page())

        if every(lambda i: getattr(i, "offers_segments", lambda: False)()):
            show = QCheckBox("Show Segment Values")
            show.setObjectName("showSegmentValues")
            show.setToolTip("Write each side's length on that side")
            show.setChecked(bool(first.segment_values))
            form.addRow("", show)
            along = QRadioButton("Align to Segment")
            along.setObjectName("segmentAlignAlong")
            level = QRadioButton("Align Horizontally")
            level.setObjectName("segmentAlignLevel")
            group = QButtonGroup(form.parentWidget())
            group.addButton(along)
            group.addButton(level)
            (level if first.segment_align == "horizontal" else along).setChecked(True)
            for radio in (along, level):
                radio.setEnabled(bool(first.segment_values))
                holder = QWidget()
                row = QHBoxLayout(holder)
                row.setContentsMargins(22, 0, 0, 0)       # indented under the tick, as Revu's
                row.addWidget(radio)
                row.addStretch(1)
                form.addRow("", holder)
            show.toggled.connect(lambda on: (
                along.setEnabled(on), level.setEnabled(on),
                self._apply(lambda i: (setattr(i, "segment_values", bool(on)), refreshed(i)),
                            "Show segment values")))
            level.toggled.connect(lambda on: self._apply(
                lambda i: (setattr(i, "segment_align", "horizontal" if on else "segment"),
                           refreshed(i)), "Segment value alignment"))

        captioned = every(lambda i: (isinstance(i, MeasureItem) and i.kind != "calibrate")
                          or sketched(i))
        if captioned:
            caption = QCheckBox("Show Caption")
            caption.setObjectName("showCaption")
            caption.setToolTip("Write the measurement's caption on the drawing "
                               "(Caption ▾ on the Properties toolbar says which values)")
            caption.setChecked(bool(first.show_size if sketched(first) else first.show_label))
            caption.toggled.connect(lambda on: self._apply(
                lambda i: (setattr(i, "show_size" if sketched(i) else "show_label", bool(on)),
                           refreshed(i)), "Caption"))
            change = QPushButton("Edit")
            change.setObjectName("editCaption")
            change.setToolTip("Edit caption: which values it writes, and its label")
            change.clicked.connect(self.edit_caption)
            form.addRow("", _row(caption, change))

        if every(lambda i: getattr(i, "offers_centroid", lambda: False)()):
            centroid = QCheckBox("Show Centroid")
            centroid.setObjectName("showCentroid")
            centroid.setToolTip("Mark the middle of what it encloses")
            centroid.setChecked(bool(first.show_centroid))
            centroid.toggled.connect(lambda on: self._apply(
                lambda i: (setattr(i, "show_centroid", bool(on)), refreshed(i)),
                "Show centroid"))
            form.addRow("", centroid)

    def edit_caption(self) -> None:
        """Revu's Edit beside Show Caption: which values the caption writes
        (the same as Caption ▾ on the bar) and the label it can carry."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        from ..items.measure import CAPTION_PARTS
        from .propbar import sketched
        if not self._items:
            return
        first = self._items[0]
        words = dict(CAPTION_PARTS)
        dialog = QDialog(self)
        dialog.setObjectName("captionDialog")
        dialog.setWindowTitle("Caption")
        form = QFormLayout(dialog)
        ticks = {}
        shown = first.caption_shown()
        for part in first.caption_choices():
            tick = QCheckBox(words.get(part, part.title()))
            tick.setObjectName(f"captionPart_{part}")
            tick.setChecked(part in shown)
            tick.setEnabled(first.caption_available(part))
            form.addRow("", tick)
            ticks[part] = tick
        label = QLineEdit(first.label)
        label.setObjectName("captionLabel")
        label.setPlaceholderText("written when Label is ticked")
        form.addRow("Label:", label)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        def accepted() -> None:
            text = label.text().strip()
            picked = {part for part, tick in ticks.items() if tick.isChecked()}

            def change(item) -> None:
                item.label = text
                for part in item.caption_choices():
                    item.set_caption_part(part, part in picked)
                if sketched(item):
                    item.show_size = True
                else:
                    item.show_label = True
                item.prepareGeometryChange()
                item.refresh(page=self.window.current_page())
            self._apply(change, "Caption")
            QTimer.singleShot(0, lambda: self.show_items(self.window.selected_items()))
        dialog.accepted.connect(accepted)
        self.caption_dialog = dialog
        dialog.open()


    def _line_style_chosen(self, combo, style) -> None:
        """A line style from the list — or Manage…, which opens Line Styles
        and leaves the markup's own style as it was."""
        from ..items import linestyles
        name = combo.currentData()
        if name == linestyles.MANAGE:
            combo.blockSignals(True)
            combo.setCurrentIndex(line_style_index(combo, style.line_style))
            combo.blockSignals(False)
            QTimer.singleShot(0, self.window.manage_line_styles)
            return
        self._apply(lambda i: linestyles.apply(i.style, name), "Line style")

    def _add_breaks(self, item: PolyItem) -> None:
        for segment in sorted(item.broken):
            form = self._group(f"Break {segment + 1}")
            width, height, position = item.break_settings(segment)
            for label, value, high, suffix in (("Width", width, 500, " pt"),
                                               ("Height", height, 500, " pt"),
                                               ("Position", position * 100, 95, " %")):
                spin = QDoubleSpinBox()
                spin.setRange(1 if label != "Position" else 5, high)
                spin.setValue(value)
                spin.setSuffix(suffix)
                spin.setObjectName(f"break{label}{segment}")
                spin.valueChanged.connect(lambda value, s=segment, name=label: self._slide(
                    lambda i: i.set_break_settings(
                        s,
                        value if name == "Width" else i.break_settings(s)[0],
                        value if name == "Height" else i.break_settings(s)[1],
                        value / 100 if name == "Position" else i.break_settings(s)[2]),
                    "Break " + name.lower()))
                form.addRow(label, spin)

    def _add_text(self, first: MarkupItem, compact: bool = False) -> None:
        """The words' settings, in Appearance as Bluebeam keeps them: the font
        and its size, Font Colour, Alignment, Font Style, Margin."""
        form = self._group("Appearance")
        style = first.style
        family = self._font_list()
        family.setObjectName("fontFamily")
        family.setCurrentFont(QFont(QFontInfo(style.font()).family()))

        def font_chosen(font) -> None:
            self._apply(lambda i: setattr(i.style, "font_family", font.family()), "Font")
        family.currentFontChanged.connect(font_chosen)
        self._font_in_use = (family, font_chosen)
        form.addRow("Font:", family)

        size = _spin(style.font_size, 1.0, 144.0, 1, 0.5)    # Revu: 1 to 144
        if isinstance(first, MeasureItem):
            size.setObjectName("measurementTextSize")
        elif isinstance(first, CountItem):
            size.setObjectName("countTextSize")
        else:
            size.setObjectName("fontSize")
        size.valueChanged.connect(lambda value: self._slide(
            lambda i: (setattr(i.style, "font_size", value),
                       setattr(i.style, "font_auto", False)), "Font size"))
        if isinstance(first, (TextItem, CalloutItem)) and not isinstance(first, TypewriterItem) \
                and getattr(first, "TYPE", "") != "checkbox":
            # Revu's Auto: the largest size that fits the box
            auto = QCheckBox("Auto")
            auto.setObjectName("fontAutoPanel")
            auto.setToolTip("The words set at the largest size that fits the box")
            auto.setChecked(bool(style.font_auto))
            size.setEnabled(not style.font_auto)
            auto.toggled.connect(lambda on: (size.setEnabled(not on), self._apply(
                lambda i: setattr(i.style, "font_auto", bool(on)), "Auto font size")))
            form.addRow("Font Size:", _row(size, auto, stretch_first=True))
        else:
            form.addRow("Font Size:", size)

        colour = ColorButton(style.text_color, label="Font Colour")
        colour.colorChanged.connect(lambda value: self._apply(
            lambda i: setattr(i.style, "text_color", value), "Text colour"))
        form.addRow("Font Colour:", _row(colour))

        # Revu's Font Style: Bold, Italic, Underline, Strikethrough — and for
        # words in a box, Superscript and Subscript (one or the other)
        weights = []
        kinds = [("B", "bold", "Bold"), ("I", "italic", "Italic"),
                 ("U", "underline", "Underline"), ("S", "strikethrough", "Strikethrough")]
        if isinstance(first, _TextBase):
            kinds += [("x²", "superscript", "Superscript"), ("x₂", "subscript", "Subscript")]
        buttons = {}
        for label, attribute, tip in kinds:
            button = QToolButton()
            button.setText(label)
            button.setToolTip(tip)
            button.setObjectName(f"fontStyle_{attribute}")
            button.setCheckable(True)
            button.setChecked(bool(getattr(style, attribute)))
            font = button.font()
            font.setBold(attribute == "bold")
            font.setItalic(attribute == "italic")
            font.setUnderline(attribute == "underline")
            font.setStrikeOut(attribute == "strikethrough")
            button.setFont(font)
            button.toggled.connect(lambda on, a=attribute: self._font_style(a, on, buttons))
            buttons[attribute] = button
            weights.append(button)
        form.addRow("Font Style:", _row(*weights))

        if compact:
            return

        # Bluebeam's Alignment: three across, then three down
        across = QComboBox()
        across.setObjectName("textAlign")
        for name in ("left", "center", "right", "justify"):
            across.addItem(name.title(), name)
        across.setCurrentIndex(max(across.findData(style.align), 0))
        across.currentIndexChanged.connect(lambda _i: self._apply(
            lambda i: setattr(i.style, "align", across.currentData()), "Alignment"))
        down = QComboBox()
        down.setObjectName("textVAlign")
        for name in ("top", "middle", "bottom"):
            down.addItem(name.title(), name)
        down.setCurrentIndex(max(down.findData(style.valign), 0))
        down.currentIndexChanged.connect(lambda _i: self._apply(
            lambda i: setattr(i.style, "valign", down.currentData()), "Alignment"))
        form.addRow("Alignment:", _row(across, down))
        if isinstance(first, _TextBase):
            # Revu's Line Spacing: Single, 1.15, 1.5, Double or any multiple
            from .propbar import line_spacing_combo
            spacing = line_spacing_combo(first.line_height_factor())
            spacing.setObjectName("lineSpacingPanel")
            spacing.setMinimumWidth(72)
            spacing.setMaximumWidth(16777215)
            spacing.valueChanged.connect(lambda value: self._apply(
                lambda i: setattr(i.style, "line_spacing", float(value))
                if isinstance(i, _TextBase) else None, "Line spacing"))
            form.addRow("Line Spacing:", spacing)
        self._add_margins(form, first)

    def _add_margins(self, form, first: MarkupItem) -> None:
        """The room between a box's border and its words: one value all round,
        or each side of its own (left, top, right, bottom)."""
        style = first.style
        sides = (first.margins() if hasattr(first, "margins")
                 else (style.padding,) * 4)
        even = max(sides) - min(sides) <= 1e-6
        margin = _spin(sides[0] if even else style.padding, 0, 100, 1, 0.5)
        margin.setObjectName("textMargin")
        margin.setToolTip("The space between the box's border and its words, in "
                          "points, the same all round")
        boxes = []
        for name, value in zip(("Left", "Top", "Right", "Bottom"), sides):
            box = _spin(value, 0, 100, 1, 0.5)
            box.setObjectName(f"textMargin{name}")
            box.setPrefix(f"{name[0]} ")
            box.setToolTip(f"{name} margin: the space between the box's {name.lower()} "
                           "border and its words, in points")
            boxes.append(box)

        def all_round(value: float) -> None:
            for box in boxes:
                box.blockSignals(True)
                box.setValue(value)
                box.blockSignals(False)

            def change(item) -> None:
                item.style.padding = value
                item.style.text_margins = ()
            self._slide(change, "Text margin")

        def one_side(_value: float) -> None:
            values = tuple(float(box.value()) for box in boxes)
            if max(values) - min(values) <= 1e-6:
                margin.blockSignals(True)
                margin.setValue(values[0])
                margin.blockSignals(False)
            self._slide(lambda item: setattr(item.style, "text_margins", values),
                        "Text margins")
        margin.valueChanged.connect(all_round)
        for box in boxes:
            box.valueChanged.connect(one_side)
        form.addRow("Margin:", margin)
        # two by two, so the panel need be no wider: left and top, right and bottom
        from PySide6.QtWidgets import QGridLayout
        sides_box = QWidget()
        grid = QGridLayout(sides_box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        for index, box in enumerate(boxes):
            grid.addWidget(box, index // 2, index % 2)
        form.addRow("Margins:", sides_box)

    def _add_arrows(self, first: MarkupItem) -> None:
        """What the ends of a line carry: Bluebeam's Start and End, in
        Appearance. A callout's leader has one end that means anything — the
        one pointing at the thing — so it is offered End and nothing else;
        its box can be drawn as a cloud (Bluebeam's Shape)."""
        form = self._group("Appearance")
        if isinstance(first, CalloutItem):
            head = arrow_combo()
            head.setObjectName("arrowEnd")
            set_arrow(head, first.style.arrow_end)
            head.currentIndexChanged.connect(lambda _i: self._apply(
                lambda i: setattr(i.style, "arrow_end", head.currentData()), "Arrow head"))
            form.addRow("End:", head)
            self._add_arrow_size(form, first)
            shape = QComboBox()
            shape.setObjectName("calloutShape")
            shape.addItems(["Rectangle", "Cloud"])
            shape.setCurrentIndex(1 if first.shape_kind == "cloud" else 0)
            shape.currentIndexChanged.connect(lambda index: self._apply(
                lambda i: setattr(i, "shape_kind", "cloud" if index else "box"),
                "Callout shape"))
            form.addRow("Shape:", shape)
            if first.leaders and not first.clouds_a_region():
                leader = self._group("Leader")
                stand_off = _spin(first.leaders[0].reach, first.LEAST_REACH, 400.0, 0, 1.0, " pt")
                stand_off.setObjectName("leaderStandOff")
                stand_off.setToolTip(
                    "How far the hinge stands off the box before the line "
                    "turns towards\nwhat it points at. Dragging the hinge "
                    "does the same thing.")
                stand_off.valueChanged.connect(lambda value: self._slide(
                    lambda i: setattr(i, "elbow_reach", value), "Leader stand-off"))
                leader.addRow("Hinge:", stand_off)
                count = QLabel(f"{len(first.leaders)}"
                               + (" arrow" if len(first.leaders) == 1 else " arrows"))
                count.setToolTip("Right-click the call-out to add another, or "
                                 "to take one away")
                leader.addRow("Leaders:", count)
            return
        start = arrow_combo()
        from .propbar import _mirrored
        for index in range(start.count()):
            # a start's end points back along the line, as on the bar (◀—)
            start.setItemIcon(index, _mirrored(start.itemIcon(index)))
        start.setObjectName("arrowStart")
        set_arrow(start, first.style.arrow_start)
        start.currentIndexChanged.connect(lambda _i: self._apply(
            lambda i: setattr(i.style, "arrow_start", start.currentData()), "Arrow"))
        form.addRow("Start:", start)
        end = arrow_combo()
        end.setObjectName("arrowEnd")
        set_arrow(end, first.style.arrow_end)
        end.currentIndexChanged.connect(lambda _i: self._apply(
            lambda i: setattr(i.style, "arrow_end", end.currentData()), "Arrow"))
        form.addRow("End:", end)
        self._add_start_size(form, first)
        self._add_arrow_size(form, first)

    def _font_style(self, attribute: str, on: bool, buttons: dict) -> None:
        """One Font Style button: superscript and subscript are one or the other."""
        other = {"superscript": "subscript", "subscript": "superscript"}.get(attribute)
        if on and other in buttons:
            buttons[other].blockSignals(True)
            buttons[other].setChecked(False)
            buttons[other].blockSignals(False)
        self._apply(lambda i: i.style.set_font_style(attribute, on), "Font style")

    @staticmethod
    def _end_size_list(name: str, value: float, tip: str):
        """A line end's size as the bar says it: Auto, 25% … 400%."""
        from .propbar import END_SIZES, ValueCombo
        size = ValueCombo(END_SIZES, lambda v: f"{v * 100:g}%", 0.25, 4.0, editable=False,
                          first=("Auto", 1.0), width=72)
        size.setMinimumWidth(72)
        size.setMaximumWidth(16777215)
        size.setObjectName(name)
        size.blockSignals(True)
        size.setValue(value)
        size.blockSignals(False)
        size.setToolTip(tip)
        return size

    def _add_start_size(self, form, first: MarkupItem) -> None:
        """Revu sizes each end on its own: the start's."""
        size = self._end_size_list(
            "arrowStartSize", first.style.start_size(),
            "The start's line-end size: Auto sizes it from the line width")
        size.valueChanged.connect(
            lambda value: self._slide(
                lambda item: setattr(item.style, "arrow_start_size", value),
                "Start size"))
        form.addRow("Start Size:", size)

    def _add_arrow_size(self, form, first: MarkupItem) -> None:
        size = self._end_size_list(
            "arrowSize", first.style.arrow_size,
            "The end's line-end size: Auto sizes it from the line width")
        def end(item, value) -> None:
            # the start keeps its size: each end is sized on its own
            if float(item.style.arrow_start_size or 0.0) <= 0:
                item.style.arrow_start_size = float(item.style.arrow_size or 1.0)
            item.style.arrow_size = value
        size.valueChanged.connect(
            lambda value: self._slide(lambda item: end(item, value), "Arrowhead size"))
        form.addRow("End Size:", size)

    def _add_size(self, item) -> None:
        """What a rectangle or an ellipse measures, and whether it says so.

        A plain one's size is its Document Width and Height, in Layout, on
        the paper. A Sketch to Scale one is drawn to a real size: its real
        Width and Height are here, to read and to type (3 m, 1500 mm).

        The size lives here rather than being written across the drawing:
        a shape drawn on a plan is a shape, and a page of shapes each carrying
        their dimensions is unreadable. The tick puts it on the shape for
        anyone who wants it there.
        """
        page = self.window.current_page()
        item.refresh(page=page)
        if getattr(item, "to_scale", False):
            form = self._group("Sketch to Scale")
            real = item.measures_real(page)
            width_text, height_text = item.size_texts(page)
            ellipse = item.kind == "ellipse"
            fields = []
            for caption, text, name, tip in (
                    ("Width:", width_text, "sketchWidth",
                     "Horizontal diameter" if ellipse else "Width"),
                    ("Height:", height_text, "sketchHeight",
                     "Vertical diameter" if ellipse else "Height")):
                field = QLineEdit(text)
                field.setObjectName(name)
                field.setToolTip(f"{tip}, real size — type it with a unit, "
                                 "e.g. 3 m" if real else
                                 f"{tip} on the paper: this page has no scale yet")
                form.addRow(caption, field)
                fields.append(field)

            def typed(_=None) -> None:
                if self._building:
                    return
                width, height = (f.text().strip() for f in fields)
                if (width, height) == item.size_texts(page):
                    return
                done = []
                self._apply(lambda i: done.append(i.set_real_size(width, height, page)),
                            "Sketch to Scale size")
                if not all(done):
                    self.window.status_hint.setText(
                        "Could not read those dimensions — try something like “3 m”.")
            for field in fields:
                field.editingFinished.connect(typed)
            if not real:
                note = QLabel("Scale Not Set — sizes are on the paper")
                note.setObjectName("sketchNoScale")
                note.setWordWrap(True)
                form.addRow("", note)
                scale = QPushButton("Set Scale…")
                scale.clicked.connect(lambda: self.window.calibrate_dialog())
                form.addRow("", scale)
        else:
            form = self._group("Size")
            exact = QPushButton("Exact size…")
            exact.setToolTip("Set the width and height on the paper")
            exact.clicked.connect(lambda: self.window.set_rectangle_size(item))
            form.addRow("", exact)

        if getattr(item, "to_scale", False):
            return                 # its Show Caption is in Appearance, as Revu's
        show = QCheckBox("Show size")
        show.setToolTip("Write the size across the shape itself")
        show.setChecked(item.show_size)
        show.toggled.connect(
            lambda on: self._apply(
                lambda i: (setattr(i, "show_size", on),
                           i.refresh(page=self.window.current_page())),
                "Show size"))
        form.addRow("", show)

    def _add_contents(self, item) -> None:
        form = self._group("Contents")
        heading = QLineEdit(item.title)
        heading.setPlaceholderText("Contents")
        typing = self._typing_run(heading)
        heading.textEdited.connect(
            lambda text: self._apply(lambda i: setattr(i, "title", text), "Heading",
                                     coalesce=typing()))
        form.addRow("Heading:", heading)

        for label, attribute in (("Page numbers", "show_page_numbers"),
                                 ("Leader dots", "leader_dots")):
            box = QCheckBox(label)
            box.setChecked(getattr(item, attribute))
            box.toggled.connect(
                lambda on, a=attribute: self._apply(
                    lambda i: setattr(i, a, on), "Contents"))
            form.addRow("", box)

        text_size = QDoubleSpinBox()
        text_size.setRange(3, 96)
        text_size.setValue(item.style.font_size)
        text_size.setSuffix(" pt")
        text_size.valueChanged.connect(lambda value: self._slide(
            lambda i: setattr(i.style, "font_size", value), "Text size"))
        form.addRow("Text Size:", text_size)
        text_colour = ColorButton(item.style.text_color, label="Text colour")
        text_colour.colorChanged.connect(lambda value: self._apply(
            lambda i: setattr(i.style, "text_color", value), "Text colour"))
        form.addRow("Text Colour:", text_colour)

        height = QDoubleSpinBox()
        height.setRange(8.0, 60.0)
        height.setValue(item.row_height)
        height.setSuffix(" pt")
        height.valueChanged.connect(
            lambda value: self._slide(
                lambda i: setattr(i, "row_height", value), "Contents"))
        form.addRow("Line Spacing:", height)

        note = QLabel(f"{len(item.entries())} bookmark(s) — add them from the "
                      "bookmarks panel")
        note.setWordWrap(True)
        note.setStyleSheet("color:#6b7280;")
        form.addRow(note)

    def _add_note(self, item) -> None:
        """A note is a pin on the page; its words are only in this panel."""
        form = self._group("Note")
        body = QPlainTextEdit(item.comment)
        body.setFixedHeight(70)
        body.setPlaceholderText("What this note says")
        typing = self._typing_run(body)
        body.textChanged.connect(
            lambda: self._apply(lambda i: setattr(i, "comment", body.toPlainText()),
                                "Note text", coalesce=typing()))
        form.addRow(body)
        # Revu's Icon: how the note is drawn
        from .propbar import note_icon_picture
        from .widgets import checked_list
        from ..items.text import NOTE_ICONS
        icon_list = QComboBox()
        icon_list.setObjectName("noteIconPanel")
        icon_list.setIconSize(QSize(20, 20))
        for key, words in NOTE_ICONS:
            icon_list.addItem(note_icon_picture(key), words, key)
        checked_list(icon_list)
        icon_list.setCurrentIndex(max(icon_list.findData(item.icon), 0))
        icon_list.currentIndexChanged.connect(lambda _i: self._apply(
            lambda i: setattr(i, "icon", icon_list.currentData() or "Note"), "Note icon"))
        appearance = self._group("Appearance")
        appearance.insertRow(0, "Icon:", icon_list)

    def _add_image(self, item) -> None:
        form = self._group("Image")
        row = QHBoxLayout()
        replace = QPushButton("Replace…")
        replace.setToolTip("Replace the picture with one from a file, keeping "
                           "its proportions inside this one's box")
        replace.clicked.connect(lambda: self.window.replace_image(item, "file"))
        pasted = QPushButton("From clipboard")
        pasted.setToolTip("Replace the picture with the one on the clipboard")
        pasted.clicked.connect(lambda: self.window.replace_image(item, "clipboard"))
        row.addWidget(replace)
        row.addWidget(pasted)
        form.addRow("", row)
        keep = QCheckBox("Keep its proportions")
        keep.setChecked(item.keep_aspect)
        keep.toggled.connect(
            lambda on: self._apply(lambda i: setattr(i, "keep_aspect", on),
                                   "Image"))
        form.addRow("", keep)
        colours = QPushButton("Colour Processing…")
        colours.clicked.connect(lambda: self.window.change_colors(item))
        form.addRow("", colours)

    def _add_measure(self, item: MeasureItem) -> None:
        form = self._group("Measurement")
        value = QLabel(item.value_text or "—")
        font = value.font()
        font.setBold(True)
        value.setFont(font)
        form.addRow("Value:", value)

        subject = QLineEdit(item.subject)
        subject.setToolTip("Measurements sharing a subject are totalled in the markups list")
        typing = self._typing_run(subject)
        subject.textEdited.connect(
            lambda text: self._apply(lambda i: setattr(i, "subject", text), "Subject",
                                     coalesce=typing()))
        form.addRow("Counts as:", subject)

        if item.kind not in ("dimension", "calibrate", "angle"):
            # Revu's Measurement Properties: this measurement's own units
            # (the Units ▾ on the Properties toolbar sets the same)
            from ..items.measure import AREA_UNITS, LENGTH_UNITS, VOLUME_UNITS
            from .propbar import _unit_words
            scale = self.window.current_page().scale
            rows = [("length", "Length:", LENGTH_UNITS, scale.display_unit)]
            if item.kind in ("area", "volume", "perimeter"):
                rows.append(("area", "Area:", AREA_UNITS, scale.area_unit))
            if item.kind == "volume" or (item.depth_text and item.kind in ("area",
                                                                            "perimeter")):
                rows.append(("volume", "Volume:", VOLUME_UNITS,
                             scale.area_unit.replace("^2", "^3")
                             if scale.area_unit.endswith("^2") else ""))
            for key, words, units, page_unit in rows:
                own = QComboBox()
                own.setObjectName(f"measureOwn{key.title()}Unit")
                own.addItem(f"Page ({_unit_words(page_unit)})" if page_unit else "Page", "")
                for unit_name in units:
                    own.addItem(_unit_words(unit_name), unit_name)
                found = own.findData(item.units.get(key, ""))
                if found < 0:
                    own.addItem(item.units.get(key, ""), item.units.get(key, ""))
                    found = own.count() - 1
                own.setCurrentIndex(found)
                own.setToolTip("What this measurement is written in: the page's "
                               "units, or its own")
                own.activated.connect(lambda _i, k=key, box=own: self._apply(
                    lambda i: (i.set_unit(k, box.currentData() or ""),
                               i.refresh(page=self.window.current_page())),
                    "Measurement units"))
                form.addRow(words, own)
        if item.kind in ("area", "volume", "perimeter"):
            unit = UnitCombo(self.window.current_page().scale.area_unit)
            unit.setObjectName("measureAreaUnit")
            unit.setToolTip("The page's area unit: every area on the page that has "
                            "none of its own")
            unit.unitChanged.connect(self.window.set_area_unit)
            form.addRow("Page Area:", unit)
        if item.kind in ("volume", "area", "perimeter"):
            depth = QLineEdit(item.depth_text)
            depth.setPlaceholderText("e.g. 150 mm")
            typing_depth = self._typing_run(depth)
            depth.textEdited.connect(
                lambda text: self._apply(
                    lambda i: (setattr(i, "depth_text", text),
                               i.refresh(page=self.window.current_page())), "Depth",
                    coalesce=typing_depth()))
            form.addRow("Depth:", depth)

        if len(self._items) == 1 and item.kind != "calibrate":
            from .namebox import SMathNameEdit
            variable = SMathNameEdit(item.variable)     # as SMath writes a name
            variable.setObjectName("measureVariable")
            variable.setPlaceholderText("a name, e.g. L.beam")
            variable.setToolTip("Give it a name and the calculations can use it: it is "
                                "defined at the top-left of the measurement, and follows "
                                "it as it changes")
            variable.editingFinished.connect(
                lambda: self.window.set_measure_variable(item, variable.text()))
            form.addRow("Variable:", variable)

        words = QLineEdit(item.custom_label)
        words.setPlaceholderText(item.measured_text or "the measured value")
        words.setToolTip("What this says on the drawing. Leave it empty and it "
                         "shows what it measured.")
        words.editingFinished.connect(
            lambda: self._apply(
                lambda i: (setattr(i, "custom_label", words.text().strip()),
                           i.refresh(page=self.window.current_page())),
                "Measurement text"))
        form.addRow("Says:", words)

        inline = QCheckBox("Inline text")
        inline.setToolTip("Keep the measurement text in line with its line")
        inline.setChecked(item.label_angle is None)
        inline.toggled.connect(
            lambda on: self._apply(
                lambda i: setattr(i, "label_angle", None if on else 0.0),
                "Text angle"))
        form.addRow("", inline)

        # (whether it is written on the page: Show Caption, in Appearance)

        calibrate = QPushButton("Calibrate…")
        calibrate.setToolTip("Pick a known distance on this page and enter its length")
        calibrate.clicked.connect(lambda: self.window.calibrate_dialog())
        form.addRow("", calibrate)

    def _add_count(self, item: CountItem) -> None:
        form = self._group("Count")
        subject = QLineEdit(item.subject)
        typing = self._typing_run(subject)
        subject.textEdited.connect(
            lambda text: self._apply(lambda i: setattr(i, "subject", text), "Count subject",
                                     coalesce=typing()))
        form.addRow("Subject:", subject)
        symbol = QComboBox()
        symbol.addItems(list(CountItem.SYMBOLS))
        symbol.setCurrentText(item.symbol)
        symbol.currentTextChanged.connect(
            lambda value: self._apply(lambda i: setattr(i, "symbol", value), "Count symbol"))
        form.addRow("Symbol:", symbol)
        number = QSpinBox()
        number.setObjectName("countNumber")
        number.setRange(1, 999999)
        number.setValue(item.index)
        number.valueChanged.connect(
            lambda value: self._apply(lambda i: setattr(i, "index", value), "Count number"))
        form.addRow("Number:", number)
        show = QCheckBox("Show number")
        show.setChecked(item.show_index)
        show.toggled.connect(
            lambda on: self._apply(lambda i: setattr(i, "show_index", on), "Count label"))
        form.addRow("", show)

    def _add_stamp(self, item: StampItem) -> None:
        form = self._group("Stamp")
        preset = QComboBox()
        preset.setEditable(True)
        preset.addItems(list(STAMP_PRESETS))
        preset.setCurrentText(item.text)
        preset.currentTextChanged.connect(self._set_stamp_text)
        form.addRow("Text:", preset)
        subtext = QLineEdit(item.subtext)
        subtext.setPlaceholderText("Name, date, revision…")
        typing = self._typing_run(subtext)
        subtext.textEdited.connect(
            lambda text: self._apply(lambda i: setattr(i, "subtext", text), "Stamp",
                                     coalesce=typing()))
        form.addRow("Sub-text:", subtext)
        radius = QDoubleSpinBox()
        radius.setObjectName("stampCornerRadius")
        radius.setRange(0, 100)
        radius.setSingleStep(0.5)
        radius.setValue(item.style.corner_radius)
        radius.setSuffix(" pt")
        radius.valueChanged.connect(lambda value: self._slide(
            lambda selected: setattr(selected.style, "corner_radius", value),
            "Stamp corners"))
        form.addRow("Corners:", radius)

    def _set_stamp_text(self, text: str) -> None:
        colour = STAMP_PRESETS.get(text.upper())

        def setter(item):
            item.text = text
            if colour:
                item.style.stroke = colour
                item.style.fill = colour
                item.style.text_color = colour
        self._apply(setter, "Stamp text")

    def _add_defaults(self, first: MarkupItem) -> None:
        """Bluebeam's Options: Add to Tool Chest (a list of the tool sets)
        and Set as Default — and Forget Default, to go back."""
        from . import toolsets

        form = self._group("Options")
        add = QToolButton()
        add.setObjectName("addToToolChest")
        add.setText("Add to Tool Chest")
        add.setToolTip("Keep this markup, contents and all, in a tool set to use again")
        add.setPopupMode(QToolButton.MenuButtonPopup)
        add.setToolButtonStyle(Qt.ToolButtonTextOnly)
        menu = QMenu(add)
        menu.setProperty("cf_data", True)          # the tool sets' names
        for group in toolsets.load_toolsets():
            menu.addAction(group.name, lambda name=group.name: self.window.add_to_toolset(
                first, into=name, ask=False))
        if menu.isEmpty():
            menu.addAction("Choose a Tool Set…", lambda: self.window.add_to_toolset(first))
        add.setMenu(menu)
        add.clicked.connect(lambda: self.window.add_to_toolset(first))
        form.addRow(add)

        default = QPushButton("Set as Default")
        default.setObjectName("setAsDefault")
        default.setToolTip("New markups of this kind will be drawn like this one")
        default.clicked.connect(lambda: self.window.set_as_default(first))
        form.addRow(default)

        if toolsets.default_key(first) in toolsets.load_defaults():
            forget = QPushButton("Forget Default")
            forget.setToolTip("Restore the original defaults for this markup kind")
            forget.clicked.connect(lambda: self._forget_default(first))
            form.addRow(forget)

    def _add_block(self, first) -> None:
        """A calculation block: what it holds, and whether it keeps its names."""
        form = self._group("Calculation block")
        members = first.members()
        equations = [m for m in members if getattr(m, "region", None) is not None]
        held = QLabel(f"{len(equations)} equation{'s' if len(equations) != 1 else ''}"
                      + (f", {len(members) - len(equations)} text" if len(members) > len(equations)
                         else ""))
        held.setObjectName("blockHolds")
        form.addRow("Holds:", held)
        contained = QCheckBox("Self-Contained")
        contained.setObjectName("blockSelfContained")
        contained.setToolTip("What the equations in the block define stays inside it; "
                             "the block still reads everything defined above it")
        contained.setChecked(first.self_contained)
        contained.toggled.connect(
            lambda on: self._apply(lambda i: i.set_self_contained(on), "Self-contained"))
        form.addRow("", contained)
        if len(self._items) == 1:
            # the right-click menu's commands, in its words (Title Case)
            members_button = QPushButton("Select Its Equations")
            members_button.setObjectName("blockSelect")
            members_button.setToolTip("Pick the equations the block holds")
            members_button.clicked.connect(lambda: self.window._select_block_members(first))
            form.addRow("", members_button)
            remove = QPushButton("Remove Block, Keep Equations")
            remove.setObjectName("blockRemove")
            remove.setToolTip("Take the frame away; its equations stay on the page as they are")
            remove.clicked.connect(lambda: self.window.remove_block_keep_equations(first))
            form.addRow("", remove)

    def _add_table(self, first) -> None:
        """A table or a spreadsheet: its name (formulas and equations use
        it), its size."""
        sheet = getattr(first, "SHEET_RUN", False)
        form = self._group("Worksheet" if sheet else "Table")
        name = QLineEdit(first.name)
        name.setObjectName("tableName")
        name.setToolTip(("The sheet's" if sheet else "The table's") +
                        " name: formulas read it as Name!B4, equations as Name.B4; "
                        "renaming it updates them")

        def renamed():
            text = name.text().strip()
            if text and text != first.name:
                if not self.window.view.tables.rename_to(first, text):
                    name.setText(first.name)
        name.editingFinished.connect(renamed)
        form.addRow("Name:", name)
        rows, cols = first.size
        paging = getattr(first, "paging", None)
        if getattr(first, "SHEET_RUN", False) and paging is not None:
            # the sheet's own, not the grid the workbook view shows past it
            rows, cols = first.sheet_rows, paging.shown_cols
        size = QLabel(f"{rows} rows × {cols} columns")
        size.setObjectName("tableSize")
        form.addRow("Size:", size)
        if sheet:
            from .workbookscope import add_sheet_rows
            add_sheet_rows(self, form, first)
        if self.window.view.tables.item is not first:
            open_button = QPushButton("Edit Table")
            open_button.setToolTip("Open the table for its cells (or double-click it)")
            open_button.clicked.connect(lambda: self.window.view.tables.open(first))
            form.addRow("", open_button)

    def _add_cells(self, table) -> None:
        """The selected cells, as the Properties toolbar's table controls
        and the cells' right-click menu offer them: number format, Decimal
        Places, Significant Figures, unit, font, fill, alignment, borders.
        Each change is one undo step (TableEditing._change)."""
        from .tablebar import NUMBER_FORMATS
        from .unitbox import UnitField
        tables = self.window.view.tables
        controls = getattr(self.window, "table_controls", None)
        if tables.active_style() is None or controls is None:
            return
        form = self._group("Cells")
        where = QLabel()
        where.setObjectName("cellsSelection")
        form.addRow("Selection:", where)
        number = QComboBox()
        number.setObjectName("cellsNumberFormat")
        for label, _code in NUMBER_FORMATS:
            number.addItem(label)
        number.addItem("More…")
        number.activated.connect(lambda i: (controls._number_chosen(i), self.sync_cells()))
        form.addRow("Number Format:", number)
        places = QSpinBox()
        places.setObjectName("cellsDecimalPlaces")
        places.setRange(-1, 15)
        places.setSpecialValueText("General")
        places.setToolTip("Decimal Places: how many the selected cells show (General: as "
                          "many as fit), as Excel's Increase and Decrease Decimal")
        places.valueChanged.connect(lambda n: self._cells_do(
            lambda: tables.set_places(None if n < 0 else n)))
        form.addRow("Decimal Places:", places)
        significant = QCheckBox("Significant Figures")
        significant.setObjectName("cellsSignificant")
        significant.setToolTip("Decimal Places counts significant figures, not places "
                               "after the point")
        significant.toggled.connect(lambda on: self._cells_do(
            lambda: tables.set_significant(on)))
        form.addRow("", significant)
        unit = UnitField()
        unit.setObjectName("cellsUnit")
        unit.setToolTip("Unit (SMath's unit box): the selected cells' quantities are shown "
                        "in it. Blank: as typed")
        unit.editingFinished.connect(lambda: self._cells_do(
            lambda: controls.set_unit(unit.unit_text(), unit)))
        form.addRow("Unit:", unit)
        font = QFontComboBox()
        font.setObjectName("cellsFont")
        font.currentFontChanged.connect(lambda f: self._cells_format(
            font=f.family() if f.family() != "Calibri" else None))
        form.addRow("Font:", font)
        size = QDoubleSpinBox()
        size.setObjectName("cellsFontSize")
        size.setRange(1, 409)
        size.setDecimals(1)
        size.setSuffix(" pt")
        size.valueChanged.connect(lambda v: self._cells_format(size=None if v == 11 else v))
        form.addRow("Size:", size)
        styles = {}
        for key, title in (("bold", "Bold"), ("italic", "Italic"), ("underline", "Underline")):
            box = QCheckBox(title)
            box.setObjectName(f"cells{title}")
            box.toggled.connect(lambda on, k=key: self._cells_format(
                **{k: ("single" if on else "") if k == "underline" else on}))
            styles[key] = box
        colour = ColorButton("#000000", label="Font colour")
        colour.setObjectName("cellsColour")
        colour.colorChanged.connect(lambda c: self._cells_format(color=c or None))
        form.addRow("Colour:", colour)
        fill = ColorButton("", True, label="Fill colour")
        fill.setObjectName("cellsFill")
        fill.colorChanged.connect(lambda c: self._cells_format(fill=c or None))
        form.addRow("Fill:", fill)
        horizontal = QComboBox()
        horizontal.setObjectName("cellsHorizontal")
        for key, title in (("general", "General"), ("left", "Left"), ("center", "Centre"),
                           ("right", "Right")):
            horizontal.addItem(title, key)
        horizontal.activated.connect(lambda _i: self._cells_format(
            h_align=horizontal.currentData()))
        form.addRow("Horizontal:", horizontal)
        vertical = QComboBox()
        vertical.setObjectName("cellsVertical")
        for key, title in (("top", "Top"), ("center", "Middle"), ("bottom", "Bottom")):
            vertical.addItem(title, key)
        vertical.activated.connect(lambda _i: self._cells_format(
            v_align=vertical.currentData()))
        form.addRow("Vertical:", vertical)
        wrap = QCheckBox("Wrap Text")
        wrap.setObjectName("cellsWrap")
        wrap.toggled.connect(lambda on: self._cells_format(wrap=on))
        # two to a row, to keep within the panel's width
        form.addRow("", _row(styles["bold"], styles["italic"]))
        form.addRow("", _row(styles["underline"], wrap))
        borders = QToolButton()
        borders.setObjectName("cellsBorders")
        borders.setText("Borders")
        borders.setToolTip("The selected cells' borders, as the Properties toolbar's")
        borders.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(borders)
        menu.setProperty("cf_context", "tablebar.borders")
        for label, which in (("All Borders", "all"), ("Outside Borders", "outside"),
                             ("Inside Borders", "inside"), ("Thick Box Border", "thick_box"),
                             ("Top Border", "top"), ("Bottom Border", "bottom"),
                             ("Left Border", "left"), ("Right Border", "right"),
                             ("No Border", "none")):
            menu.addAction(label, lambda w=which: self._cells_do(lambda: tables.borders(w)))
        borders.setMenu(menu)
        more = QPushButton("Format Cells…")
        more.setToolTip("Every setting of the selected cells (Ctrl+1)")
        more.clicked.connect(self.window.format_cells_dialog)
        form.addRow("", borders)
        form.addRow("", more)
        self._cells = dict(where=where, number=number, places=places, significant=significant,
                           unit=unit, font=font, size=size, styles=styles, colour=colour,
                           fill=fill, horizontal=horizontal, vertical=vertical, wrap=wrap)
        self.sync_cells()

    def _cells_do(self, change) -> None:
        if self._building or self._cells is None:
            return
        if not self.window.view.tables.is_open():
            return
        # (the formula bar's controls hand the keys back to the cells; a
        # change made here keeps them in the panel)
        from .widgets import focus_kept
        with focus_kept(unless=self.window.view):
            change()

    def _cells_format(self, **fields) -> None:
        self._cells_do(lambda: self.window.view.tables.format(**fields))

    def sync_cells(self) -> None:
        """The Cells section shows the active cell's look (after a change, or
        when the selection moves): cheap, nothing rebuilt."""
        from shiboken6 import isValid
        from ..sheet.refs import col_letters
        from .tablebar import format_index
        cells = self._cells
        tables = self.window.view.tables
        if cells is None or not isValid(cells["places"]) or tables.item not in self._items:
            return
        st = tables.active_style()
        if st is None:
            return
        building, self._building = self._building, True
        try:
            t, l, b, r = tables.selection()
            text = f"{col_letters(l)}{t + 1}"
            if (t, l) != (b, r):
                text += f":{col_letters(r)}{b + 1}"
            cells["where"].setText(text)
            cells["number"].setCurrentIndex(format_index(st.number_format))
            places = tables.places()
            cells["places"].setValue(-1 if places is None else places)
            cells["significant"].setChecked(bool(st.significant))
            if not cells["unit"].hasFocus():
                cells["unit"].set_unit_text(st.unit)
            cells["font"].setCurrentFont(QFont(st.font or "Calibri"))
            cells["size"].setValue(st.size or 11)
            cells["styles"]["bold"].setChecked(bool(st.bold))
            cells["styles"]["italic"].setChecked(bool(st.italic))
            cells["styles"]["underline"].setChecked(bool(st.underline))
            cells["colour"].set_color(st.color or "#000000")
            cells["fill"].set_color(st.fill or "")
            cells["horizontal"].setCurrentIndex(max(cells["horizontal"].findData(
                st.h_align if st.h_align in ("left", "center", "right") else "general"), 0))
            cells["vertical"].setCurrentIndex(max(cells["vertical"].findData(st.v_align), 0))
            cells["wrap"].setChecked(bool(st.wrap))
        finally:
            self._building = building

    def _add_workbook(self, with_sheet: bool = False) -> None:
        """A workbook's sheet open or in view (one brought in from Excel or
        made here): its Workbook section (workbookscope.py) — and, nothing
        being selected (*with_sheet*), the Worksheet's after it."""
        from .workbookscope import add_panel_section, open_sheet, run_of_sheet
        try:
            sheet = open_sheet(self.window)
        except AttributeError:
            sheet = None                     # the window still being built
        if sheet is not None:
            add_panel_section(self, sheet)
            run = run_of_sheet(self.window, sheet) if with_sheet else None
            if run is not None:
                self._add_table(run)

    def _add_chart(self, first) -> None:
        """A chart: what it is, and its dialog (or double-click it)."""
        form = self._group("Chart")
        kind = {"scatter": "XY scatter", "line": "Line", "column": "Column"}.get(
            first.spec.get("kind"), "")
        form.addRow("Type:", QLabel(kind))
        form.addRow("Series:", QLabel(str(len(first.spec.get("series", [])))))
        edit = QPushButton("Edit Chart…")
        edit.setToolTip("Type, titles, axes, series, error bars and trendlines (or double-click it)")
        edit.setEnabled(not first.locked)
        edit.clicked.connect(lambda: self.window._edit_chart(first))
        form.addRow("", edit)

    def _forget_default(self, item: MarkupItem) -> None:
        from . import toolsets

        toolsets.forget_default(toolsets.default_key(item))
        self.window.status_hint.setText(
            f"New {item.display_name().lower()}s are back to their original look")
        self.show_items(self._items)

    def _add_metadata(self, first: MarkupItem) -> None:
        """Bluebeam's General: Subject, Author, Label, the comments, when it
        was last changed, Lock — and Print, whether it goes on paper."""
        form = self._group("General")
        subject = QLineEdit(first.subject)
        subject.setObjectName("markupSubject")
        typing_subject = self._typing_run(subject)
        subject.textEdited.connect(lambda text: self._apply(
            lambda i: setattr(i, "subject", text), "Subject", coalesce=typing_subject()))
        form.addRow("Subject:", subject)

        author = QLineEdit(first.author)
        author.setObjectName("markupAuthor")
        typing_author = self._typing_run(author)
        author.textEdited.connect(lambda text: self._apply(
            lambda i: setattr(i, "author", text), "Author", coalesce=typing_author()))
        form.addRow("Author:", author)

        label = QLineEdit(first.label)
        label.setObjectName("markupLabel")
        typing_label = self._typing_run(label)
        label.textEdited.connect(lambda text: self._apply(
            lambda i: setattr(i, "label", text), "Label", coalesce=typing_label()))
        form.addRow("Label:", label)

        comment = QPlainTextEdit(first.comment)
        comment.setObjectName("markupComments")
        comment.setPlaceholderText("Comments")
        comment.setFixedHeight(58)
        typing_comment = self._typing_run(comment)
        comment.textChanged.connect(lambda: self._apply(
            lambda i: setattr(i, "comment", comment.toPlainText()), "Comment",
            coalesce=typing_comment()))
        form.addRow(comment)

        if len(self._items) == 1 and getattr(first, "modified", ""):
            form.addRow("Modified:", QLabel(str(first.modified).replace("T", " ")))

        locked = QCheckBox("Lock")
        locked.setObjectName("markupLock")
        locked.setChecked(first.locked)
        locked.toggled.connect(lambda on: self._apply(lambda i: i.set_locked(on), "Lock"))
        boxes = [locked]
        if not getattr(first, "IS_CALC", False):
            # an equation always prints (decision 17)
            printable = QCheckBox("Print")
            printable.setObjectName("markupPrint")
            printable.setToolTip("Include this markup when the page is printed")
            printable.setChecked(first.printable)
            printable.toggled.connect(lambda on: self._apply(
                lambda i: setattr(i, "printable", on), "Print flag"))
            boxes.append(printable)
        if len(self._items) == 1 and hasattr(first, "auto_bookmark"):
            # a text box as a bookmark, titled with its words, wherever it goes
            mark = QCheckBox("Bookmark")
            mark.setObjectName("markupBookmark")
            mark.setToolTip("A bookmark titled with this text, that goes wherever the box goes")
            mark.setChecked(bool(first.auto_bookmark))
            mark.toggled.connect(lambda on: self.window.set_text_bookmark(first, on))
            boxes.append(mark)
        form.addRow(_row(*boxes))
