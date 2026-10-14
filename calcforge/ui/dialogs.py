"""Dialogs — page setup, properties, about, etc."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QDialogButtonBox, QLabel, QLineEdit, QGroupBox,
    QTabWidget, QWidget, QTextEdit,
)

from ..core.document import PageSize, Orientation, PageSettings, PageMargins


class PageSetupDialog(QDialog):
    """Dialog for configuring page size, orientation, and margins."""

    def __init__(self, settings: PageSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Page Setup")
        self.settings = settings
        self.setMinimumWidth(350)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self._size_combo = QComboBox()
        for ps in PageSize:
            self._size_combo.addItem(ps.label, ps)
        self._size_combo.setCurrentText(settings.size.label)
        form.addRow("Page size:", self._size_combo)

        self._orient_combo = QComboBox()
        self._orient_combo.addItem("Portrait", Orientation.PORTRAIT)
        self._orient_combo.addItem("Landscape", Orientation.LANDSCAPE)
        self._orient_combo.setCurrentIndex(0 if settings.orientation == Orientation.PORTRAIT else 1)
        form.addRow("Orientation:", self._orient_combo)

        layout.addLayout(form)

        margins_group = QGroupBox("Margins (pt)")
        mg_layout = QFormLayout(margins_group)
        self._margin_left = QDoubleSpinBox()
        self._margin_left.setRange(0, 200)
        self._margin_left.setValue(settings.margins.left)
        mg_layout.addRow("Left:", self._margin_left)
        self._margin_right = QDoubleSpinBox()
        self._margin_right.setRange(0, 200)
        self._margin_right.setValue(settings.margins.right)
        mg_layout.addRow("Right:", self._margin_right)
        self._margin_top = QDoubleSpinBox()
        self._margin_top.setRange(0, 200)
        self._margin_top.setValue(settings.margins.top)
        mg_layout.addRow("Top:", self._margin_top)
        self._margin_bottom = QDoubleSpinBox()
        self._margin_bottom.setRange(0, 200)
        self._margin_bottom.setValue(settings.margins.bottom)
        mg_layout.addRow("Bottom:", self._margin_bottom)
        layout.addWidget(margins_group)

        grid_group = QGroupBox("Grid")
        grid_layout = QFormLayout(grid_group)
        self._grid_visible = QCheckBox("Show grid")
        self._grid_visible.setChecked(settings.grid_visible)
        grid_layout.addRow(self._grid_visible)
        self._grid_snap = QCheckBox("Snap to grid")
        self._grid_snap.setChecked(settings.grid_snap)
        grid_layout.addRow(self._grid_snap)
        self._grid_spacing = QDoubleSpinBox()
        self._grid_spacing.setRange(5, 100)
        self._grid_spacing.setValue(settings.grid_spacing)
        grid_layout.addRow("Spacing:", self._grid_spacing)
        layout.addWidget(grid_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_settings(self) -> PageSettings:
        return PageSettings(
            size=self._size_combo.currentData(),
            orientation=self._orient_combo.currentData(),
            margins=PageMargins(
                left=self._margin_left.value(),
                right=self._margin_right.value(),
                top=self._margin_top.value(),
                bottom=self._margin_bottom.value(),
            ),
            grid_visible=self._grid_visible.isChecked(),
            grid_snap=self._grid_snap.isChecked(),
            grid_spacing=self._grid_spacing.value(),
        )


class DocumentPropertiesDialog(QDialog):
    """Document title, author, project metadata."""

    def __init__(self, title: str = "", author: str = "", project: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Document Properties")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._title = QLineEdit(title)
        form.addRow("Title:", self._title)
        self._author = QLineEdit(author)
        form.addRow("Author:", self._author)
        self._project = QLineEdit(project)
        form.addRow("Project:", self._project)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def doc_title(self) -> str:
        return self._title.text()

    @property
    def doc_author(self) -> str:
        return self._author.text()

    @property
    def doc_project(self) -> str:
        return self._project.text()


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About SMath Studio")
        self.setFixedSize(380, 220)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>SMath Studio</h2>"))
        layout.addWidget(QLabel("Mathematical notebook with unit-aware\n"
                                "calculations, 2D plotting, and text regions."))
        layout.addWidget(QLabel(""))
        layout.addWidget(QLabel("Python/Qt reimplementation"))
        layout.addWidget(QLabel("Built with PySide6 and Pint"))
        layout.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class CalcInputDialog(QDialog):
    """Multi-line calculation input."""

    def __init__(self, lines: list[str] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Calculation")
        self.setMinimumSize(500, 300)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Enter expressions (one per line):"))
        self._editor = QTextEdit()
        self._editor.setPlainText("\n".join(lines or [""]))
        font = self._editor.font()
        font.setFamily("monospace")
        font.setPointSize(12)
        self._editor.setFont(font)
        layout.addWidget(self._editor)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def lines(self) -> list[str]:
        return self._editor.toPlainText().split("\n")
