"""Dock panels: pages, the markups list, bookmarks, tool sets and properties."""
from __future__ import annotations

import csv
import re

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, QTimer, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QIcon, QKeySequence,
                           QPainter, QPen, QPixmap)
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox,
                               QDoubleSpinBox, QInputDialog, QMessageBox,
                               QFontComboBox, QFormLayout, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QListView, QListWidget,
                               QListWidgetItem, QMenu, QPlainTextEdit, QPushButton,
                               QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem,
                               QToolButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from ..core.units import format_quantity
from ..items.base import (ARROW_HEADS, DASH_ARRAYS, HATCH_PATTERNS,
                          LINE_STYLES, MarkupItem)
from ..items.contents import ContentsItem
from ..items.media import ImageItem
from ..items.measure import CountItem, MeasureItem
from ..items.shapes import PolyItem, RectItem
from ..items.text import STAMP_PRESETS, CalloutItem, NoteItem, StampItem, TextItem
from .icons import icon
from .stylecaps import (DASH, FILL, FILL_OPACITY, HATCH, OPACITY, STROKE,
                        WIDTH, common_capabilities)
from .widgets import ColorButton, LabeledSlider, UnitCombo


def _line_style_icon(name: str, colour: str, width: float) -> QIcon:
    pixmap = QPixmap(76, 22)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(colour or "#111318"))
    pen.setWidthF(max(0.75, min(float(width), 6.0)))
    dashes = DASH_ARRAYS.get(name, [])
    if dashes:
        pen.setStyle(Qt.CustomDashLine)
        pen.setDashPattern(dashes)
        pen.setCapStyle(Qt.FlatCap)
    painter.setPen(pen)
    painter.drawLine(3, 11, 73, 11)
    painter.end()
    return QIcon(pixmap)


def _hatch_icon(name: str, colour: str) -> QIcon:
    pixmap = QPixmap(76, 22)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    ink = QColor(colour or "#748096")
    painter.setPen(QPen(ink.darker(135), 1))
    painter.setBrush(QBrush(ink, HATCH_PATTERNS.get(name, Qt.SolidPattern)))
    painter.drawRect(3, 3, 69, 15)
    painter.end()
    return QIcon(pixmap)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

class PageListWidget(QListWidget):
    """A wrapping thumbnail grid whose cells stay centred across the row."""

    CELL_WIDTH = 116
    CELL_HEIGHT = 174

    def __init__(self, parent=None):
        super().__init__(parent)
        self.external_drop_row: int | None = None

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        width = max(self.viewport().width(), 1)
        columns = max(width // self.CELL_WIDTH, 1)
        self.setGridSize(QSize(max(width // columns, 1), self.CELL_HEIGHT))

    def set_external_drop_row(self, row: int | None) -> None:
        row = None if row is None else max(0, min(int(row), self.count()))
        if row != self.external_drop_row:
            self.external_drop_row = row
            self.viewport().update()

    def uses_horizontal_slots(self) -> bool:
        """Whether successive thumbnails currently share a visual row."""
        if self.count() > 1:
            first = self.visualItemRect(self.item(0))
            second = self.visualItemRect(self.item(1))
            return abs(first.center().y() - second.center().y()) < \
                max(first.height(), second.height()) / 2
        return self.viewport().width() >= self.CELL_WIDTH * 2

    def drop_indicator_line(self, row: int):
        """The visible slot for an external page drop, in viewport pixels."""
        if not self.count():
            return QPointF(6, 6), QPointF(max(self.viewport().width() - 6, 6), 6)
        if not self.uses_horizontal_slots():
            reference = self.visualItemRect(
                self.item(row if row < self.count() else self.count() - 1))
            y = reference.top() if row < self.count() else reference.bottom()
            return QPointF(reference.left() + 3, y), QPointF(reference.right() - 3, y)
        reference = self.visualItemRect(
            self.item(row if row < self.count() else self.count() - 1))
        x = reference.left() if row < self.count() else reference.right()
        return QPointF(x, reference.top() + 3), QPointF(x, reference.bottom() - 3)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.external_drop_row is None:
            return
        start, end = self.drop_indicator_line(self.external_drop_row)
        painter = QPainter(self.viewport())
        pen = QPen(QColor("#1971c2"), 3.0, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(start, end)
        painter.end()

class PagesPanel(QWidget):
    """Thumbnail strip with reordering and page commands."""

    pageSelected = Signal(int)
    # Where a run of pages was dragged to: the first of them, how many, and
    # the page number the run now starts at. A run, because a block of sheets
    # picked out together is dragged as a block.
    pagesReordered = Signal(int, int, int)

    def __init__(self, window):
        super().__init__()
        self.window = window
        # A page finished being drawn in the background: put it in its row.
        from ..io import pdftiles

        pdftiles.TILES.sheetReady.connect(self._page_was_drawn)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        buttons = QHBoxLayout()
        # Lambdas, not the bound methods: clicked() carries a "checked" bool
        # that would otherwise arrive as the page to act on.
        for label, tip, slot in (
                ("+", "Add a page", lambda: self.window.add_page()),
                ("⧉", "Duplicate the page, or the pages picked out",
                 lambda: self.window.duplicate_page(
                     self.window.selected_pages()[0]
                     if self.window.selected_pages() else None)),
                ("−", "Delete the page, or the pages picked out",
                 lambda: self.window.delete_page(
                     self.window.selected_pages()[0]
                     if self.window.selected_pages() else None))):
            button = QToolButton()
            button.setText(label)
            button.setToolTip(tip)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.list = PageListWidget()
        # Sheets are drawn as they are scrolled to rather than all at once.
        self.list.verticalScrollBar().valueChanged.connect(
            lambda _value: self._draw_what_is_on_screen())
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setIconSize(QSize(96, 128))
        self.list.setFlow(QListView.LeftToRight)
        self.list.setWrapping(True)
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Static)
        self.list.setSpacing(6)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        # The line that says where a dragged page will land. Without it a drag
        # is a guess, and a page dropped one place out has to be dragged again.
        self.list.setDropIndicatorShown(True)
        # More than one page at a time: a header taken off a run of drawing
        # sheets, or a block of pages dragged somewhere else, is one gesture
        # rather than twenty.
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.currentRowChanged.connect(self._row_changed)
        self.list.model().rowsMoved.connect(self._rows_moved)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)
        self.list.installEventFilter(self)
        # A PDF or an image dragged onto the strip goes in where the line is.
        self.list.setAcceptDrops(True)
        self.list.viewport().setAcceptDrops(True)
        self.list.dragEnterEvent = self._drag_enter
        self.list.dragMoveEvent = self._drag_move
        self.list.dragLeaveEvent = self._drag_leave
        self.list.dropEvent = self._drop
        layout.addWidget(self.list, 1)
        self._suppress = False

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

    def _drag_enter(self, event) -> None:
        if self._files_in(event):
            self.list.set_external_drop_row(
                self.drop_row(event.position().toPoint()))
            event.setDropAction(Qt.CopyAction)
            event.acceptProposedAction()
            return
        self.list.set_external_drop_row(None)
        QListWidget.dragEnterEvent(self.list, event)

    def _drag_move(self, event) -> None:
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
            return row + int(after)
        # In the gaps, find the first visual centre after the pointer rather
        # than treating every empty pixel as the end of the document.
        for row in range(self.list.count()):
            box = self.list.visualItemRect(self.list.item(row))
            if position.y() < box.top():
                return row
            if box.top() <= position.y() <= box.bottom() \
                    and position.x() < box.center().x():
                return row
        return self.list.count()

    def _drop(self, event) -> None:
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

    def eventFilter(self, watched, event):
        """Ctrl+C and Ctrl+V on the thumbnails copy and paste whole pages."""
        if watched is self.list and event.type() == QEvent.KeyPress:
            if event.matches(QKeySequence.Copy):
                self.window.copy_page(self.list.currentRow())
                return True
            if event.matches(QKeySequence.Paste):
                self.window.paste_page(self.list.currentRow())
                return True
        return super().eventFilter(watched, event)

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
        menu = self.window.page_menu(index)
        menu.exec(self.list.viewport().mapToGlobal(point))

    def _row_changed(self, row: int) -> None:
        if not self._suppress and row >= 0:
            self.pageSelected.emit(row)

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
        self.list.clear()
        for index, page in enumerate(document.pages):
            # The scale rides with the page number: what a measurement on that
            # page means depends on it, and it belongs where the page is named.
            scale = page.scale.label if page.scale.is_calibrated() else ""
            parts = [str(index + 1)]
            label = page.label.strip()
            if label and label != parts[0]:
                parts.append(label)
            if scale:
                parts.append(scale)
            caption = "   ".join(parts)
            entry = QListWidgetItem(self._thumbnail(page, document, ask=False),
                                    caption)
            entry.setTextAlignment(Qt.AlignHCenter)
            tip = page.label or page.source_note or f"Page {index + 1}"
            if not page.printable:
                entry.setForeground(QColor("#8b929c"))
                tip += "\nExcluded from print and export"
            entry.setToolTip(f"{tip}\n{page.setup.size_name} {page.setup.orientation}"
                             f"\nScale {page.scale.label}")
            self.list.addItem(entry)
        self.list.setCurrentRow(current)
        self._suppress = False
        self._draw_what_is_on_screen()

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
            if entry is None:
                continue
            # A row well below the fold is not worth a render yet. The margin
            # is a screenful, so scrolling lands on sheets already drawn.
            box = self.list.visualItemRect(entry)
            if box.bottom() < -showing.height() or \
                    box.top() > showing.height() * 2:
                continue
            entry.setIcon(self._thumbnail(document.pages[index], document))

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

    @staticmethod
    def _thumbnail(page, document=None, ask: bool = True) -> QIcon:
        """A small picture of the page for the list.

        A page that came in from a PDF is drawn once, small, in the background
        for the canvas to have something to show while its tiles arrive — so
        the list borrows that rather than rendering every page again. Opening
        a drawing set used to spend half a second here doing exactly the work
        that was already being done.
        """
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
                    return QIcon(sheet.scaled(
                        160, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                # Not drawn yet. A blank sheet of the right shape now, and the
                # row is refreshed when the picture arrives.
                tall = int(160 * page.height_pt / max(page.width_pt, 1.0))
                waiting = QPixmap(160, max(tall, 1))
                waiting.fill(Qt.white)
                return QIcon(waiting)
        scene = page.frame
        if scene is None:
            pixmap = QPixmap(96, 128)
            pixmap.fill(Qt.white)
            return QIcon(pixmap)
        image = scene.render_image(dpi=18.0, for_print=False)
        return QIcon(QPixmap.fromImage(image))


# ---------------------------------------------------------------------------
# Markups list
# ---------------------------------------------------------------------------

class MarkupsPanel(QWidget):
    """Every markup in the document, filterable and exportable — like a takeoff list.

    Pick a row and the markup is picked on the page, and the other way round:
    the list and the drawing are two views of one thing.
    """

    markupActivated = Signal(int, str)
    markupPicked = Signal(int, str)

    COLUMNS = ["Page", "Type", "Subject", "Value", "Author", "Date", "Comment"]

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
        self.filter.textChanged.connect(lambda _: self.rebuild(self.window.document))
        top.addWidget(self.filter, 1)
        export = QToolButton()
        export.setText("CSV")
        export.setToolTip("Export the markups list to CSV")
        export.clicked.connect(self.export_csv)
        top.addWidget(export)
        layout.addLayout(top)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(len(self.COLUMNS))
        self.tree.setHeaderLabels(self.COLUMNS)
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.itemDoubleClicked.connect(self._activate)
        self.tree.itemSelectionChanged.connect(self._picked)
        self.tree.header().setSectionResizeMode(QHeaderView.Interactive)
        self.tree.setSortingEnabled(True)
        layout.addWidget(self.tree, 1)
        # True while the list is being rebuilt or is following the canvas, so
        # that putting a selection into it does not send that selection
        # straight back out and fight whatever set it.
        self._echoing = False

        self.totals = QLabel("")
        self.totals.setWordWrap(True)
        self.totals.setStyleSheet("color:#4a5261; padding:2px;")
        layout.addWidget(self.totals)

    def rebuild(self, document) -> None:
        needle = self.filter.text().strip().lower()
        self._echoing = True
        sorting = self.tree.isSortingEnabled()
        self.tree.setSortingEnabled(False)
        self.tree.clear()
        rows = []
        empty = [""] * len(self.COLUMNS)
        for index, page in enumerate(document.pages):
            if page.frame is None:
                continue
            page_node = QTreeWidgetItem([f"Page {index + 1}"] + empty[1:])
            font = page_node.font(0)
            font.setBold(True)
            page_node.setFont(0, font)
            added = False
            for item in page.frame.ordered_markups():
                row = [str(index + 1), item.display_name(), item.subject,
                       getattr(item, "value_text", ""), item.author,
                       item.modified[:10], item.summary()]
                if needle and not any(needle in str(cell).lower() for cell in row):
                    continue
                node = QTreeWidgetItem(row)
                node.setData(0, Qt.UserRole, (index, item.uid))
                node.setIcon(1, icon(_icon_for(item), 16))
                if item.locked:
                    node.setForeground(1, QColor("#8b93a1"))
                page_node.addChild(node)
                rows.append(row)
                added = True
            if added or not needle:
                self.tree.addTopLevelItem(page_node)
                page_node.setExpanded(True)
        for column in range(len(self.COLUMNS)):
            self.tree.resizeColumnToContents(column)
        self.tree.setSortingEnabled(sorting)
        self._rows = rows
        self.totals.setText(self._totals_text(document))
        self._echoing = False
        self.follow_the_canvas()

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

    def _activate(self, node: QTreeWidgetItem, _column: int) -> None:
        data = node.data(0, Qt.UserRole)
        if data:
            self.markupActivated.emit(data[0], data[1])

    def _picked(self) -> None:
        """One click picks the markup on the page, as a row in a list should."""
        if self._echoing:
            return
        for node in self.tree.selectedItems():
            data = node.data(0, Qt.UserRole)
            if data:
                self.markupPicked.emit(data[0], data[1])
                return

    def follow_the_canvas(self) -> None:
        """Pick out the rows for whatever is selected on the page.

        The list and the drawing are two views of one thing, so picking a
        markup on either should show it on the other.
        """
        scene = self.window.view.scene() if self.window.view else None
        wanted = {item.uid for item in scene.selectedItems()} if scene else set()
        self._echoing = True
        try:
            first = None
            for index in range(self.tree.topLevelItemCount()):
                parent = self.tree.topLevelItem(index)
                for child in range(parent.childCount()):
                    node = parent.child(child)
                    data = node.data(0, Qt.UserRole)
                    chosen = bool(data) and data[1] in wanted
                    node.setSelected(chosen)
                    if chosen and first is None:
                        first = node
            if first is not None:
                self.tree.scrollToItem(first)
        finally:
            self._echoing = False

    def export_csv(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "Export markups", "markups.csv",
                                              "CSV files (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(self.COLUMNS)
            writer.writerows(getattr(self, "_rows", []))
        QMessageBox.information(self, "Export markups", f"Saved {path}")


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

        buttons = QHBoxLayout()
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
        buttons.addStretch(1)
        layout.addLayout(buttons)

    # -- display -----------------------------------------------------------
    def rebuild(self, document=None) -> None:
        document = document or self.window.document
        self.tree.clear()
        for mark, index in document.contents_entries():
            node = QTreeWidgetItem([("    " * mark.level) + mark.title,
                                    str(index + 1)])
            node.setData(0, Qt.UserRole, mark)
            self.tree.addTopLevelItem(node)

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
            mark.title = title.strip()
            self.window.bookmarks_changed()

    def remove(self) -> None:
        mark = self._selected()
        if mark is None:
            return
        self.window.document.bookmarks.remove(mark)
        self.window.bookmarks_changed()

    def insert_contents(self) -> None:
        self.window.insert_contents_block()


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

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.groups: list = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIconSize(QSize(48, 34))
        self.tree.setRootIsDecorated(True)
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
        layout.addWidget(self.tree, 1)

        self.hint = QLabel("")
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color:#6b7280;")
        layout.addWidget(self.hint)

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
        self.groups = toolsets.load_toolsets()
        self.tree.blockSignals(True)
        self.tree.clear()
        for group in self.groups:
            header = QTreeWidgetItem([f"{group.name}  ({len(group.entries)})"])
            header.setData(0, self.SET_ROLE, group.name)
            header.setData(0, self.ENTRY_ROLE, -1)
            header.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            font = header.font(0)
            font.setBold(True)
            header.setFont(0, font)
            self.tree.addTopLevelItem(header)
            self._fill(header, group)
            header.setExpanded(group.name not in rolled)
        self.tree.blockSignals(False)
        if wanted:
            self.show_set(wanted)
        self.refresh_buttons()

    def _fill(self, header, group) -> None:
        from . import toolsets

        numbered = group.name == toolsets.MY_TOOLS
        for position, entry in enumerate(group.entries):
            prefix = f"{position + 1}.  " if numbered and position < 9 else ""
            mode_tag = "  · Property" if entry.mode == toolsets.PROPERTIES else ""
            row = QTreeWidgetItem([f"{prefix}{entry.label}{mode_tag}"])
            row.setIcon(0, QIcon(entry_thumbnail(entry)))
            row.setData(0, self.SET_ROLE, group.name)
            row.setData(0, self.ENTRY_ROLE, position)
            row.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
            row.setToolTip(0,
                           "Put back exactly what was added" if entry.mode == toolsets.COPY
                           else "Draw a new one with these properties")
            header.addChild(row)

    def rebuild_entries(self) -> None:
        """Redraw the rows of the set that is open, keeping where you were."""
        name = self.current_set_name()
        self.rebuild(keep=name)

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
        if row is None or row.data(0, self.ENTRY_ROLE) in (None, -1):
            return
        self.use_selected()

    def use_selected(self) -> None:
        entry = self.current_entry()
        if entry is not None:
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
        entry = self.current_entry()
        group = self.current_set()
        if entry is not None:
            menu.addAction("Use", self.use_selected)
            draw = menu.addAction("Property mode", self.toggle_mode)
            draw.setCheckable(True)
            draw.setChecked(entry.mode == toolsets.PROPERTIES)
            draw.setEnabled(toolsets.can_be_properties(entry.payload))
            draw.setToolTip("Draw a fresh markup using this stored style")
            if not draw.isEnabled():
                draw.setToolTip("This one only makes sense put back as it was")
            menu.addAction("Rename…", self.rename_entry)
            menu.addAction("Remove", self.remove_entry)
            menu.addSeparator()
        if group is not None:
            add = menu.addAction("Add selection", self.add_selection)
            add.setToolTip(f"Keep what is selected on the page in “{group.name}”")
            rename = menu.addAction("Rename set…", self.rename_set)
            rename.setToolTip(f"Rename “{group.name}”")
            delete = menu.addAction("Delete set", self.delete_set)
            delete.setToolTip(f"Delete “{group.name}” and everything in it")
            menu.addSeparator()
        menu.addAction("New tool set…", self.new_set)
        imported = menu.addAction("Import tools…", self.import_set)
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


def entry_thumbnail(entry, width: int = 48, height: int = 34) -> QPixmap:
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
                (height - 2 * margin) / bounds.height(), 1.6)
    painter.translate(width / 2, height / 2)
    painter.scale(scale, scale)
    painter.translate(-bounds.center())
    for item in items:
        painter.save()
        painter.translate(item.pos())
        try:
            item.paint_content(painter)
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
            "note": "note", "stamp": "stamp", "image": "image",
            "measure": "measure_length",
            "count": "count", "contents": "page"}.get(type_name, "select")


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

class PropertiesPanel(QScrollArea):
    """Context-sensitive editor for whatever is selected."""

    changed = Signal(str)

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self._items: list[MarkupItem] = []
        self._building = False
        self.body = QWidget()
        self.setWidget(self.body)
        self.layout = QVBoxLayout(self.body)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(8)
        self.show_items([])

    # -- construction ------------------------------------------------------
    def show_items(self, items: list[MarkupItem]) -> None:
        self._items = [i for i in items if isinstance(i, MarkupItem)]
        self._building = True
        while self.layout.count():
            child = self.layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                # Hide before unparenting, then unparent before deleting:
                # deleteLater() only runs on the next trip through the event
                # loop, so until then an old child would keep painting over its
                # replacement — and a *visible* widget given no parent becomes a
                # floating top-level window.
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        if not self._items:
            hint = QLabel("Nothing selected.\n\nPick a markup on the page to edit its "
                          "appearance, or choose a tool to draw a new one.")
            hint.setWordWrap(True)
            hint.setStyleSheet("color:#6b7280;")
            self.layout.addWidget(hint)
            self.layout.addStretch(1)
            self._settle()
            self._building = False
            return

        first = self._items[0]
        heading = QLabel(first.display_name() if len(self._items) == 1
                         else f"{len(self._items)} markups selected")
        font = heading.font()
        font.setBold(True)
        heading.setFont(font)
        self.layout.addWidget(heading)

        appearance = common_capabilities(self._items)
        if appearance - {"font"}:
            self._add_appearance(first, appearance)
        if all(getattr(i, "HAS_TEXT", False) or isinstance(i, StampItem)
               for i in self._items):
            self._add_text(first)
        if all(isinstance(i, (PolyItem, MeasureItem, CalloutItem)) for i in self._items):
            self._add_arrows(first)
        if len(self._items) == 1:
            if isinstance(first, MeasureItem):
                self._add_measure(first)
            elif isinstance(first, CountItem):
                self._add_count(first)
            elif isinstance(first, StampItem):
                self._add_stamp(first)
            elif isinstance(first, ContentsItem):
                self._add_contents(first)
            elif isinstance(first, NoteItem):
                self._add_note(first)
            elif isinstance(first, ImageItem):
                self._add_image(first)
            elif isinstance(first, RectItem) and first.kind in ("rect", "ellipse"):
                self._add_size(first)
            elif isinstance(first, RectItem) and first.kind == "cloud":
                self._add_cloud(first)
            elif isinstance(first, PolyItem) and first.kind == "cloud":
                self._add_cloud(first)
        if len(self._items) == 1:
            self._add_geometry(first)
        self._add_metadata(first)
        if len(self._items) == 1:
            self._add_defaults(first)
        self.layout.addStretch(1)
        self._settle()
        self._building = False

    def _settle(self) -> None:
        """Re-lay-out the rebuilt form and scroll back to the top.

        Without this the scroll area keeps the geometry of the *previous*
        selection for one more event loop turn, which leaves the panel showing
        empty space below content that is no longer there.
        """
        self.layout.activate()
        self.body.adjustSize()
        self.verticalScrollBar().setValue(0)
        self.horizontalScrollBar().setValue(0)

    def _group(self, title: str) -> QFormLayout:
        box = QGroupBox(title)
        form = QFormLayout(box)
        form.setContentsMargins(8, 8, 8, 8)
        form.setSpacing(5)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.layout.addWidget(box)
        return form

    def _apply(self, setter, description: str, coalesce: bool = False) -> None:
        """Change every selected item, and record one undo step for it.

        *coalesce* is for the controls that send a value continuously — a
        slider being dragged, a spin box being held down. Those belong in the
        undo history as the one change they are, not as every value passed
        through on the way.
        """
        if self._building:
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

    def _slide(self, setter, description: str) -> None:
        """A change from a slider or a spin box: part of one continuous run."""
        self._apply(setter, description, coalesce=True)

    def _add_geometry(self, item) -> None:
        """Where it is, how big it is and which way it is turned — as numbers.

        Dragging is fine for most things and useless for the rest: a detail
        that has to start exactly 40 mm in, or two boxes that have to be the
        same width, are typed rather than nudged. The numbers are in
        millimetres because that is what the page is set up in, and they are
        measured from the top-left corner of the paper.
        """
        from ..core.document import MM_TO_PT, PT_TO_MM

        form = self._group("Position and size")
        rect = item.local_rect().normalized()
        rows = [
            ("X", item.pos().x(), lambda i, v: i.setPos(v, i.pos().y()), False),
            ("Y", item.pos().y(), lambda i, v: i.setPos(i.pos().x(), v), False),
        ]
        if item.RESIZABLE and rect.width() > 0 and rect.height() > 0:
            rows += [
                ("Width", rect.width(), self._set_width, True),
                ("Height", rect.height(), self._set_height, True),
            ]
        for label, value, setter, is_size in rows:
            box = QDoubleSpinBox()
            box.setRange(0.1 if is_size else -20000.0, 20000.0)
            box.setDecimals(1)
            box.setSuffix(" mm")
            box.setSingleStep(1.0)
            box.setValue(value * PT_TO_MM)
            box.setToolTip(f"{value:.1f} pt")
            box.valueChanged.connect(
                lambda millimetres, apply=setter:
                self._slide(lambda i: apply(i, millimetres * MM_TO_PT),
                            "Position and size"))
            form.addRow(label, box)

        if item.ROTATABLE:
            turn = QDoubleSpinBox()
            turn.setRange(-360.0, 360.0)
            turn.setDecimals(1)
            turn.setSuffix("°")
            turn.setWrapping(True)
            turn.setValue(item.rotation())
            turn.valueChanged.connect(
                lambda angle: self._slide(lambda i: i.set_item_rotation(angle),
                                          "Rotation"))
            form.addRow("Rotation", turn)

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
        form = self._group("Appearance")

        if controls == {OPACITY}:
            opacity = LabeledSlider(5, 100, int(first.style.opacity * 100))
            opacity.valueChanged.connect(
                lambda value: self._slide(
                    lambda i: setattr(i.style, "opacity", value), "Opacity"))
            form.addRow("Opacity", opacity)
            return

        if STROKE in controls:
            stroke = ColorButton(first.style.stroke, allow_none=True, label="Line colour")
            stroke.colorChanged.connect(
                lambda colour: self._apply(
                    lambda i: setattr(i.style, "stroke", colour), "Line colour"))
            form.addRow("Line", stroke)

        if FILL in controls:
            fill = ColorButton(first.style.fill, allow_none=True, label="Fill colour")
            fill.colorChanged.connect(
                lambda colour: self._apply(
                    lambda i: setattr(i.style, "fill", colour), "Fill colour"))
            form.addRow("Fill", fill)

        if WIDTH in controls:
            width = QDoubleSpinBox()
            width.setRange(0.0, 40.0)
            width.setSingleStep(0.25)
            width.setDecimals(2)
            width.setValue(first.style.width)
            width.setSuffix(" pt")
            width.valueChanged.connect(
                lambda value: self._slide(
                    lambda i: setattr(i.style, "width", value), "Line width"))
            form.addRow("Thickness", width)

        if DASH in controls:
            line_style = QComboBox()
            line_style.setObjectName("lineStyle")
            line_style.setIconSize(QSize(76, 22))
            for name in DASH_ARRAYS:
                line_style.addItem(
                    _line_style_icon(name, first.style.stroke, first.style.width),
                    name, name)
            line_style.setCurrentIndex(
                max(line_style.findData(first.style.line_style), 0))
            line_style.currentIndexChanged.connect(
                lambda _index: self._apply(
                    lambda i: (setattr(i.style, "line_style", line_style.currentData()),
                               setattr(i.style, "dash_array", ())),
                    "Line style"))
            form.addRow("Style", line_style)

        # A hatch over the fill: how a section reads as concrete or as steel,
        # and what a Bluebeam tool set full of sections needs to come in with.
        if HATCH in controls:
            hatch = QComboBox()
            hatch.setObjectName("hatchPattern")
            hatch.setIconSize(QSize(76, 22))
            hatch_colour = first.style.fill or first.style.stroke
            for name in HATCH_PATTERNS:
                hatch.addItem(_hatch_icon(name, hatch_colour), name or "plain", name)
            hatch.setCurrentIndex(max(hatch.findData(first.style.hatch or ""), 0))
            hatch.currentIndexChanged.connect(
                lambda _index: self._apply(
                    lambda i: setattr(i.style, "hatch", hatch.currentData()),
                                          "Hatch"))
            form.addRow("Hatch", hatch)

        if OPACITY in controls:
            opacity = LabeledSlider(5, 100, int(first.style.opacity * 100))
            opacity.valueChanged.connect(
                lambda value: self._slide(
                    lambda i: setattr(i.style, "opacity", value), "Opacity"))
            form.addRow("Opacity", opacity)

        if FILL_OPACITY in controls:
            fill_opacity = LabeledSlider(0, 100, int(first.style.fill_opacity * 100))
            fill_opacity.valueChanged.connect(
                lambda value: self._slide(
                    lambda i: setattr(i.style, "fill_opacity", value),
                    "Fill opacity"))
            form.addRow("Fill opacity", fill_opacity)


    def _add_text(self, first: MarkupItem) -> None:
        form = self._group("Text")
        family = QFontComboBox()
        family.setCurrentFont(QFont(first.style.font_family))
        family.currentFontChanged.connect(
            lambda font: self._apply(lambda i: setattr(i.style, "font_family", font.family()),
                                     "Font"))
        form.addRow("Font", family)

        size = QDoubleSpinBox()
        size.setRange(3.0, 96.0)
        size.setSingleStep(0.5)
        size.setValue(first.style.font_size)
        size.setSuffix(" pt")
        size.valueChanged.connect(
            lambda value: self._slide(lambda i: setattr(i.style, "font_size", value), "Font size"))
        form.addRow("Size", size)

        row = QHBoxLayout()
        for label, attribute in (("B", "bold"), ("I", "italic"), ("U", "underline")):
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setChecked(getattr(first.style, attribute))
            button.toggled.connect(
                lambda on, a=attribute: self._apply(lambda i: setattr(i.style, a, on), "Font style"))
            row.addWidget(button)
        row.addStretch(1)
        holder = QWidget()
        holder.setLayout(row)
        form.addRow("Weight", holder)

        colour = ColorButton(first.style.text_color, label="Text colour")
        colour.colorChanged.connect(
            lambda value: self._apply(lambda i: setattr(i.style, "text_color", value),
                                      "Text colour"))
        form.addRow("Colour", colour)

        align = QComboBox()
        align.addItems(["left", "center", "right", "justify"])
        align.setCurrentText(first.style.align)
        align.currentTextChanged.connect(
            lambda value: self._apply(lambda i: setattr(i.style, "align", value), "Alignment"))
        form.addRow("Align", align)

        valign = QComboBox()
        valign.addItems(["top", "middle", "bottom"])
        valign.setCurrentText(first.style.valign)
        valign.currentTextChanged.connect(
            lambda value: self._apply(lambda i: setattr(i.style, "valign", value), "Alignment"))
        form.addRow("Vertical", valign)

    def _add_arrows(self, first: MarkupItem) -> None:
        """What the ends of a line carry.

        A callout's leader has one end that means anything — the one pointing
        at the thing — so it is offered that and nothing else. Asking which
        arrow head goes on the end joined to the box is a question with no
        useful answer.
        """
        if isinstance(first, CalloutItem):
            form = self._group("Leader")
            head = QComboBox()
            head.addItems(ARROW_HEADS)
            head.setCurrentText(first.style.arrow_end)
            head.currentTextChanged.connect(
                lambda value: self._apply(
                    lambda i: setattr(i.style, "arrow_end", value), "Arrow head"))
            form.addRow("Arrow head", head)
            shape = QComboBox()
            shape.addItems(["Box", "Cloud"])
            shape.setCurrentIndex(1 if first.shape_kind == "cloud" else 0)
            shape.currentIndexChanged.connect(
                lambda index: self._apply(
                    lambda i: setattr(i, "shape_kind", "cloud" if index else "box"),
                    "Callout shape"))
            form.addRow("Drawn as", shape)
            if first.leaders and not first.clouds_a_region():
                stand_off = QDoubleSpinBox()
                stand_off.setRange(first.LEAST_REACH, 400.0)
                stand_off.setDecimals(0)
                stand_off.setSuffix(" pt")
                stand_off.setValue(first.leaders[0].reach)
                stand_off.setToolTip(
                    "How far the hinge stands off the box before the line "
                    "turns towards\nwhat it points at. Dragging the hinge "
                    "does the same thing.")
                stand_off.valueChanged.connect(
                    lambda value: self._slide(
                        lambda i: setattr(i, "elbow_reach", value),
                        "Leader stand-off"))
                form.addRow("Hinge", stand_off)
                count = QLabel(f"{len(first.leaders)}"
                               + (" arrow" if len(first.leaders) == 1
                                  else " arrows"))
                count.setToolTip("Right-click the call-out to add another, or "
                                 "to take one away")
                form.addRow("Leaders", count)
            return
        form = self._group("Ends")
        start = QComboBox()
        start.addItems(ARROW_HEADS)
        start.setCurrentText(first.style.arrow_start)
        start.currentTextChanged.connect(
            lambda value: self._apply(lambda i: setattr(i.style, "arrow_start", value), "Arrow"))
        form.addRow("Start", start)
        end = QComboBox()
        end.addItems(ARROW_HEADS)
        end.setCurrentText(first.style.arrow_end)
        end.currentTextChanged.connect(
            lambda value: self._apply(lambda i: setattr(i.style, "arrow_end", value), "Arrow"))
        form.addRow("End", end)

    def _add_size(self, item) -> None:
        """What a rectangle or an ellipse measures, and whether it says so.

        The size lives here rather than being written across the drawing:
        a shape drawn on a plan is a shape, and a page of shapes each carrying
        their dimensions is unreadable. The tick puts it on the shape for
        anyone who wants it there.
        """
        form = self._group("Size")
        item.refresh(page=self.window.current_page())
        value = QLabel(item.size_text or "—")
        font = value.font()
        font.setBold(True)
        value.setFont(font)
        form.addRow("It is", value)

        exact = QPushButton("Exact size…")
        exact.setToolTip("Set the scaled width and height or diameters")
        exact.clicked.connect(lambda: self.window.set_rectangle_size(item))
        form.addRow("", exact)

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
        heading.textEdited.connect(
            lambda text: self._apply(lambda i: setattr(i, "title", text), "Heading"))
        form.addRow("Heading", heading)

        for label, attribute in (("Page numbers", "show_page_numbers"),
                                 ("Leader dots", "leader_dots")):
            box = QCheckBox(label)
            box.setChecked(getattr(item, attribute))
            box.toggled.connect(
                lambda on, a=attribute: self._apply(
                    lambda i: setattr(i, a, on), "Contents"))
            form.addRow("", box)

        height = QDoubleSpinBox()
        height.setRange(8.0, 60.0)
        height.setValue(item.row_height)
        height.setSuffix(" pt")
        height.valueChanged.connect(
            lambda value: self._slide(
                lambda i: setattr(i, "row_height", value), "Contents"))
        form.addRow("Line spacing", height)

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
        body.textChanged.connect(
            lambda: self._apply(lambda i: setattr(i, "comment", body.toPlainText()),
                                "Note text"))
        form.addRow(body)

    def _add_image(self, item) -> None:
        form = self._group("Image")
        replace = QPushButton("Replace image…")
        replace.clicked.connect(lambda: self.window.replace_image(item))
        form.addRow("", replace)
        keep = QCheckBox("Keep its proportions")
        keep.setChecked(item.keep_aspect)
        keep.toggled.connect(
            lambda on: self._apply(lambda i: setattr(i, "keep_aspect", on),
                                   "Image"))
        form.addRow("", keep)
        colours = QPushButton("Change colours…")
        colours.clicked.connect(lambda: self.window.recolour_item(item))
        form.addRow("", colours)

    def _add_cloud(self, first) -> None:
        form = self._group("Cloud")
        radius = QDoubleSpinBox()
        radius.setRange(2.0, 60.0)
        radius.setValue(first.cloud_radius)
        radius.setSuffix(" pt")
        radius.valueChanged.connect(
            lambda value: self._slide(lambda i: setattr(i, "cloud_radius", value), "Cloud size"))
        form.addRow("Arc size", radius)




    def _add_measure(self, item: MeasureItem) -> None:
        form = self._group("Measurement")
        value = QLabel(item.value_text or "—")
        font = value.font()
        font.setBold(True)
        value.setFont(font)
        form.addRow("Value", value)

        subject = QLineEdit(item.subject)
        subject.setToolTip("Measurements sharing a subject are totalled in the markups list")
        subject.textEdited.connect(
            lambda text: self._apply(lambda i: setattr(i, "subject", text), "Subject"))
        form.addRow("Counts as", subject)

        if item.kind in ("area", "volume", "perimeter"):
            unit = UnitCombo(self.window.current_page().scale.area_unit)
            unit.currentTextChanged.connect(self.window.set_area_unit)
            form.addRow("Area unit", unit)
        if item.kind == "volume":
            depth = QLineEdit(item.depth_text)
            depth.setPlaceholderText("e.g. 150 mm")
            depth.textEdited.connect(
                lambda text: self._apply(
                    lambda i: (setattr(i, "depth_text", text),
                               i.refresh(page=self.window.current_page())), "Depth"))
            form.addRow("Depth", depth)

        words = QLineEdit(item.custom_label)
        words.setPlaceholderText(item.measured_text or "the measured value")
        words.setToolTip("What this says on the drawing. Leave it empty and it "
                         "shows what it measured.")
        words.editingFinished.connect(
            lambda: self._apply(
                lambda i: (setattr(i, "custom_label", words.text().strip()),
                           i.refresh(page=self.window.current_page())),
                "Measurement text"))
        form.addRow("Says", words)

        inline = QCheckBox("Inline text")
        inline.setToolTip("Keep the measurement text in line with its line")
        inline.setChecked(item.label_angle is None)
        inline.toggled.connect(
            lambda on: self._apply(
                lambda i: setattr(i, "label_angle", None if on else 0.0),
                "Text angle"))
        form.addRow("", inline)

        label = QCheckBox("Show value")
        label.setToolTip("Write the measurement on the page beside its line")
        label.setChecked(item.show_label)
        label.toggled.connect(
            lambda on: self._apply(lambda i: setattr(i, "show_label", on), "Label"))
        form.addRow("", label)

        calibrate = QPushButton("Calibrate scale…")
        calibrate.setToolTip("Pick a known distance on this page and enter its length")
        calibrate.clicked.connect(lambda: self.window.calibrate_dialog())
        form.addRow("", calibrate)

    def _add_count(self, item: CountItem) -> None:
        form = self._group("Count")
        subject = QLineEdit(item.subject)
        subject.textEdited.connect(
            lambda text: self._apply(lambda i: setattr(i, "subject", text), "Count subject"))
        form.addRow("Subject", subject)
        symbol = QComboBox()
        symbol.addItems(list(CountItem.SYMBOLS))
        symbol.setCurrentText(item.symbol)
        symbol.currentTextChanged.connect(
            lambda value: self._apply(lambda i: setattr(i, "symbol", value), "Count symbol"))
        form.addRow("Symbol", symbol)
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
        form.addRow("Text", preset)
        subtext = QLineEdit(item.subtext)
        subtext.setPlaceholderText("Name, date, revision…")
        subtext.textEdited.connect(
            lambda text: self._apply(lambda i: setattr(i, "subtext", text), "Stamp"))
        form.addRow("Sub-text", subtext)

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
        """Keep this one's look for the next one of its kind, or add it to a set."""
        from . import toolsets

        form = self._group("Defaults")
        note = QLabel("Set how it is now as the way new ones are drawn, or keep "
                      "the whole thing in a tool set to use again.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#6b7280;")
        form.addRow(note)

        default = QPushButton("Set default")
        default.setToolTip("New markups of this kind will be drawn like this one")
        default.clicked.connect(lambda: self.window.set_as_default(first))
        form.addRow("", default)

        if toolsets.default_key(first) in toolsets.load_defaults():
            forget = QPushButton("Forget default")
            forget.setToolTip("Restore the original defaults for this markup kind")
            forget.clicked.connect(lambda: self._forget_default(first))
            form.addRow("", forget)

        add = QPushButton("Add tool…")
        add.setToolTip("Keep this markup, contents and all, to put down again")
        add.clicked.connect(lambda: self.window.add_to_toolset(first))
        form.addRow("", add)

    def _forget_default(self, item: MarkupItem) -> None:
        from . import toolsets

        toolsets.forget_default(toolsets.default_key(item))
        self.window.status_hint.setText(
            f"New {item.display_name().lower()}s are back to their original look")
        self.show_items(self._items)

    def _add_metadata(self, first: MarkupItem) -> None:
        form = self._group("Details")
        label = QLineEdit(first.label)
        label.textEdited.connect(
            lambda text: self._apply(lambda i: setattr(i, "label", text), "Label"))
        form.addRow("Label", label)

        author = QLineEdit(first.author)
        author.textEdited.connect(
            lambda text: self._apply(lambda i: setattr(i, "author", text), "Author"))
        form.addRow("Author", author)

        comment = QPlainTextEdit(first.comment)
        comment.setFixedHeight(58)
        comment.textChanged.connect(
            lambda: self._apply(lambda i: setattr(i, "comment", comment.toPlainText()), "Comment"))
        form.addRow("Comment", comment)

        locked = QCheckBox("Locked")
        locked.setChecked(first.locked)
        locked.toggled.connect(
            lambda on: self._apply(lambda i: i.set_locked(on), "Lock"))
        form.addRow("", locked)

        printable = QCheckBox("Print")
        printable.setToolTip("Include this markup when the page is printed")
        printable.setChecked(first.printable)
        printable.toggled.connect(
            lambda on: self._apply(lambda i: setattr(i, "printable", on), "Print flag"))
        form.addRow("", printable)
