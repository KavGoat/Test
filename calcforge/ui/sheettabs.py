"""Excel's sheet tabs, under the canvas: every spreadsheet in the document,
in reading order (the user's choice, 2026-10-11: a tab strip that navigates
— each sheet stays on its own printed pages). Tables have none (the user,
2026-10-11: "Tables don't need tabs").

A click goes to it, the tab of the sheet in view is the current one, a
double-click renames, a tab dragged along moves the sheet's run of pages,
and + adds a new sheet at the end.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QMenu, QTabBar, QToolButton, QWidget



class SheetTabs(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setObjectName("sheetTabs")
        self.entries: list = []                 # (run uid, name)
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

        from ..items.sheetpage import run_item_for
        out, seen = [], set()
        for page in self.window.document.pages:
            if page.sheet is None or page.sheet in seen:
                continue
            seen.add(page.sheet)
            frame = page.frame
            if frame is not None and not isValid(frame):
                frame = None                    # its page being rebuilt: no frame yet
            run = run_item_for(frame) if frame is not None else None
            out.append((page.sheet, run.name if run is not None else "Sheet"))
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
            for _uid, name in found:
                index = self.bar.addTab("▦ " + name)
                self.bar.setTabToolTip(index, f"Spreadsheet {name}")
            self.bar.blockSignals(False)
        self.setVisible(bool(found))
        self.follow()

    def follow(self) -> None:
        """The tab of the spreadsheet page in view."""
        window = self.window
        wanted: Optional[str] = None
        pages = window.document.pages
        index = window.current_index
        if 0 <= index < len(pages):
            wanted = pages[index].sheet
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
        """A sheet's tab dragged along: its run of pages goes where the tab went."""
        entry = self.entries[frm]
        order = list(self.entries)
        order.insert(to, order.pop(frm))
        pages = self.window.document.pages
        run = [i for i, page in enumerate(pages) if page.sheet == entry[0]]
        after = order[to + 1] if to + 1 < len(order) else None
        if after is None:
            target = len(pages)
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
