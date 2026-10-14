"""Dock panels — Variables, Functions, Problems, Markups, Thumbnails."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPixmap, QPainter, QBrush
from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QTreeWidget, QTreeWidgetItem, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QLineEdit, QHeaderView, QSizePolicy,
    QMenu, QScrollArea, QFrame,
)

from ..core.evaluator import EvalContext
from ..core.problems import ProblemCollector, Problem, Severity
from ..core.functions import list_functions


class VariablesPanel(QDockWidget):
    """Shows all defined variables with their values."""

    variable_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Variables", parent)
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea |
                             Qt.DockWidgetArea.RightDockWidgetArea)
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Name", "Value", "Source"])
        self._tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._tree.setAlternatingRowColors(True)
        self._tree.setRootIsDecorated(False)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter variables...")
        self._filter.textChanged.connect(self._apply_filter)
        layout.addWidget(self._filter)
        layout.addWidget(self._tree)
        self.setWidget(container)

    def update_variables(self, ctx: EvalContext):
        self._tree.clear()
        for name, val in sorted(ctx.variables.items()):
            item = QTreeWidgetItem([name, repr(val.auto_display()), ""])
            self._tree.addTopWidgetItem(item) if False else self._tree.addTopLevelItem(item)

    def _apply_filter(self, text: str):
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            visible = text.lower() in item.text(0).lower() if text else True
            item.setHidden(not visible)

    def _on_double_click(self, item: QTreeWidgetItem, col: int):
        self.variable_clicked.emit(item.text(0))


class FunctionsPanel(QDockWidget):
    """Lists all available functions with help text."""

    function_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Functions", parent)
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea |
                             Qt.DockWidgetArea.RightDockWidgetArea)
        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._on_double_click)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter functions...")
        self._filter.textChanged.connect(self._apply_filter)
        layout.addWidget(self._filter)
        layout.addWidget(self._list)
        self.setWidget(container)
        self._populate()

    def _populate(self):
        for name, doc in list_functions():
            item = QListWidgetItem(f"{name}  —  {doc}")
            item.setData(Qt.ItemDataRole.UserRole, name)
            self._list.addItem(item)

    def _apply_filter(self, text: str):
        for i in range(self._list.count()):
            item = self._list.item(i)
            visible = text.lower() in item.text().lower() if text else True
            item.setHidden(not visible)

    def _on_double_click(self, item: QListWidgetItem):
        name = item.data(Qt.ItemDataRole.UserRole)
        self.function_clicked.emit(name)


class ProblemsPanel(QDockWidget):
    """Shows evaluation errors and warnings."""

    problem_clicked = Signal(object)

    def __init__(self, parent=None):
        super().__init__("Problems", parent)
        self.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea |
                             Qt.DockWidgetArea.TopDockWidgetArea)
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Severity", "Location", "Message"])
        self._tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._tree.setRootIsDecorated(False)
        self._tree.setAlternatingRowColors(True)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        self.setWidget(self._tree)

    def update_problems(self, collector: ProblemCollector):
        self._tree.clear()
        for p in collector.all:
            icon = "⛔" if p.severity == Severity.ERROR else "⚠"
            item = QTreeWidgetItem([icon, p.location, p.message])
            if p.severity == Severity.ERROR:
                item.setForeground(2, QColor(200, 0, 0))
            else:
                item.setForeground(2, QColor(180, 140, 0))
            item.setData(0, Qt.ItemDataRole.UserRole, p)
            self._tree.addTopLevelItem(item)

    def _on_double_click(self, item: QTreeWidgetItem, col: int):
        problem = item.data(0, Qt.ItemDataRole.UserRole)
        if problem:
            self.problem_clicked.emit(problem)


class ThumbnailPanel(QDockWidget):
    """Page thumbnail strip for navigation and page management."""

    page_selected = Signal(int)
    page_add_requested = Signal(int)
    page_delete_requested = Signal(int)
    page_duplicate_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__("Pages", parent)
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea |
                             Qt.DockWidgetArea.RightDockWidgetArea)
        self._list = QListWidget()
        self._list.setIconSize(self._list.iconSize())
        self._list.setSpacing(4)
        self._list.currentRowChanged.connect(self._on_row_changed)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._context_menu)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(2, 2, 2, 2)
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("+")
        add_btn.setToolTip("Add page")
        add_btn.clicked.connect(lambda: self.page_add_requested.emit(self._list.currentRow()))
        btn_layout.addWidget(add_btn)
        del_btn = QPushButton("−")
        del_btn.setToolTip("Delete page")
        del_btn.clicked.connect(lambda: self.page_delete_requested.emit(self._list.currentRow()))
        btn_layout.addWidget(del_btn)
        dup_btn = QPushButton("⎘")
        dup_btn.setToolTip("Duplicate page")
        dup_btn.clicked.connect(lambda: self.page_duplicate_requested.emit(self._list.currentRow()))
        btn_layout.addWidget(dup_btn)
        layout.addLayout(btn_layout)
        layout.addWidget(self._list)
        self.setWidget(container)

    def update_pages(self, page_count: int):
        self._list.clear()
        for i in range(page_count):
            item = QListWidgetItem(f"Page {i + 1}")
            self._list.addItem(item)

    def _on_row_changed(self, row: int):
        if row >= 0:
            self.page_selected.emit(row)

    def _context_menu(self, pos):
        row = self._list.currentRow()
        if row < 0:
            return
        menu = QMenu(self)
        menu.addAction("Add page after", lambda: self.page_add_requested.emit(row))
        menu.addAction("Duplicate page", lambda: self.page_duplicate_requested.emit(row))
        menu.addAction("Delete page", lambda: self.page_delete_requested.emit(row))
        menu.exec(self._list.mapToGlobal(pos))


class MarkupsPanel(QDockWidget):
    """List of all annotations in the document."""

    markup_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Markups", parent)
        self.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea |
                             Qt.DockWidgetArea.RightDockWidgetArea)
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Page", "Type", "Subject", "Value", "Author"])
        self._tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._tree.setRootIsDecorated(False)
        self._tree.setAlternatingRowColors(True)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        self.setWidget(self._tree)

    def update_markups(self, regions):
        self._tree.clear()
        for r in regions:
            if r.type in ("line", "arrow", "rectangle", "ellipse", "polygon",
                          "cloud", "text", "stamp", "measure"):
                item = QTreeWidgetItem([
                    str(r.page_index + 1),
                    r.type.title(),
                    r.data.get("subject", ""),
                    r.data.get("display_value", ""),
                    r.data.get("author", ""),
                ])
                item.setData(0, Qt.ItemDataRole.UserRole, r.id)
                self._tree.addTopLevelItem(item)

    def _on_double_click(self, item: QTreeWidgetItem, col: int):
        rid = item.data(0, Qt.ItemDataRole.UserRole)
        if rid:
            self.markup_clicked.emit(rid)
