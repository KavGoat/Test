"""Excel's sheet tabs, under the canvas, in the workbook view: the sheets of
the workbook shown, in reading order, with + for a new sheet and × at the
end to go back to the pages (ui/sheetview.py; the user, 2026-10-22: "like
Excel, when I click a workbook it opens a [spreadsheet] with tabs at the
bottom"). Tables have none (the user, 2026-10-11: "Tables don't need tabs").

Whether the strip shows has one answer, asked afresh on every change that
could alter it (a page gone to, the pages rebuilt, undo, a document tab or a
pane changed, a file opened): its own view's canvas is showing a sheet alone
(``scene.sheet_view``). Nothing else turns it on or off (the user,
2026-10-22: "I could see workbook tabs when not in a workbook").

Excel's row (docs/qa/excel_audit.md, A1–A2, C1–C4): ◀ ▶ to scroll the
tabs (Ctrl+click to the first or last, right-click for a list of every
sheet), the tabs, ⊕ for a new sheet after the last, the × back to the
pages, and the splitter at the scroll bar's left: the tabs take
``tab_ratio`` of the row (Excel's TabRatio, 0.6 to start), dragged to give
the tabs or the scroll bar more room and kept with the workbook (read from
an Excel file's ``workbookView/@tabRatio``).

A click goes to that sheet, the tab of the sheet shown is the current one,
a double-click renames it on the tab, a tab dragged along moves the sheet's
run of pages, and ⊕ adds a new sheet at the end of the workbook.
Right-click (or a long press, for touch) a tab for its menu: Print, ticked
while the sheet prints, is Print / Don't Print for the sheet; a sheet that
doesn't print has a grey tab with a crossed-out printer.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLineEdit, QMenu, QSizePolicy,
                               QTabBar, QToolButton, QWidget)

#: How long a press on a tab is held before it opens the tab's menu (touch).
LONG_PRESS_MS = 550

#: Excel's TabRatio to start with: the tabs 60 % of the row, the scroll bar 40 %.
TAB_RATIO = 0.6

#: The scroll bar keeps at least this much of the row (px), the tabs their splitter.
MIN_BAR = 24



def no_print_pixmap(size: int = 16, ratio: float = 1.0, ink: Optional[str] = None) -> QPixmap:
    """A printer crossed out in red: a sheet or page that doesn't print.
    *ink*: the printer's colour (the theme's ink when not given)."""
    if ink is None:
        from ..app import current_theme
        from ..theme import tokens
        ink = tokens(current_theme())["ink"]
    picture = QPixmap(int(size * ratio), int(size * ratio))
    picture.setDevicePixelRatio(ratio)
    picture.fill(Qt.transparent)
    painter = QPainter(picture)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.scale(size / 24.0, size / 24.0)
    painter.setPen(QPen(QColor(ink), 1.6))
    painter.setBrush(Qt.NoBrush)
    painter.drawRect(QRectF(4, 9, 16, 7))           # the printer, as the Print icon
    painter.drawRect(QRectF(7, 3, 10, 6))
    painter.drawRect(QRectF(7, 14, 10, 7))
    painter.setPen(QPen(QColor("#c92a2a"), 2.6, Qt.SolidLine, Qt.RoundCap))
    painter.drawLine(QPointF(3.5, 20.5), QPointF(20.5, 3.5))
    painter.end()
    return picture


class _TabBar(QTabBar):
    """The tabs, a sheet that doesn't print drawn greyed out."""

    def __init__(self, owner: "SheetTabs"):
        super().__init__()
        self.owner = owner

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        greyed = [i for i in range(self.count()) if not self.owner.prints(i)]
        if not greyed:
            return
        from ..app import current_theme
        from ..theme import tokens
        wash = QColor(tokens(current_theme())["chrome"])
        wash.setAlpha(150)
        painter = QPainter(self)
        for i in greyed:
            # the sheet shown keeps more of its tab, so it reads as the current one
            wash.setAlpha(90 if i == self.currentIndex() else 150)
            painter.fillRect(self.tabRect(i), wash)
        painter.end()


class _Clip(QWidget):
    """The part of the tab bar in sight: the bar laid out whole inside it,
    moved along by ◀ ▶ (Excel's tabs scroll a tab at a time)."""

    def __init__(self, bar: QTabBar):
        super().__init__()
        self.bar = bar
        bar.setParent(self)
        self.offset = 0
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

    def sizeHint(self) -> QSize:
        return self.bar.sizeHint()

    def minimumSizeHint(self) -> QSize:
        return QSize(0, self.bar.sizeHint().height())

    def place(self) -> None:
        hint = self.bar.sizeHint()
        self.bar.setGeometry(-self.offset, 0, max(hint.width(), 1), self.height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.place()


class _Splitter(QWidget):
    """Excel's splitter between the tabs and the scroll bar: three dots,
    the double-headed arrow, dragged to share the row out."""

    def __init__(self, owner: "SheetTabs"):
        super().__init__()
        self.owner = owner
        self.setObjectName("sheetTabSplitter")
        self.setFixedWidth(7)
        self.setCursor(QCursor(Qt.SplitHCursor))
        self.setToolTip("Drag to give the sheet tabs or the scroll bar more room")
        self._dragging = False

    def paintEvent(self, event) -> None:
        from ..app import current_theme
        from ..theme import tokens
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(tokens(current_theme())["ink_soft"]))
        x, y = self.width() / 2.0, self.height() / 2.0
        for k in (-4, 0, 4):
            painter.drawEllipse(QPointF(x, y + k), 1.1, 1.1)
        painter.end()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging = True
            # where it was pressed, along the row, and on the screen: the
            # splitter moves under the pointer as it is dragged
            row = self.owner._row
            start = self.mapTo(row, event.position().toPoint()).x() if row is not None else 0
            self._from = (float(start), event.globalPosition().x())
            event.accept()

    _from = (0.0, 0.0)

    def _row_x(self, event) -> float:
        start, screen = self._from
        return start + event.globalPosition().x() - screen

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self.owner.drag_ratio(self._row_x(event))
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging and event.button() == Qt.LeftButton:
            self._dragging = False
            self.owner.drag_ratio(self._row_x(event))
            self.owner.keep_ratio()
            event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        # Excel: a double-click puts the split back where it starts
        self.owner.set_ratio(TAB_RATIO)
        self.owner.keep_ratio()
        event.accept()


class SheetTitle(QWidget):
    """The workbook view's title strip, over the grid: the sheet's name in
    bold (after its workbook's, for one brought in from Excel), as a table's
    name tag says whose cells they are, and the × back to the pages at its
    right."""

    def __init__(self, close_button: QToolButton):
        super().__init__()
        from PySide6.QtWidgets import QLabel
        self.setObjectName("sheetTitle")
        self.setAttribute(Qt.WA_StyledBackground, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 1, 2, 1)
        layout.setSpacing(6)
        self.book = QLabel()
        self.book.setObjectName("sheetTitleBook")
        self.sheet = QLabel()
        self.sheet.setObjectName("sheetTitleSheet")
        bold = self.sheet.font()
        bold.setBold(True)
        self.sheet.setFont(bold)
        self.sheet.setTextInteractionFlags(Qt.NoTextInteraction)
        layout.addWidget(self.book)
        layout.addWidget(self.sheet)
        layout.addStretch(1)
        layout.addWidget(close_button)
        self.hide()

    def show_names(self, book: str, sheet: str) -> None:
        self.book.setText(f"{book}  ▸" if book else "")
        self.book.setVisible(bool(book))
        self.sheet.setText(sheet)
        self.setToolTip(f"{book} ▸ {sheet}" if book else sheet)


class SheetTabs(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setObjectName("sheetTabs")
        self.entries: list = []                 # (run uid, name) of the workbook listed
        self.section_key: Optional[str] = None  # the workbook listed (its first run)
        self.showing = False                    # whether a sheet is shown alone
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 0, 0)
        layout.setSpacing(2)
        # its width is its share of the row (tab_ratio), set as the row is
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._ratio: Optional[float] = None      # while the splitter is dragged
        self._row = None                         # the row it shares with the scroll bar
        # Excel's tab-scroll arrows, at the left, always there
        self.back = self._arrow(Qt.LeftArrow, "sheetTabsBack",
                                "Scroll the tabs left (Ctrl+click: the first sheet; "
                                "right-click: every sheet)", -1)
        self.forth = self._arrow(Qt.RightArrow, "sheetTabsForth",
                                 "Scroll the tabs right (Ctrl+click: the last sheet; "
                                 "right-click: every sheet)", 1)
        self.add = QToolButton()
        self.add.setObjectName("sheetTabsNew")
        self.add.setText("⊕")
        self.add.setAutoRaise(True)
        self.add.setToolTip("New sheet (a spreadsheet page at the end of this workbook)")
        self.add.clicked.connect(lambda: self.new_sheet())
        self.bar = _TabBar(self)
        self.bar.setMovable(True)
        self.bar.setDrawBase(False)
        self.bar.setExpanding(False)
        self.bar.setElideMode(Qt.ElideNone)
        self.bar.setUsesScrollButtons(False)       # its own ◀ ▶, at the left
        self.clip = _Clip(self.bar)
        self.first_shown = 0                       # the first tab in sight
        self.bar.setShape(QTabBar.RoundedSouth)
        self.bar.setContextMenuPolicy(Qt.CustomContextMenu)
        self.bar.tabBarClicked.connect(self._clicked)
        self.bar.tabBarDoubleClicked.connect(self._rename)
        self.bar.tabMoved.connect(self._moved)
        self.bar.customContextMenuRequested.connect(self._menu)
        # a long press opens the menu too, for a finger (no right button)
        self._press: Optional[QPoint] = None
        self._long = QTimer(self)
        self._long.setSingleShot(True)
        self._long.setInterval(LONG_PRESS_MS)
        self._long.timeout.connect(self._long_pressed)
        self.bar.installEventFilter(self)
        self.popup: Optional[QMenu] = None
        # Excel has none: the way back to the pages (the page you came from)
        self.close_button = QToolButton()
        self.close_button.setObjectName("sheetViewClose")
        self.close_button.setText("×")
        self.close_button.setAutoRaise(True)
        self.close_button.setToolTip("Close Workbook — back to the pages, where you were")
        self.close_button.clicked.connect(self.close_sheet_view)
        self.splitter = _Splitter(self)
        self.editor: Optional[QLineEdit] = None    # a tab's name edited on it
        layout.addWidget(self.back)
        layout.addWidget(self.forth)
        layout.addWidget(self.clip)
        layout.addWidget(self.add)
        layout.addStretch(1)
        layout.addWidget(self.splitter)
        # the workbook's and the sheet's names over the grid, the × at their
        # right: the top right of the sheet, where a window's close is (the
        # user, 2026-10-22: "the x button to escape workbook should be top
        # right, where is the sheet name easily visible like table name")
        self.title = SheetTitle(self.close_button)
        self._moving = False
        self.hide()

    def _arrow(self, kind, name: str, tip: str, step: int) -> QToolButton:
        button = QToolButton()
        button.setObjectName(name)
        button.setArrowType(kind)
        button.setAutoRaise(True)
        button.setToolTip(tip)
        button.setFixedWidth(16)
        button.clicked.connect(lambda: self._arrow_clicked(step))
        button.setContextMenuPolicy(Qt.CustomContextMenu)
        button.customContextMenuRequested.connect(
            lambda pos, b=button: self._sheet_list(b.mapToGlobal(pos)))
        return button

    # -- the row shared with the scroll bar (Excel's TabRatio) ---------------------------
    def ratio(self) -> float:
        """The tabs' share of the row: as dragged, else the workbook's."""
        if self._ratio is not None:
            return self._ratio
        for uid, _name in self.entries[:1]:
            item = self._item(uid)
            page = getattr(getattr(item, "sheet", None), "page", None) or {}
            try:
                return max(0.0, min(1.0, float(page.get("tab_ratio", TAB_RATIO))))
            except (TypeError, ValueError):
                break
        return TAB_RATIO

    def _watch_row(self) -> None:
        row = self.parentWidget()
        if row is not None and row is not self._row:
            self._row = row
            row.installEventFilter(self)

    def fit_row(self) -> None:
        """Its width: its share of the row, the scroll bar the rest."""
        self._watch_row()
        row = self._row
        if row is None:
            return
        total = row.width()
        width = int(round(total * self.ratio()))
        width = max(self.splitter.width(), min(width, total - MIN_BAR))
        if self.width() != width or self.minimumWidth() != width:
            self.setFixedWidth(max(width, 0))
            self._show_current()

    def set_ratio(self, ratio: float) -> None:
        self._ratio = max(0.0, min(1.0, ratio))
        self.fit_row()

    def drag_ratio(self, x: float) -> None:
        """The splitter dragged to *x* along the row: the tabs end there."""
        row = self._row
        if row is None or row.width() <= 0:
            return
        self.set_ratio((x + self.splitter.width() / 2.0) / row.width())

    def keep_ratio(self) -> None:
        """The split dragged to: kept with the workbook (each of its
        sheets), saved with the document."""
        ratio = self._ratio
        if ratio is None:
            return
        changed = False
        for uid, _name in self.entries:
            item = self._item(uid)
            sheet = getattr(item, "sheet", None)
            if sheet is None:
                continue
            if sheet.page is None:
                sheet.page = {}
            if sheet.page.get("tab_ratio") != round(ratio, 3):
                sheet.page["tab_ratio"] = round(ratio, 3)
                changed = True
        self._ratio = None
        if changed:
            self.window.mark_modified()
        self.fit_row()

    # -- scrolling the tabs ------------------------------------------------------------------
    def _arrow_clicked(self, step: int) -> None:
        count = self.bar.count()
        if not count:
            return
        if QApplication.keyboardModifiers() & Qt.ControlModifier:
            # Excel: Ctrl+click an arrow goes to the first or last sheet
            self.go(0 if step < 0 else count - 1)
            return
        self.scroll_tabs(self.first_shown + step)

    def scroll_tabs(self, first: int) -> None:
        """The tabs from tab *first* in sight."""
        count = self.bar.count()
        first = max(0, min(first, max(count - 1, 0)))
        # no further than shows the last tab at the right
        room = self.clip.width()
        while first > 0 and self.bar.tabRect(count - 1).right() - \
                self.bar.tabRect(first - 1).left() < room:
            first -= 1
        self.first_shown = first
        self.clip.offset = self.bar.tabRect(first).left() if count else 0
        self.clip.place()
        # (never greyed: a right-click on either lists every sheet, as Excel's)

    def _show_current(self) -> None:
        """The current tab in sight, scrolled to if it was not."""
        i = self.bar.currentIndex()
        self._name_title(i)
        if i < 0:
            self.scroll_tabs(self.first_shown)
            return
        rect = self.bar.tabRect(i)
        room = self.clip.width()
        first = self.first_shown
        if rect.left() < self.bar.tabRect(min(first, self.bar.count() - 1)).left():
            first = i
        while first < i and rect.right() - self.bar.tabRect(first).left() >= room:
            first += 1
        self.scroll_tabs(first)

    def _name_title(self, index: int) -> None:
        """The strip over the grid: the workbook's name (an Excel one's, when
        it came from a file) and the sheet's."""
        if not 0 <= index < len(self.entries):
            self.title.show_names("", "")
            return
        from .sheetpages import sections
        document = getattr(self, "_document", None) or self.window.document
        section = next((x for x in sections(document) if x.key == self.section_key), None)
        book = section.name if section is not None and section.book else ""
        self.title.show_names(book, self.entries[index][1])

    def _sheet_list(self, at: QPoint) -> Optional[QMenu]:
        """Excel's right-click on the tab arrows: every sheet, to go to."""
        menu = QMenu(self)
        menu.setProperty("cf_context", "sheetlist")
        current = self.bar.currentIndex()
        for i, (_uid, name) in enumerate(self.entries):
            action = menu.addAction(name, lambda i=i: self.go(i))
            action.setCheckable(True)
            action.setChecked(i == current)
        self.popup = menu
        menu.aboutToHide.connect(menu.deleteLater)
        menu.popup(at)
        return menu

    # -- the workbook shown -----------------------------------------------------------
    def _sections(self) -> list:
        from .sheetpages import sections
        return sections(self.window.document)

    def section(self):
        """The workbook listed in the strip, or None."""
        for section in self._sections():
            if section.key == self.section_key:
                return section
        return None

    def view(self):
        """The view this strip sits under (each pane of a split has its own)."""
        from PySide6.QtWidgets import QGraphicsView
        widget = self.parentWidget()
        while widget is not None and not isinstance(widget, QGraphicsView):
            widget = widget.parentWidget()
        return widget if widget is not None else getattr(self.window, "view", None)

    def in_view(self) -> bool:
        """Whether a sheet is shown alone under this strip."""
        from .sheetview import run_shown
        view = self.view()
        return run_shown(view.scene() if view is not None else None) is not None

    def update_mode(self) -> bool:
        """Show the strip if, and only if, its view's canvas shows a sheet
        alone, listing that workbook's sheets. True when that changed."""
        from shiboken6 import isValid

        from .sheetview import run_shown
        if self._moving or not isValid(self):
            return False
        view = self.view()
        scene = view.scene() if view is not None else None
        uid = run_shown(scene)
        document = getattr(scene, "document", None) or self.window.document
        from .sheetpages import sections
        found = sections(document)
        section = next((s for s in found if uid in s.runs), None) if uid else None
        was = (self.showing, self.section_key)
        self.showing = section is not None
        self.section_key = section.key if section is not None else None
        self._document = document
        self._fill()
        self.setVisible(self.showing)
        self.title.setVisible(self.showing)
        self._scroll_row(view, bool(found))
        self.fit_row()
        self.follow()
        return was != (self.showing, self.section_key)

    def close_sheet_view(self) -> None:
        """The ×: back to the pages, to the page you came from."""
        from .sheetview import close
        if self.view() is not getattr(self.window, "view", None):
            return
        close(self.window)

    def _fill(self) -> None:
        """The tabs of the workbook listed, rebuilt if its sheets changed."""
        document = getattr(self, "_document", None) or self.window.document
        from .sheetpages import run_book, sections
        section = next((s for s in sections(document) if s.key == self.section_key), None)
        found = []
        if section is not None:
            for uid in section.runs:
                found.append((uid, run_book(document, uid)[2]))
        if found != self.entries:
            self.entries = found
            self._marked = ()
            self.bar.blockSignals(True)
            while self.bar.count():
                self.bar.removeTab(0)
            for _uid, name in found:
                self.bar.addTab(name)              # the bare name, as Excel's
            self.bar.blockSignals(False)
            self.clip.updateGeometry()
            self.clip.place()
        self._mark_printing()

    def prints(self, index: int) -> bool:
        """Whether the sheet of tab *index* prints."""
        if not 0 <= index < len(self.entries):
            return True
        from .sheetpages import sheet_prints
        return sheet_prints(getattr(self, "_document", None) or self.window.document,
                            self.entries[index][0])

    def _mark_printing(self) -> None:
        """A sheet that doesn't print: its tab greyed, a crossed-out printer
        on it, and its tooltip says so."""
        from ..app import current_theme
        states = [self.prints(i) for i in range(len(self.entries))]
        if (self.entries, states, current_theme()) == self._marked:
            return                       # as marked already (setting an icon lays the tabs out)
        self._marked = (list(self.entries), states, current_theme())
        ratio = self.window.devicePixelRatioF()
        for i, (_uid, name) in enumerate(self.entries):
            prints = states[i]
            self.bar.setTabIcon(i, QIcon() if prints else QIcon(no_print_pixmap(14, ratio)))
            self.bar.setTabToolTip(
                i, f"Spreadsheet {name}" if prints else
                f"Spreadsheet {name} — doesn't print (right-click ▸ Print to print it)")
        self.bar.update()

    _marked: tuple = ()

    def _scroll_row(self, view, any_sheets: bool) -> None:
        # Excel's row: the tabs on the left of the horizontal scroll bar, one
        # bar — the tabs on a row of their own under the canvas's scroll bar
        # read as a second scroll bar (the user, 2026-10-15). The bar is kept
        # showing while the document has sheets, whether or not their tabs
        # are, so the canvas keeps its height as the tabs come and go.
        if view is None:
            return
        policy = Qt.ScrollBarAlwaysOn if any_sheets else Qt.ScrollBarAsNeeded
        if view.horizontalScrollBarPolicy() != policy:
            # Qt lays the whole view out again when told, changed or not:
            # 80 ms of every page scrolled onto in a drawing set (2026-10-19)
            view.setHorizontalScrollBarPolicy(policy)
        scroll = view.horizontalScrollBar()
        name = "sheetRowScroll" if any_sheets else ""
        if scroll.objectName() != name:
            scroll.setObjectName(name)       # the row as tall as the tabs
            scroll.style().unpolish(scroll)
            scroll.style().polish(scroll)
            scroll.updateGeometry()
        # the workbook view's bars: Windows' arrows at their ends (A4)
        changed = False
        for bar in (scroll, view.verticalScrollBar()):
            if bool(bar.property("sheetView")) != self.showing:
                bar.setProperty("sheetView", self.showing)
                bar.style().unpolish(bar)
                bar.style().polish(bar)
                bar.updateGeometry()
                changed = True
        if changed:
            # the view lays its bars out at once: the window is its new size
            # before it is scrolled back to where it was
            QApplication.sendEvent(view, QEvent(QEvent.LayoutRequest))

    def refresh(self) -> None:
        """The strip as its view now is — and every other pane's strip, so
        none is left showing for a workbook it no longer shows."""
        from shiboken6 import isValid
        if not isValid(self) or self._moving:
            return
        from .sheetview import sync
        sync(self.window)
        changed = self.update_mode()
        from . import sheetfreeze, sheetstatus
        sheetstatus.refresh(self.window)   # the footer: Excel's or the paper's, as the view is
        view = self.view()
        if view is not None:
            sheetfreeze.refresh(view)
        for pane in getattr(self.window, "_panes", None) or ():
            other = getattr(pane, "sheet_tabs", None)
            if other is not None and other is not self and isValid(other):
                other.update_mode()
        if changed:
            tables = getattr(self.view(), "tables", None)
            if tables is not None:
                tables.refresh_bar()

    def follow(self) -> None:
        """The tab of the spreadsheet page in view."""
        from .sheetview import run_shown
        view = self.view()
        wanted = run_shown(view.scene() if view is not None else None)
        for i, (uid, _name) in enumerate(self.entries):
            if uid == wanted:
                self.bar.blockSignals(True)
                self.bar.setCurrentIndex(i)
                self.bar.blockSignals(False)
                self._show_current()
                return

    # -- going there --------------------------------------------------------------------
    def _item(self, uid: str):
        from ..items.sheetpage import SheetRunItem
        for frame in getattr(self.window.scene, "frames", []) or []:
            for item in frame.markups():
                if isinstance(item, SheetRunItem) and item.uid == uid:
                    return item
        return None

    def go(self, index: int) -> None:
        if not 0 <= index < len(self.entries):
            return
        uid, _name = self.entries[index]
        window = self.window
        first = next(i for i, page in enumerate(window.document.pages) if page.sheet == uid)
        window.go_to_page(first)
        self.follow()

    def _clicked(self, index: int) -> None:
        if index >= 0:
            self.go(index)

    def _rename(self, index: int) -> None:
        if not 0 <= index < len(self.entries):
            return
        uid, name = self.entries[index]
        item = self._item(uid)
        if item is None:
            return
        # Excel: the name edited on the tab itself; Enter (or a click away)
        # keeps it, Esc leaves it as it was
        self._end_rename(False)
        if self.bar.currentIndex() != index:
            self.go(index)
        editor = self.editor = QLineEdit(self.bar)
        editor.setObjectName("sheetTabRename")
        editor.setText(name)
        editor.selectAll()
        editor.setFrame(False)
        editor.setAlignment(Qt.AlignCenter)
        editor.setGeometry(self.bar.tabRect(index).adjusted(2, 2, -2, -2))
        editor.setToolTip("The sheet's name: Enter keeps it (formulas that use it follow), "
                          "Esc leaves it")
        editor._uid = uid
        editor.returnPressed.connect(lambda: self._end_rename(True))
        # a click elsewhere keeps the name too (the focus taken by the sheet
        # coming into view does not)
        editor.installEventFilter(self)
        editor.show()
        editor.setFocus(Qt.MouseFocusReason)

        def ready(editor=editor):
            from shiboken6 import isValid
            if self.editor is editor and isValid(editor):
                editor.setFocus(Qt.OtherFocusReason)    # (the sheet shown took it)
                editor.selectAll()
        QTimer.singleShot(0, ready)

    def _end_rename(self, keep: bool) -> None:
        editor, self.editor = self.editor, None
        if editor is None:
            return
        uid, new = editor._uid, editor.text().strip()
        editor.hide()
        editor.deleteLater()
        item = self._item(uid)
        name = next((n for u, n in self.entries if u == uid), None)
        if keep and item is not None and new and new != name:
            self.window.view.tables.rename_to(item, new)
            self.entries = []
            self.refresh()
        self.window.view.setFocus()

    # -- moving a sheet ------------------------------------------------------------------
    def _moved(self, frm: int, to: int) -> None:
        """A sheet's tab dragged along: its run of pages goes where the tab
        went, among the workbook's sheets."""
        entry = self.entries[frm]
        order = list(self.entries)
        order.insert(to, order.pop(frm))
        pages = self.window.document.pages
        run = [i for i, page in enumerate(pages) if page.sheet == entry[0]]
        after = order[to + 1] if to + 1 < len(order) else None
        if after is None:
            # after the workbook's last sheet
            last = order[-2] if len(order) > 1 else entry
            target = max(i for i, page in enumerate(pages) if page.sheet == last[0]) + 1
        else:
            target = next(i for i, page in enumerate(pages) if page.sheet == after[0])
        self._moving = True
        try:
            if target > run[0]:
                target -= len(run)
            if target != run[0]:
                self.window.move_page(run[0], target, len(run))
        finally:
            self._moving = False
        self.entries = []
        self.refresh()

    # -- the menu and + --------------------------------------------------------------------------
    def build_menu(self, index: int) -> QMenu:
        """Excel's sheet tab menu (QA round 4): Insert Sheet, Delete,
        Rename…, then CalcForge's Print (ticked while the sheet prints) and
        Go To. (Move or Copy… and Tab Colour are left out: a sheet cannot be
        copied as a sheet yet, nor coloured.)"""
        from . import menutidy
        menu = QMenu(self)
        menu.setProperty("cf_context", "sheettab")
        menu.addAction("Insert Sheet", self.new_sheet).setToolTip(
            "A new sheet: a spreadsheet page at the end of this workbook")
        if 0 <= index < len(self.entries):
            delete = menu.addAction("Delete", lambda: self.delete_sheet(index))
            delete.setToolTip("Delete this sheet and its pages")
            menu.addAction("Rename…", lambda: self._rename(index))
            # a sheet of an imported Excel workbook: whether its names are its own
            from .workbookscope import tab_action
            run = self._item(self.entries[index][0])
            tab_action(menu, run.sheet if run is not None else None, self.window)
            menu.addSeparator()
            prints = menu.addAction("Print")
            prints.setCheckable(True)
            prints.setChecked(self.prints(index))
            prints.setToolTip("Ticked, this sheet's pages print and export; unticked "
                              "(Don't Print) they are left out, and its tab is greyed. "
                              "Its cells are still read by equations and other sheets.")
            prints.toggled.connect(lambda on, i=index: self.set_printing(i, on))
            menu.addSeparator()
            menu.addAction("Go To", lambda: self.go(index)).setToolTip(
                "Go to this sheet's first page")
        if self.showing:
            menu.addAction("Close Workbook", self.close_sheet_view).setToolTip(
                "Back to the pages, where you were (the × at the top right of the sheet)")
        return menutidy.tidy(menu)

    def set_printing(self, index: int, on: bool) -> None:
        """Print / Don't Print for the sheet of tab *index*: one undo step."""
        if not 0 <= index < len(self.entries):
            return
        from .sheetpages import set_sheet_printing
        uid, name = self.entries[index]
        set_sheet_printing(self.window, uid, on)
        self.refresh()
        self.window.status_hint.setText(
            f"{name} prints" if on else f"{name} doesn't print (its cells are still read)")

    def _menu(self, pos) -> None:
        menu = self.build_menu(self.bar.tabAt(pos))
        menu.exec(self.bar.mapToGlobal(pos))
        menu.deleteLater()

    def _menu_popup(self, pos) -> QMenu:
        """The tab's menu, left up (a long press: the finger is still down)."""
        if self.popup is not None:
            try:
                self.popup.close()
            except RuntimeError:
                pass
        menu = self.popup = self.build_menu(self.bar.tabAt(pos))
        menu.aboutToHide.connect(menu.deleteLater)
        menu.popup(self.bar.mapToGlobal(pos))
        return menu

    def eventFilter(self, watched, event) -> bool:
        if watched is self._row and event.type() == QEvent.Resize:
            self.fit_row()
            return False
        if watched is self.editor and event.type() == QEvent.KeyPress \
                and event.key() == Qt.Key_Escape:
            self._end_rename(False)
            return True
        if watched is self.editor and event.type() == QEvent.FocusOut \
                and event.reason() == Qt.MouseFocusReason:
            QTimer.singleShot(0, lambda: self._end_rename(True))
            return False
        if watched is self.bar:
            kind = event.type()
            if kind == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._press = event.position().toPoint()
                self._long.start()
            elif kind == QEvent.MouseMove and self._press is not None:
                moved = event.position().toPoint() - self._press
                if moved.manhattanLength() > QApplication.startDragDistance():
                    self._long.stop()
                    self._press = None
            elif kind in (QEvent.MouseButtonRelease, QEvent.Leave, QEvent.Hide):
                self._long.stop()
                self._press = None
        return super().eventFilter(watched, event)

    def _long_pressed(self) -> None:
        pos, self._press = self._press, None
        if pos is not None and self.bar.tabAt(pos) >= 0:
            self._menu_popup(pos)

    def delete_sheet(self, index: int) -> None:
        """Excel's Delete on a sheet tab: the sheet's pages go (asked first)."""
        if not 0 <= index < len(self.entries):
            return
        uid, _name = self.entries[index]
        window = self.window
        pages = [i for i, page in enumerate(window.document.pages) if page.sheet == uid]
        if pages:
            window.delete_page(pages[0], pages=pages)
            self.refresh()

    def new_sheet(self, before: bool = False) -> None:
        """A new spreadsheet page, a sheet of its own, at the end of the
        workbook in view (of the document, when there is none) — or, with
        *before* (Shift+F11), before the sheet shown, as Excel puts it."""
        window = self.window
        from . import sheetpages
        section = self.section()
        if section is not None:
            from .sheetview import run_shown
            shown = run_shown(window.scene) if before else None
            sheetpages.new_sheet_in(window, section, before=shown)
            # and it is the sheet shown (new_sheet_in made it the current page)
            window.go_to_page(window.current_index)
        else:
            sheetpages.insert_sheet_page(window, len(window.document.pages) - 1, new_sheet=True)
        self.refresh()
