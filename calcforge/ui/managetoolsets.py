"""Bluebeam's Manage Tool Sets: every set in one list, a tick for the ones the
Tool Chest shows, and the buttons that make, bring in, rename, remove and
order them."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QInputDialog,
                               QListWidget, QListWidgetItem, QMessageBox, QPushButton,
                               QVBoxLayout)

from . import toolsets

#: The sets that are always there and always at the top, in this order.
FIXED = (toolsets.MY_TOOLS, toolsets.RECENT_TOOLS)


class ManageToolSetsDialog(QDialog):
    """Changes are made as they are clicked, as in Revu: Close only closes."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Manage Tool Sets")
        self.setObjectName("manageToolSets")
        self.resize(420, 360)
        layout = QHBoxLayout(self)

        self.list = QListWidget()
        self.list.setObjectName("toolSetList")
        self.list.itemChanged.connect(self._ticked)
        self.list.currentRowChanged.connect(lambda *_: self._enable())
        layout.addWidget(self.list, 1)

        side = QVBoxLayout()
        self.buttons = {}
        for key, text, slot in (("add", "Add…", self.add),
                                ("import", "Import…", self.import_set),
                                ("rename", "Rename…", self.rename),
                                ("remove", "Remove", self.remove),
                                (None, "", None),
                                ("up", "Move Up", lambda: self.move(-1)),
                                ("down", "Move Down", lambda: self.move(1))):
            if key is None:
                side.addSpacing(12)
                continue
            button = QPushButton(text)
            button.setObjectName(f"toolSet_{key}")
            button.clicked.connect(slot)
            side.addWidget(button)
            self.buttons[key] = button
        side.addStretch(1)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        side.addWidget(close)
        layout.addLayout(side)
        self.refill()

    # -- the list ----------------------------------------------------------
    def refill(self, current: str = "") -> None:
        current = current or self.current_name()
        self.sets = toolsets.load_toolsets()
        self.list.blockSignals(True)
        self.list.clear()
        for group in self.sets:
            row = QListWidgetItem(f"{group.name}  ({len(group.entries)})")
            row.setData(Qt.UserRole, group.name)
            row.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
            row.setCheckState(Qt.Unchecked if group.hidden else Qt.Checked)
            row.setToolTip("Ticked: shown in the Tool Chest")
            self.list.addItem(row)
            if group.name == current:
                self.list.setCurrentItem(row)
        self.list.blockSignals(False)
        if self.list.currentRow() < 0 and self.list.count():
            self.list.setCurrentRow(0)
        self._enable()

    def current_name(self) -> str:
        row = self.list.currentItem() if hasattr(self, "list") else None
        return row.data(Qt.UserRole) if row is not None else ""

    def current(self):
        name = self.current_name()
        return next((g for g in self.sets if g.name == name), None)

    def _enable(self) -> None:
        name = self.current_name()
        fixed = name in FIXED
        movable = [g.name for g in self.sets if g.name not in FIXED]
        self.buttons["rename"].setEnabled(bool(name) and not fixed)
        self.buttons["remove"].setEnabled(bool(name) and name != toolsets.MY_TOOLS)
        self.buttons["up"].setEnabled(not fixed and name in movable and movable.index(name) > 0)
        self.buttons["down"].setEnabled(not fixed and name in movable
                                        and movable.index(name) < len(movable) - 1)

    def _save(self, keep: str = "") -> None:
        toolsets.save_toolsets(self.sets)
        self.window.toolsets_panel.rebuild()
        self.refill(keep)

    # -- what the buttons do ----------------------------------------------
    def _ticked(self, row) -> None:
        group = next((g for g in self.sets if g.name == row.data(Qt.UserRole)), None)
        if group is not None:
            group.hidden = row.checkState() != Qt.Checked
            self._save(group.name)

    def set_shown(self, name: str, shown: bool) -> None:
        for index in range(self.list.count()):
            row = self.list.item(index)
            if row.data(Qt.UserRole) == name:
                row.setCheckState(Qt.Checked if shown else Qt.Unchecked)

    def _ask_name(self, title: str, text: str = "") -> str:
        name, accepted = QInputDialog.getText(self, title, "Name:", text=text)
        name = name.strip()
        if not accepted or not name:
            return ""
        if any(g.name == name for g in self.sets) and name != text:
            QMessageBox.information(self, title, f"There is already a set called “{name}”.")
            return ""
        return name

    def add(self, name: str = "") -> None:
        name = name or self._ask_name("Add Tool Set")
        if name and not any(g.name == name for g in self.sets):
            self.sets.append(toolsets.ToolSet(name))
            self._save(name)

    def import_set(self) -> None:
        if self.window.import_toolset():
            self.refill()

    def rename(self, name: str = "") -> None:
        group = self.current()
        if group is None or group.name in FIXED:
            return
        name = name or self._ask_name("Rename Tool Set", group.name)
        if name and name != group.name:
            group.name = name
            self._save(name)

    def remove(self, ask: bool = True) -> None:
        group = self.current()
        if group is None or group.name == toolsets.MY_TOOLS:
            return
        if ask and QMessageBox.question(
                self, "Remove Tool Set",
                f"Remove “{group.name}” and its {len(group.entries)} tool(s)?") != QMessageBox.Yes:
            return
        self.sets.remove(group)
        self._save()

    def move(self, step: int) -> None:
        group = self.current()
        if group is None or group.name in FIXED:
            return
        index = self.sets.index(group)
        target = index + step
        if target < 0 or target >= len(self.sets) or self.sets[target].name in FIXED:
            return
        self.sets[index], self.sets[target] = self.sets[target], self.sets[index]
        self._save(group.name)
