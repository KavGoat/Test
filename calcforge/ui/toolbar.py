"""Toolbars for the main window."""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QAction, QActionGroup, QIcon, QKeySequence
from PySide6.QtWidgets import QToolBar, QToolButton, QComboBox, QLabel


class DrawingToolbar(QToolBar):
    """Toolbar for selecting drawing/creation tools."""

    tool_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Tools", parent)
        self.setMovable(False)
        self._group = QActionGroup(self)
        self._group.setExclusive(True)

        tools = [
            ("Select", "select", "Esc", "Select and move items"),
            ("Pen", "pen", "P", "Freehand drawing"),
            ("Highlighter", "highlighter", "K", "Highlighter"),
            ("Line", "line", "L", "Draw a line"),
            ("Arrow", "arrow", "A", "Draw an arrow"),
            ("Rectangle", "rectangle", "R", "Draw a rectangle"),
            ("Ellipse", "ellipse", "E", "Draw an ellipse"),
            ("Cloud", "cloud", "C", "Revision cloud"),
            ("Text", "text", "T", "Add text annotation"),
            ("Note", "note", "N", "Sticky note"),
            ("Stamp", "stamp", "S", "Status stamp"),
            ("Calc", "calculation", "M", "Calculation region"),
            ("Table", "table", "B", "Spreadsheet table"),
            ("Plot", "plot", "G", "Function plot"),
            ("Measure", "measure", "", "Measurement tool"),
        ]

        for label, tool_id, shortcut, tooltip in tools:
            action = QAction(label, self)
            action.setCheckable(True)
            action.setToolTip(f"{tooltip} [{shortcut}]" if shortcut else tooltip)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            action.setData(tool_id)
            action.triggered.connect(lambda checked, t=tool_id: self.tool_selected.emit(t))
            self._group.addAction(action)
            self.addAction(action)
            if tool_id == "select":
                action.setChecked(True)
            if tool_id in ("highlighter", "note", "stamp", "plot"):
                self.addSeparator()

    def set_tool(self, tool_id: str):
        for action in self._group.actions():
            if action.data() == tool_id:
                action.setChecked(True)
                break


class ViewToolbar(QToolBar):
    """Toolbar for zoom controls."""

    zoom_fit_page = Signal()
    zoom_fit_width = Signal()
    zoom_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__("View", parent)
        self.setMovable(False)

        fit_page = QAction("Fit Page", self)
        fit_page.setShortcut(QKeySequence("Ctrl+0"))
        fit_page.setToolTip("Fit page [Ctrl+0]")
        fit_page.triggered.connect(self.zoom_fit_page.emit)
        self.addAction(fit_page)

        fit_width = QAction("Fit Width", self)
        fit_width.setShortcut(QKeySequence("Ctrl+1"))
        fit_width.setToolTip("Fit width [Ctrl+1]")
        fit_width.triggered.connect(self.zoom_fit_width.emit)
        self.addAction(fit_width)

        self.addSeparator()
        self._zoom_combo = QComboBox()
        self._zoom_combo.setEditable(True)
        self._zoom_combo.addItems(["50%", "75%", "100%", "125%", "150%", "200%", "300%"])
        self._zoom_combo.setCurrentText("100%")
        self._zoom_combo.currentTextChanged.connect(self._on_zoom_text)
        self.addWidget(QLabel(" Zoom: "))
        self.addWidget(self._zoom_combo)

    def _on_zoom_text(self, text: str):
        try:
            val = float(text.replace("%", "")) / 100.0
            if 0.1 <= val <= 10.0:
                self.zoom_changed.emit(val)
        except ValueError:
            pass
