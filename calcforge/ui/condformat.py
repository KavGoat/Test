"""Conditional formatting of equations: the dialogs (calc/condformat.py).

* Right-click an equation ▸ Conditional Formatting…: no rules, a preset, or
  its own rules (which can be saved as a preset).
* Calculation ▸ Conditional Formatting…: the document's presets, and
  which preset applies to which variable names (DCR* → DCR).

A rule sets the font colour, size, bold, underline and/or background, when
a result without units passes its test.
"""
from __future__ import annotations

import copy

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QColorDialog, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QHBoxLayout, QHeaderView, QInputDialog, QLabel, QListWidget, QPushButton, QRadioButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ..calc.condformat import DCR_EXAMPLE, OPS


class _Swatch(QPushButton):
    def __init__(self, colour, start: str = "#ffc9c9", title: str = "Background"):
        super().__init__()
        self.colour = colour
        self.start = start
        self.title = title
        self.clicked.connect(self._pick)
        self._show()

    def _show(self):
        if self.colour:
            self.setText(self.colour)
            self.setStyleSheet(f"background:{self.colour}; color:black")
        else:
            self.setText("No change")
            self.setStyleSheet("")

    def _pick(self):
        got = QColorDialog.getColor(QColor(self.colour or self.start), self, self.title)
        if got.isValid():
            self.colour = got.name()
            self._show()

    def clear(self):
        self.colour = None
        self._show()


class RulesEditor(QWidget):
    """A list of rules: test, value(s), font size, background."""

    def __init__(self, rules=None):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["Result is", "Value", "and", "Colour", "Size", "Bold",
                                              "Underline", "Background"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)
        row = QHBoxLayout()
        for text, slot in (("Add rule", lambda: self.add({"op": ">", "a": 1.0})),
                           ("Remove", self.remove), ("Up", lambda: self.move(-1)),
                           ("Down", lambda: self.move(1)),
                           ("DCR: > 1 red, ≤ 1 green", self.dcr)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        layout.addLayout(row)
        note = QLabel("Every rule that matches applies (the higher one wins where two set the "
                      "same thing). Only results without units are compared.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.set_rules(rules or [])

    def set_rules(self, rules) -> None:
        self.table.setRowCount(0)
        for rule in rules:
            self.add(rule)

    def dcr(self) -> None:
        self.set_rules(copy.deepcopy(DCR_EXAMPLE))

    def add(self, rule: dict) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        op = QComboBox()
        for key, label in OPS:
            op.addItem(label, key)
        op.setCurrentIndex(max(0, [k for k, _ in OPS].index(rule.get("op", ">"))))
        a = QDoubleSpinBox()
        b = QDoubleSpinBox()
        for spin, v in ((a, rule.get("a", 1.0)), (b, rule.get("b") or 0.0)):
            spin.setRange(-1e12, 1e12)
            spin.setDecimals(4)
            spin.setValue(float(v or 0.0))
        b.setEnabled(rule.get("op") in ("between", "outside"))
        op.currentIndexChanged.connect(lambda _i, o=op, bb=b: bb.setEnabled(o.currentData() in ("between", "outside")))
        size = QDoubleSpinBox()
        size.setRange(0, 72)
        size.setSpecialValueText("No change")
        size.setSuffix(" pt")
        size.setValue(float(rule.get("size") or 0.0))
        colour = _Swatch(rule.get("color"), "#c92a2a", "Font colour")
        bold, underline = QComboBox(), QComboBox()
        for box, key in ((bold, "bold"), (underline, "underline")):
            box.addItems(["No change", "Yes", "No"])
            box.setCurrentIndex({None: 0, True: 1, False: 2}.get(rule.get(key), 0))
        swatch = _Swatch(rule.get("bg"))
        self.table.setCellWidget(r, 0, op)
        self.table.setCellWidget(r, 1, a)
        self.table.setCellWidget(r, 2, b)
        self.table.setCellWidget(r, 3, colour)
        self.table.setCellWidget(r, 4, size)
        self.table.setCellWidget(r, 5, bold)
        self.table.setCellWidget(r, 6, underline)
        self.table.setCellWidget(r, 7, swatch)

    def remove(self) -> None:
        r = self.table.currentRow()
        if r < 0:
            r = self.table.rowCount() - 1
        if r >= 0:
            self.table.removeRow(r)

    def move(self, step: int) -> None:
        rules = self.rules()
        r = self.table.currentRow()
        t = r + step
        if 0 <= r < len(rules) and 0 <= t < len(rules):
            rules[r], rules[t] = rules[t], rules[r]
            self.set_rules(rules)
            self.table.setCurrentCell(t, 0)

    def rules(self) -> list:
        out = []
        for r in range(self.table.rowCount()):
            op = self.table.cellWidget(r, 0).currentData()
            a = self.table.cellWidget(r, 1).value()
            b = self.table.cellWidget(r, 2).value() if op in ("between", "outside") else None
            colour = self.table.cellWidget(r, 3).colour
            size = self.table.cellWidget(r, 4).value() or None
            flags = [{0: None, 1: True, 2: False}[self.table.cellWidget(r, k).currentIndex()]
                     for k in (5, 6)]
            bg = self.table.cellWidget(r, 7).colour
            out.append({"op": op, "a": a, "b": b, "color": colour, "size": size, "bold": flags[0],
                        "underline": flags[1], "bg": bg})
        return out


def _store(document) -> dict:
    store = document.settings.calc_rules
    if not isinstance(store, dict):
        store = {}
    store.setdefault("presets", {})
    store.setdefault("by_name", [])
    document.settings.calc_rules = store
    return store


class EquationRulesDialog(QDialog):
    """The selected equations' rules: none, a preset, or their own."""

    def __init__(self, window, items):
        super().__init__(window)
        self.setWindowTitle("Conditional Formatting")
        self.window = window
        self.items = items
        first = items[0]
        store = _store(window.document)
        layout = QVBoxLayout(self)
        self.none = QRadioButton("No rules of its own (document rules by name still apply)")
        self.preset = QRadioButton("Use a preset:")
        self.own = QRadioButton("Its own rules:")
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(sorted(store["presets"]))
        row = QHBoxLayout()
        row.addWidget(self.preset)
        row.addWidget(self.preset_combo, 1)
        layout.addWidget(self.none)
        layout.addLayout(row)
        layout.addWidget(self.own)
        self.editor = RulesEditor(copy.deepcopy(first.cond_rules or []))
        layout.addWidget(self.editor)
        save = QPushButton("Save these rules as a preset…")
        save.clicked.connect(self.save_preset)
        layout.addWidget(save, 0, Qt.AlignLeft)
        manage = QPushButton("Document rules (presets, by variable name)…")
        manage.clicked.connect(self._document_rules)
        layout.addWidget(manage, 0, Qt.AlignLeft)
        if first.cond_rules:
            self.own.setChecked(True)
        elif first.cond_preset:
            self.preset.setChecked(True)
            self.preset_combo.setCurrentText(first.cond_preset)
        else:
            self.none.setChecked(True)
        self.preset.setEnabled(self.preset_combo.count() > 0)
        self.editor.table.cellClicked.connect(lambda *_: self.own.setChecked(True))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(640, 420)

    def _document_rules(self) -> None:
        """Presets made, renamed or deleted there show here straight away."""
        open_document_rules(self.window)
        now = self.preset_combo.currentText()
        self.preset_combo.clear()
        self.preset_combo.addItems(sorted(_store(self.window.document)["presets"]))
        self.preset_combo.setCurrentText(now)
        self.preset.setEnabled(self.preset_combo.count() > 0)

    def save_preset(self, name: str = "") -> None:
        if not name:
            if not getattr(self.window, "interactive_prompts", True):
                return
            name, ok = QInputDialog.getText(self, "Save preset", "Name of the preset (e.g. DCR):")
            if not ok or not name.strip():
                return
        name = name.strip()
        _store(self.window.document)["presets"][name] = self.editor.rules()
        self.window.document.modified = True
        if self.preset_combo.findText(name) < 0:
            self.preset_combo.addItem(name)
        self.preset_combo.setCurrentText(name)
        self.preset.setEnabled(True)
        self.preset.setChecked(True)

    def accept(self) -> None:
        if self.own.isChecked():
            rules, preset = self.editor.rules(), ""
        elif self.preset.isChecked():
            rules, preset = None, self.preset_combo.currentText()
        else:
            rules, preset = None, ""
        set_rules(self.window, self.items, rules, preset)
        super().accept()


def set_rules(window, items, rules, preset: str) -> None:
    """Give equations their own rules or a preset (or neither): one undo step."""
    items = [i for i in items if not getattr(i, "locked", False)]
    if not items:
        return
    view = window.view
    view.begin_snapshot(view.involved_frames(*items))
    for item in items:
        item.cond_rules = copy.deepcopy(rules) if rules else None
        item.cond_preset = preset or ""
        item.relayout()
        item.update()
    view.commit_snapshot("Conditional formatting")


class DocumentRulesDialog(QDialog):
    """The document's presets, and the presets that apply by variable name."""

    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle("Conditional Formatting Rules")
        self.window = window
        store = copy.deepcopy(_store(window.document))
        self.presets = store["presets"]
        self.renamed: dict = {}                  # old preset name -> new, for the equations using it
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Presets</b> — named sets of rules"))
        top = QHBoxLayout()
        side = QVBoxLayout()
        self.names = QListWidget()
        self.names.addItems(sorted(self.presets))
        side.addWidget(self.names)
        for text, slot in (("New", self.new_preset), ("Rename", self.rename_preset),
                           ("Delete", self.delete_preset)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            side.addWidget(b)
        top.addLayout(side)
        self.editor = RulesEditor()
        top.addWidget(self.editor, 1)
        layout.addLayout(top)
        layout.addWidget(QLabel("<b>By variable name</b> — equations that define or show a matching "
                                "name and have no rules of their own use the preset "
                                "(* matches anything: DCR*, *.util)"))
        self.by_name = QTableWidget(0, 2)
        self.by_name.setHorizontalHeaderLabels(["Name pattern", "Preset"])
        self.by_name.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.by_name.verticalHeader().setVisible(False)
        layout.addWidget(self.by_name)
        row = QHBoxLayout()
        add = QPushButton("Add name rule")
        add.clicked.connect(lambda: self.add_name_rule("", ""))
        rm = QPushButton("Remove")
        rm.clicked.connect(self.remove_name_rule)
        row.addWidget(add)
        row.addWidget(rm)
        row.addStretch(1)
        layout.addLayout(row)
        for pattern, preset in store["by_name"]:
            self.add_name_rule(pattern, preset)
        self._current = None
        self.names.currentTextChanged.connect(self._switch)
        if self.names.count():
            self.names.setCurrentRow(0)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(760, 560)

    def _keep(self) -> None:
        if self._current is not None and self._current in self.presets:
            self.presets[self._current] = self.editor.rules()

    def _switch(self, name: str) -> None:
        self._keep()
        self._current = name or None
        self.editor.set_rules(copy.deepcopy(self.presets.get(name, [])))

    def new_preset(self, name: str = "") -> None:
        if not name:
            if not getattr(self.window, "interactive_prompts", True):
                return
            name, ok = QInputDialog.getText(self, "New preset", "Name:")
            if not ok or not name.strip():
                return
        name = name.strip()
        self._keep()
        self.presets.setdefault(name, copy.deepcopy(DCR_EXAMPLE))
        if not self.names.findItems(name, Qt.MatchExactly):
            self.names.addItem(name)
        self.names.setCurrentRow(self.names.count() - 1)
        self._refresh_presets()

    def rename_preset(self, name: str = "") -> None:
        old = self._current
        if old is None:
            return
        if not name:
            if not getattr(self.window, "interactive_prompts", True):
                return
            name, ok = QInputDialog.getText(self, "Rename preset", "Name:", text=old)
            if not ok:
                return
        name = name.strip()
        if not name or name == old or name in self.presets:
            return
        self._keep()
        using = [r for r in range(self.by_name.rowCount())
                 if self.by_name.cellWidget(r, 1).currentText() == old]
        self.presets[name] = self.presets.pop(old)
        first = next((k for k, v in self.renamed.items() if v == old), old)
        self.renamed[first] = name
        self._current = name
        self.names.currentItem().setText(name)
        self._refresh_presets()
        for r in using:
            self.by_name.cellWidget(r, 1).setCurrentText(name)

    def delete_preset(self) -> None:
        if self._current is None:
            return
        self.presets.pop(self._current, None)
        self._current = None
        self.names.takeItem(self.names.currentRow())
        self._refresh_presets()

    def add_name_rule(self, pattern: str, preset: str) -> None:
        r = self.by_name.rowCount()
        self.by_name.insertRow(r)
        self.by_name.setItem(r, 0, QTableWidgetItem(pattern))
        combo = QComboBox()
        combo.addItems(sorted(self.presets))
        combo.setCurrentText(preset)
        self.by_name.setCellWidget(r, 1, combo)

    def remove_name_rule(self) -> None:
        """The chosen name rule, or the last one when none is chosen."""
        r = self.by_name.currentRow()
        self.by_name.removeRow(r if r >= 0 else self.by_name.rowCount() - 1)

    def _refresh_presets(self) -> None:
        for r in range(self.by_name.rowCount()):
            combo = self.by_name.cellWidget(r, 1)
            now = combo.currentText()
            combo.clear()
            combo.addItems(sorted(self.presets))
            # a deleted preset leaves its rule with none (not quietly another)
            combo.setCurrentIndex(combo.findText(now))

    def store(self) -> dict:
        self._keep()
        by_name = []
        for r in range(self.by_name.rowCount()):
            item = self.by_name.item(r, 0)
            pattern = item.text().strip() if item else ""
            preset = self.by_name.cellWidget(r, 1).currentText()
            if pattern and preset:
                by_name.append([pattern, preset])
        return {"presets": self.presets, "by_name": by_name}

    def accept(self) -> None:
        apply_document_rules(self.window, self.store(), self.renamed)
        super().accept()


def apply_document_rules(window, store: dict, renamed: dict | None = None) -> None:
    """The document's presets and name rules; equations using a renamed
    preset follow it to its new name."""
    window.document.settings.calc_rules = copy.deepcopy(store)
    window.document.modified = True
    if renamed:
        from ..items.calc import CalcItem
        for page in window.document.pages:
            frame = getattr(page, "frame", None)
            for item in frame.markups() if frame is not None else ():
                if isinstance(item, CalcItem) and item.cond_preset in renamed:
                    item.cond_preset = renamed[item.cond_preset]
            for record in getattr(page, "_pending_items", ()):     # pages not built yet
                if record.get("cond_preset") in renamed:
                    record["cond_preset"] = renamed[record["cond_preset"]]
    redraw_all(window)


def redraw_all(window) -> None:
    from ..items.calc import CalcItem
    for page in window.document.pages:
        frame = getattr(page, "frame", None)
        if frame is None:
            continue
        for item in frame.markups():
            if isinstance(item, CalcItem) and item.region is not None:
                item.relayout()
                item.update()


def open_document_rules(window) -> None:
    dialog = DocumentRulesDialog(window)
    if not getattr(window, "interactive_prompts", True):
        window._last_rules_dialog = dialog
        return
    dialog.exec()


def open_equation_rules(window, items) -> None:
    dialog = EquationRulesDialog(window, items)
    if not getattr(window, "interactive_prompts", True):
        window._last_rules_dialog = dialog
        return
    dialog.exec()
