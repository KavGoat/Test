"""Excel's sheet tabs, under the canvas: the sheets of the workbook in view,
in reading order (the user's choice, 2026-10-11: a tab strip that navigates
— each sheet stays on its own printed pages). Tables have none (the user,
2026-10-11: "Tables don't need tabs").

The strip shows only while a workbook is in view (the user, 2026-10-21:
"spreadsheet imported tabs etc. are always showing at the bottom, don't"):
a workbook is a section of the document (sheetpages.sections), and while
the page in view — the one the page box shows — is one of its pages, or one
of its sheets is open, the spreadsheet view is on: the formula bar, these
tabs and, with a cell picked, the cell tools. Scrolling off it turns the
view off again, a little past the edge of its pages rather than on the
pixel, so the bars don't flicker on and off at the page boundary.

A click goes to it, the tab of the sheet in view is the current one, a
double-click renames, a tab dragged along moves the sheet's run of pages,
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

#: How far past the edge of a workbook's pages the middle of the window must
#: go before the spreadsheet view follows a scroll, in screen pixels: more
#: than half the formula bar's height, so the bar showing or going (which
#: moves the middle by half its height) never turns it back.
HYSTERESIS_PX = 32

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
            painter.fillRect(self.tabRect(i), wash)
        painter.end()


class SheetTabs(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setObjectName("sheetTabs")
        self.entries: list = []                 # (run uid, name) of the workbook listed
        self.section_key: Optional[str] = None  # the workbook listed (its first run)
        self.showing = False                    # whether the spreadsheet view is on
        self._updating = False
        self._hooked = None                     # the view whose scrolling is heard
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
        layout.addWidget(self.add)
        layout.addWidget(self.bar, 1)
        self._moving = False
        self.hide()

    # -- the workbook in view ---------------------------------------------------------
    def _sections(self) -> list:
        from .sheetpages import sections
        return sections(self.window.document)

    def section(self):
        """The workbook listed in the strip (shown or not), or None."""
        for section in self._sections():
            if section.key == self.section_key:
                return section
        return None

    def in_view(self) -> bool:
        """Whether the spreadsheet view is on (the formula bar asks)."""
        if not self._updating:
            self.update_mode()
        return self.showing

    def _frames_rect(self, section) -> QRectF:
        from shiboken6 import isValid
        out = QRectF()
        for i in section.pages:
            frame = self.window.document.pages[i].frame
            if frame is not None and isValid(frame) and frame.isVisible():
                out = out.united(frame.sceneBoundingRect())
        return out

    def _middle(self):
        """The middle of the window on the canvas, and the hysteresis there."""
        view = self.window.view
        transform = view.transform()
        scale = max((transform.m11() ** 2 + transform.m12() ** 2) ** 0.5, 1e-6)
        return view.mapToScene(view.viewport().rect().center()), HYSTERESIS_PX / scale

    def _seen(self, section) -> bool:
        """Whether any of the workbook's pages is in the window."""
        view = self.window.view
        shown = view.mapToScene(view.viewport().rect()).boundingRect()
        _middle, margin = self._middle()
        # more than a sliver of it: the edge of a page above the one gone to
        # peeking in at the top is not the sheet in view
        shown = shown.adjusted(margin, margin, -margin, -margin)
        return self._frames_rect(section).intersects(shown)

    def _open_section(self, found: list):
        """The workbook of the sheet open for its cells, if one is."""
        from ..items.sheetpage import SheetRunItem
        tables = getattr(self.window.view, "tables", None)
        item = tables.item if tables is not None else None
        if not isinstance(item, SheetRunItem):
            return None
        return next((s for s in found if item.uid in s.runs), None)

    def _wanted(self, found: list, jumped: bool, scrolled: bool):
        """The workbook the spreadsheet view is for, or None."""
        window = self.window
        index = window.current_index
        counter = next((s for s in found if s.first <= index <= s.last), None)
        opened = self._open_section(found)
        if opened is not None:
            if jumped and (counter is None or counter.key != opened.key):
                # gone to another page: once there, put down a sheet no longer on screen
                QTimer.singleShot(0, self, self._left_behind)
            if not (scrolled and not jumped and self._put_down(opened)):
                return opened            # a sheet open stays in view while it is on screen
        if jumped:
            return counter
        shown = next((s for s in found if s.key == self.section_key), None) \
            if self.showing else None
        if (counter.key if counter else None) == (shown.key if shown else None):
            return counter
        # the page box has moved on: followed, unless the middle of the window
        # is still within a little of the edge it crossed
        middle, margin = self._middle()
        if shown is not None and self._frames_rect(shown).adjusted(
                -margin, -margin, margin, margin).contains(middle):
            return shown                 # not far enough off it yet
        if counter is not None:
            rect = self._frames_rect(counter)
            if rect.adjusted(-margin, -margin, margin, margin).contains(middle) and \
                    not rect.adjusted(margin, margin, -margin, -margin).contains(middle):
                return shown             # not far enough onto it yet
        return counter

    def _put_down(self, section) -> bool:
        """Close the sheet open for its cells once none of its workbook's
        pages is on screen (not while a cell is being typed in). True when
        it was closed."""
        tables = self.window.view.tables
        if tables.editor is not None or self._seen(section):
            return False
        tables.close()
        return True

    def _left_behind(self) -> None:
        from shiboken6 import isValid
        if not isValid(self) or getattr(self.window, "sheet_tabs", None) is not self:
            return
        opened = self._open_section(self._sections())
        if opened is not None and self._put_down(opened):
            self.update_mode(jumped=False)

    def update_mode(self, jumped: Optional[bool] = None, scrolled: bool = False) -> bool:
        """Turn the spreadsheet view on or off for what is in view, and list
        the workbook's sheets. True when anything changed."""
        from shiboken6 import isValid
        if self._updating or self._moving or not isValid(self):
            return False
        if jumped is None:
            from .viewsync import ViewSync
            jumped = bool(ViewSync._jumping)
        self._updating = True
        try:
            found = self._sections()
            wanted = self._wanted(found, jumped, scrolled) if found else None
            was = (self.showing, self.section_key)
            self.showing = wanted is not None
            if wanted is not None:
                self.section_key = wanted.key
            elif not any(s.key == self.section_key for s in found):
                # nothing in view: the tabs (hidden) are the first workbook's,
                # for a key bound to a tab's command
                self.section_key = found[0].key if found else None
            if not scrolled or was[1] != self.section_key:
                self._fill()             # (a scroll that stays on it changes nothing there)
            self.setVisible(self.showing)
            self._scroll_row(bool(found))
            self.follow()
            changed = was != (self.showing, self.section_key)
        finally:
            self._updating = False
        if changed:
            tables = getattr(self.window.view, "tables", None)
            if tables is not None:
                tables.refresh_bar()
        return changed

    def _fill(self) -> None:
        """The tabs of the workbook listed, rebuilt if its sheets changed."""
        section = self.section()
        found = []
        if section is not None:
            from .sheetpages import run_book
            for uid in section.runs:
                found.append((uid, run_book(self.window.document, uid)[2]))
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
        return sheet_prints(self.window.document, self.entries[index][0])

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

    def _scroll_row(self, any_sheets: bool) -> None:
        # Excel's row: the tabs on the left of the horizontal scroll bar, one
        # bar — the tabs on a row of their own under the canvas's scroll bar
        # read as a second scroll bar (the user, 2026-10-15). The bar is kept
        # showing while the document has sheets, whether or not their tabs
        # are, so the canvas keeps its height as the tabs come and go.
        view = getattr(self.window, "view", None)
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

    def _hook(self) -> None:
        """Hear the canvas scroll, to turn the view off (or on) once the
        middle of the window is far enough past the workbook's edge."""
        window = self.window
        view = getattr(window, "view", None)
        if view is None or getattr(window, "sheet_tabs", None) is not self or self._hooked is view:
            return
        self._hooked = view
        view.verticalScrollBar().valueChanged.connect(self._scrolled)
        view.horizontalScrollBar().valueChanged.connect(self._scrolled)

    def _scrolled(self, _value: int = 0) -> None:
        window = self.window
        if getattr(window, "sheet_tabs", None) is not self or window.view is not self._hooked:
            return
        if self.section_key is None and not self._sections():
            return
        self.update_mode(scrolled=True)

    def refresh(self) -> None:
        """Rebuild the tabs if the sheets changed; then the current one."""
        from shiboken6 import isValid
        if not isValid(self) or self._moving:
            return
        self._hook()
        self.update_mode()

    def follow(self) -> None:
        """The tab of the spreadsheet page in view."""
        window = self.window
        wanted: Optional[str] = None
        pages = window.document.pages
        index = window.current_index
        if 0 <= index < len(pages):
            wanted = pages[index].sheet
        from ..items.sheetpage import SheetRunItem
        item = getattr(getattr(window.view, "tables", None), "item", None)
        if isinstance(item, SheetRunItem):
            wanted = item.uid              # the sheet open for its cells
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
        else:
            sheetpages.insert_sheet_page(window, len(window.document.pages) - 1, new_sheet=True)
        self.refresh()
