"""Excel's sheet tabs, under the canvas: every spreadsheet and table in the
document, in reading order (the user's choice, 2026-10-11: a tab strip that
navigates — each sheet stays on its own printed pages).

A click goes to it, the tab of what is in view is the current one, a
double-click renames, a sheet's tab dragged along moves its run of pages,
and + adds a new sheet at the end.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QMenu, QTabBar, QToolButton, QWidget

SHEET, TABLE = "sheet", "table"


class SheetTabs(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setObjectName("sheetTabs")
        self.entries: list = []                 # (kind, uid, name)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(2)
        self.add = QToolButton()
        self.add.setText("+")
        self.add.setToolTip("New sheet (a spreadsheet page at the end)")
        self.add.clicked.connect(self.new_sheet)
        self.bar = QTabBar()
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
        layout.addWidget(self.add)
        layout.addWidget(self.bar, 1)
        self._moving = False
        self.hide()

    # -- what there is --------------------------------------------------------------
    def _found(self) -> list:
        from shiboken6 import isValid

        from ..items.sheetpage import SheetRunItem, run_item_for
        from ..items.table import TableItem
        out, seen = [], set()
        document = self.window.document
        for page in document.pages:
            frame = page.frame
            if frame is not None and not isValid(frame):
                frame = None                    # its page being rebuilt: no frame yet
            if page.sheet is not None and page.sheet not in seen:
                seen.add(page.sheet)
                run = run_item_for(frame) if frame is not None else None
                name = run.name if run is not None else "Sheet"
                out.append((SHEET, page.sheet, name))
            if frame is None:
                continue
            for item in sorted((i for i in frame.markups() if isinstance(i, TableItem)
                                and not isinstance(i, SheetRunItem)),
                               key=lambda i: (i.pos().y(), i.pos().x())):
                out.append((TABLE, item.uid, item.name))
        return out

    def refresh(self) -> None:
        """Rebuild the tabs if the sheets or tables changed; then the current one."""
        from shiboken6 import isValid
        if not isValid(self) or self._moving:
            return
        found = self._found()
        if found != self.entries:
            self.entries = found
            self.bar.blockSignals(True)
            while self.bar.count():
                self.bar.removeTab(0)
            for kind, _uid, name in found:
                index = self.bar.addTab(("▦ " if kind == SHEET else "▤ ") + name)
                self.bar.setTabToolTip(index, f"{'Spreadsheet' if kind == SHEET else 'Table'} {name}")
            self.bar.blockSignals(False)
        self.setVisible(bool(found))
        self.follow()

    def follow(self) -> None:
        """The tab of the open table, or of the spreadsheet page in view."""
        window = self.window
        tables = window.view.tables
        wanted: Optional[str] = None
        if tables.item is not None:
            wanted = tables.item.uid if not getattr(tables.item, "SHEET_RUN", False) else None
        if wanted is None:
            pages = window.document.pages
            index = window.current_index
            if 0 <= index < len(pages):
                wanted = pages[index].sheet
        for i, (_kind, uid, _name) in enumerate(self.entries):
            if uid == wanted:
                self.bar.blockSignals(True)
                self.bar.setCurrentIndex(i)
                self.bar.blockSignals(False)
                return

    # -- going there --------------------------------------------------------------------
    def _item(self, uid: str):
        from ..items.table import TableItem
        for frame in getattr(self.window.scene, "frames", []) or []:
            for item in frame.markups():
                if isinstance(item, TableItem) and item.uid == uid:
                    return item
        return None

    def go(self, index: int) -> None:
        if not 0 <= index < len(self.entries):
            return
        kind, uid, _name = self.entries[index]
        window = self.window
        if kind == SHEET:
            first = next(i for i, page in enumerate(window.document.pages) if page.sheet == uid)
            window.go_to_page(first)
        else:
            item = self._item(uid)
            if item is None:
                return
            window.view.tables.close()
            window.view.scene().clearSelection()
            item.setSelected(True)
            window.view.centerOn(item)
        self.follow()

    def _clicked(self, index: int) -> None:
        if index >= 0:
            self.go(index)

    def _rename(self, index: int) -> None:
        if not 0 <= index < len(self.entries):
            return
        kind, uid, name = self.entries[index]
        item = self._item(uid)
        if item is None:
            return
        window = self.window
        if not getattr(window, "interactive_prompts", True):
            return
        from PySide6.QtWidgets import QInputDialog
        new, ok = QInputDialog.getText(window, "Rename sheet" if kind == SHEET else "Rename table",
                                       "Name (formulas that use it follow):", text=name)
        if ok and new.strip() and new.strip() != name:
            window.view.tables.rename_to(item, new.strip())
            self.refresh()

    # -- moving a sheet ------------------------------------------------------------------
    def _moved(self, frm: int, to: int) -> None:
        """A sheet's tab dragged along: its run of pages goes where the tab went."""
        entry = self.entries[frm]
        order = list(self.entries)
        order.insert(to, order.pop(frm))
        if entry[0] != SHEET:
            self.entries = []                  # tables stay on their pages
            self.refresh()
            return
        pages = self.window.document.pages
        run = [i for i, page in enumerate(pages) if page.sheet == entry[1]]
        after = order[to + 1] if to + 1 < len(order) else None
        if after is None:
            target = len(pages)
        elif after[0] == SHEET:
            target = next(i for i, page in enumerate(pages) if page.sheet == after[1])
        else:
            item = self._item(after[1])
            target = pages.index(item.parentItem().page) if item is not None else len(pages)
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
    def _menu(self, pos) -> None:
        index = self.bar.tabAt(pos)
        menu = QMenu(self)
        if index >= 0:
            menu.addAction("Go to", lambda: self.go(index))
            menu.addAction("Rename…", lambda: self._rename(index))
            menu.addSeparator()
        menu.addAction("New sheet", self.new_sheet)
        menu.exec(self.bar.mapToGlobal(pos))

    def new_sheet(self) -> None:
        """A new spreadsheet page, a sheet of its own, at the end."""
        window = self.window
        from . import sheetpages
        sheetpages.insert_sheet_page(window, len(window.document.pages) - 1, new_sheet=True)
        self.refresh()
