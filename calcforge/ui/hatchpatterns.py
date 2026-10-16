"""Revu's Hatch Patterns: every pattern the hatch lists offer, each drawn, and
bringing in an AutoCAD / Revu .pat file or writing a pattern of one's own.
The built-in patterns stay; one's own can be taken out again."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
                               QInputDialog, QListWidget, QListWidgetItem, QMessageBox,
                               QPushButton, QVBoxLayout)

from ..items import hatches

#: What a hatch list's last row carries: open this dialog.
MANAGE = "__manage__"

#: An example a new pattern starts from: 45° lines an eighth of an inch apart.
EXAMPLE = "*MY-PATTERN, 45 degree lines\n45, 0,0, 0,0.125\n"


class HatchPatternsDialog(QDialog):
    def __init__(self, parent=None, ink: str = "#000000"):
        super().__init__(parent)
        self.ink = ink
        self.setWindowTitle("Hatch Patterns")
        self.setObjectName("hatchPatterns")
        self.resize(440, 420)
        layout = QHBoxLayout(self)
        self.list = QListWidget()
        self.list.setObjectName("hatchList")
        self.list.setIconSize(QSize(64, 24))
        self.list.currentRowChanged.connect(lambda *_: self._enable())
        layout.addWidget(self.list, 1)
        side = QVBoxLayout()
        self.buttons = {}
        for key, text, slot in (("import", "Import…", self.import_file),
                                ("new", "New…", self.new_pattern),
                                ("remove", "Remove", self.remove)):
            button = QPushButton(text)
            button.setObjectName(f"hatch_{key}")
            button.clicked.connect(slot)
            side.addWidget(button)
            self.buttons[key] = button
        side.addStretch(1)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        side.addWidget(close)
        layout.addLayout(side)
        self.refill()

    def refill(self, current: str = "") -> None:
        from .icons import visible_ink
        self.list.clear()
        ink = visible_ink(self.ink)
        size = self.list.iconSize()
        for key in hatches.NAMES:
            own = key in hatches.CUSTOM
            # drawn at the list's own size: the lists' wide sample squeezed
            # into it was grey on grey in dark mode (F-37)
            row = QListWidgetItem(hatches.sample_icon(key, ink, size.width(), size.height()),
                                  hatches.display_name(key) + ("" if not own else "  (custom)"))
            row.setData(Qt.UserRole, key)
            self.list.addItem(row)
            if key == current:
                self.list.setCurrentItem(row)
        self._enable()

    def current_key(self) -> str:
        row = self.list.currentItem()
        return row.data(Qt.UserRole) if row is not None else ""

    def _enable(self) -> None:
        self.buttons["remove"].setEnabled(self.current_key() in hatches.CUSTOM)

    def add_text(self, text: str) -> list:
        """Every pattern in a .pat text, added. Their keys."""
        added = []
        for _key, (name, families) in hatches.parse_pat(text).items():
            key = hatches.add_pattern(name, families)
            if key:
                added.append(key)
        if added:
            hatches.save_custom()
            self.refill(added[-1])
        return added

    def import_file(self, path: str = "") -> list:
        if not path:
            path, _filter = QFileDialog.getOpenFileName(
                self, "Import Hatch Patterns", "", "Hatch patterns (*.pat);;All files (*)")
            if not path:
                return []
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError as problem:
            QMessageBox.warning(self, "Import Hatch Patterns", f"That file could not be read.\n\n{problem}")
            return []
        added = self.add_text(text)
        if not added:
            QMessageBox.information(self, "Import Hatch Patterns",
                                    "There were no patterns in that file that could be "
                                    "brought in (a built-in one keeps its own drawing).")
        return added

    def new_pattern(self) -> list:
        text, accepted = QInputDialog.getMultiLineText(
            self, "New Hatch Pattern",
            "As a .pat pattern: *NAME, then a line per family —\n"
            "angle, x-origin, y-origin, shift, spacing [, dash, gap, …] (inches)", EXAMPLE)
        return self.add_text(text) if accepted else []

    def remove(self) -> None:
        if hatches.remove_pattern(self.current_key()):
            hatches.save_custom()
            self.refill()
