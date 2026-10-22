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

A click goes to that sheet, the tab of the sheet shown is the current one,
a double-click renames, a tab dragged along moves the sheet's run of pages,
and + adds a new sheet at the end of the workbook. Right-click (or a long
press, for touch) a tab for its menu: Print, ticked while the sheet prints,
is Print / Don't Print for the sheet; a sheet that doesn't print has a grey
tab with a crossed-out printer.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QHBoxLayout, QMenu, QTabBar, QToolButton, QWidget

#: How long a press on a tab is held before it opens the tab's menu (touch).
LONG_PRESS_MS = 550



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


class SheetTabs(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setObjectName("sheetTabs")
        self.entries: list = []                 # (run uid, name) of the workbook listed
        self.section_key: Optional[str] = None  # the workbook listed (its first run)
        self.showing = False                    # whether a sheet is shown alone
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 4, 0)
        layout.setSpacing(2)
        # beside the scroll bar, at most half of it (the rest scrolls)
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.add = QToolButton()
        self.add.setText("+")
        self.add.setToolTip("New sheet (a spreadsheet page at the end of this workbook)")
        self.add.clicked.connect(self.new_sheet)
        self.bar = _TabBar(self)
        self.bar.setMovable(True)
        self.bar.setDrawBase(False)
        self.bar.setExpanding(False)
        self.bar.setUsesScrollButtons(True)
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
        layout.addWidget(self.add)
        layout.addWidget(self.bar, 1)
        layout.addWidget(self.close_button)
        self._moving = False
        self.hide()

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
        self._scroll_row(view, bool(found))
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
                self.bar.addTab("▦ " + name)
            self.bar.blockSignals(False)
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

    def refresh(self) -> None:
        """The strip as its view now is — and every other pane's strip, so
        none is left showing for a workbook it no longer shows."""
        from shiboken6 import isValid
        if not isValid(self) or self._moving:
            return
        from .sheetview import sync
        sync(self.window)
        changed = self.update_mode()
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
        window = self.window
        if not getattr(window, "interactive_prompts", True):
            return
        from PySide6.QtWidgets import QInputDialog
        new, ok = QInputDialog.getText(window, "Rename sheet",
                                       "Name (formulas that use it follow):", text=name)
        if ok and new.strip() and new.strip() != name:
            window.view.tables.rename_to(item, new.strip())
            self.refresh()

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
                "Back to the pages, where you were (the × at the end of the tabs)")
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

    def new_sheet(self) -> None:
        """A new spreadsheet page, a sheet of its own, at the end of the
        workbook in view (of the document, when there is none)."""
        window = self.window
        from . import sheetpages
        section = self.section()
        if section is not None:
            sheetpages.new_sheet_in(window, section)
            # and it is the sheet shown (new_sheet_in made it the current page)
            window.go_to_page(window.current_index)
        else:
            sheetpages.insert_sheet_page(window, len(window.document.pages) - 1, new_sheet=True)
        self.refresh()
