"""Bookmarks panel: PDF outline navigation and editing."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QInputDialog, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout,
                               QWidget)

from ..document import Bookmark, PdfDocument

STYLE = """
QListWidget { background: #fafafa; border: 1px solid #ddd; border-radius: 3px; }
QListWidget::item { padding: 4px 8px; }
QListWidget::item:selected { background: #dce9fb; color: #10233d; }
QListWidget::item:hover:!selected { background: #eef1f5; }
"""


class BookmarkPanel(QWidget):
    """Shows the PDF's outline and lets the user jump, add, or remove entries."""

    page_requested = Signal(int)

    def __init__(self, document: PdfDocument, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.document = document

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._list = QListWidget()
        self._list.setStyleSheet(STYLE)
        self._list.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self._list)

        btn_row = QHBoxLayout()
        self._add_btn = QPushButton("+")
        self._add_btn.setFixedWidth(30)
        self._add_btn.setToolTip("Add a bookmark for the current page")
        self._add_btn.clicked.connect(self._on_add)
        self._remove_btn = QPushButton("−")
        self._remove_btn.setFixedWidth(30)
        self._remove_btn.setToolTip("Remove the selected bookmark")
        self._remove_btn.clicked.connect(self._on_remove)
        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(self._remove_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._bookmarks: list[Bookmark] = []
        self._current_page = 0

    def set_current_page(self, page: int) -> None:
        self._current_page = page

    def reload(self) -> None:
        self._list.clear()
        self._bookmarks = self.document.bookmarks()
        for bm in self._bookmarks:
            indent = "  " * max(bm.level - 1, 0)
            item = QListWidgetItem(f"{indent}{bm.title}  (p.{bm.page + 1})")
            item.setData(Qt.UserRole, bm.page)
            self._list.addItem(item)

    def _on_double_click(self, item: QListWidgetItem) -> None:
        page = item.data(Qt.UserRole)
        if page is not None:
            self.page_requested.emit(page)

    def _on_add(self) -> None:
        title, ok = QInputDialog.getText(self, "Add Bookmark",
                                         f"Bookmark name for page {self._current_page + 1}:")
        if ok and title.strip():
            self.document.add_bookmark(title.strip(), self._current_page)
            self.reload()

    def _on_remove(self) -> None:
        row = self._list.currentRow()
        if row >= 0:
            self.document.remove_bookmark(row)
            self.reload()
