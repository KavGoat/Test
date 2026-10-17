"""Revu's line-style Manage…: every style the line lists offer, each drawn,
and bringing in an AutoCAD .lin file or writing a style of one's own. The
built-in styles stay; one's own can be taken out again. Laid out as Hatch
Patterns is (hatchpatterns.py)."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QPushButton, QVBoxLayout)

from ..items import linestyles
from ..items.base import DASH_ARRAYS


class LineStylesDialog(QDialog):
    def __init__(self, parent=None, ink: str = "#000000"):
        super().__init__(parent)
        self.ink = ink
        self.setWindowTitle("Line Styles")
        self.setObjectName("lineStyles")
        self.resize(460, 420)
        layout = QHBoxLayout(self)
        self.list = QListWidget()
        self.list.setObjectName("lineStyleList")
        self.list.setIconSize(QSize(96, 22))
        self.list.currentRowChanged.connect(lambda *_: self._enable())
        layout.addWidget(self.list, 1)
        side = QVBoxLayout()
        self.buttons = {}
        for key, text, slot in (("import", "Import…", self.import_file),
                                ("new", "New…", self.new_style),
                                ("remove", "Remove", self.remove)):
            button = QPushButton(text)
            button.setObjectName(f"lineStyle_{key}")
            button.clicked.connect(lambda _=False, s=slot: s())
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
        from .panels import _line_style_icon, line_style_name
        self.list.clear()
        ink = visible_ink(self.ink)
        for name in DASH_ARRAYS:
            own = name in linestyles.CUSTOM
            row = QListWidgetItem(_line_style_icon(name, ink, 1),
                                  line_style_name(name) + ("  (custom)" if own else ""))
            row.setData(Qt.UserRole, name)
            self.list.addItem(row)
            if name == current:
                self.list.setCurrentItem(row)
        self._enable()

    def current_key(self) -> str:
        row = self.list.currentItem()
        return row.data(Qt.UserRole) if row is not None else ""

    def _enable(self) -> None:
        self.buttons["remove"].setEnabled(self.current_key() in linestyles.CUSTOM)

    def add_styles(self, found: dict) -> list:
        added = [key for key in (linestyles.add_style(name, steps)
                                 for name, steps in found.items()) if key]
        if added:
            linestyles.save_custom()
            self.refill(added[-1])
        return added

    def import_file(self, path: str = "", unit: str = "") -> list:
        """Every simple line type in an AutoCAD .lin file, added. Lengths are
        read in inches, or millimetres for an ISO file (acadiso.lin)."""
        if not path:
            path, _filter = QFileDialog.getOpenFileName(
                self, "Import Line Styles", "", "AutoCAD line types (*.lin);;All files (*)")
            if not path:
                return []
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError as problem:
            QMessageBox.warning(self, "Import Line Styles",
                                f"That file could not be read.\n\n{problem}")
            return []
        unit = unit or ("mm" if "iso" in path.lower() else "in")
        added = self.add_styles(linestyles.parse_lin(text, unit))
        if not added:
            QMessageBox.information(self, "Import Line Styles",
                                    "There were no line types in that file that could be "
                                    "brought in (only dashes, gaps and dots can be).")
        return added

    def new_style(self, name: str = "", pattern: str = "") -> str:
        """A style of one's own: a name, and its dashes and gaps in points."""
        if not name:
            editor = NewLineStyleDialog(self, self.ink)
            if editor.exec() != QDialog.Accepted:
                return ""
            name, pattern = editor.name.text(), editor.pattern.text()
        steps = linestyles.parse_dashes(pattern)
        if not steps:
            QMessageBox.warning(self, "New Line Style",
                                "A line style is a dash and a gap, or several: "
                                "for example 6, 2, 1, 2 (points).")
            return ""
        added = self.add_styles({name: steps})
        if not added:
            QMessageBox.warning(self, "New Line Style",
                                "That name is a built-in line style's, or there is none.")
            return ""
        return added[0]

    def remove(self) -> None:
        if linestyles.remove_style(self.current_key()):
            linestyles.save_custom()
            self.refill()


class NewLineStyleDialog(QDialog):
    """A name, the dashes and gaps, and the line drawn as it will be."""

    def __init__(self, parent=None, ink: str = "#000000"):
        super().__init__(parent)
        self.ink = ink
        self.setWindowTitle("New Line Style")
        self.setObjectName("newLineStyle")
        form = QFormLayout(self)
        self.name = QLineEdit()
        self.name.setObjectName("lineStyleName")
        self.name.setPlaceholderText("e.g. Fence")
        form.addRow("Name:", self.name)
        self.pattern = QLineEdit("6, 2, 1, 2")
        self.pattern.setObjectName("lineStylePattern")
        self.pattern.setToolTip("Dash, gap, dash, gap… in points")
        form.addRow("Dashes and gaps (pt):", self.pattern)
        self.preview = QLabel()
        self.preview.setObjectName("lineStylePreview")
        form.addRow("Preview:", self.preview)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.ok = buttons.button(QDialogButtonBox.Ok)
        self.name.textChanged.connect(self._show)
        self.pattern.textChanged.connect(self._show)
        self._show()

    def _show(self) -> None:
        from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
        from .icons import visible_ink
        steps = linestyles.parse_dashes(self.pattern.text())
        picture = QPixmap(200, 20)
        picture.fill(Qt.transparent)
        if steps:
            painter = QPainter(picture)
            painter.setRenderHint(QPainter.Antialiasing, True)
            pen = QPen(QColor(visible_ink(self.ink)), 2.0)
            pen.setDashPattern([step / 2.0 for step in steps])
            pen.setCapStyle(Qt.FlatCap)
            painter.setPen(pen)
            painter.drawLine(2, 10, 198, 10)
            painter.end()
        self.preview.setPixmap(picture)
        self.ok.setEnabled(bool(steps and self.name.text().strip()))
