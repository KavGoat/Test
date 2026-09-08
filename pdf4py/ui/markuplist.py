"""Markups panel: a sortable list of every annotation in the document."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout,
                               QHeaderView, QLineEdit, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ..document import Markup, PdfDocument

COLUMNS = ["Page", "Type", "Subject", "Author", "Text"]

STYLE = """
QTableWidget {
    background: #1f2335;
    gridline-color: #292e42;
    border: none;
    font-size: 11px;
    color: #c0caf5;
    selection-background-color: #283457;
    selection-color: #c0caf5;
}
QTableWidget::item:selected { background: #283457; color: #c0caf5; }
QTableWidget::item:hover { background: #24283b; }
QHeaderView::section {
    background: #24283b;
    color: #a9b1d6;
    border: none;
    border-bottom: 1px solid #292e42;
    padding: 5px 8px;
    font-weight: 600;
    font-size: 11px;
}
"""


class MarkupListPanel(QWidget):
    """Live table of every annotation, linked to the canvas."""

    markup_selected = Signal(int, int)  # page_index, xref

    def __init__(self, document: PdfDocument, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.document = document
        self._all_markups: list[Markup] = []
        self._filtered: list[Markup] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Filter row
        filter_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter markups...")
        self._search.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self._search)

        self._type_filter = QComboBox()
        self._type_filter.addItem("All types")
        self._type_filter.setMinimumWidth(100)
        self._type_filter.currentTextChanged.connect(lambda _: self._apply_filter())
        filter_row.addWidget(self._type_filter)
        layout.addLayout(filter_row)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(len(COLUMNS))
        self._table.setHorizontalHeaderLabels(COLUMNS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSortingEnabled(True)
        self._table.setStyleSheet(STYLE)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.cellClicked.connect(self._on_click)
        layout.addWidget(self._table)

        # Status
        self._count_label = QLineEdit("0 markups")
        self._count_label.setReadOnly(True)
        self._count_label.setFrame(False)
        self._count_label.setStyleSheet("color: #565f89; font-size: 11px; background: transparent;")
        layout.addWidget(self._count_label)

    def reload(self) -> None:
        self._all_markups = self.document.all_markups()
        types = sorted({m.subtype for m in self._all_markups})
        current = self._type_filter.currentText()
        self._type_filter.blockSignals(True)
        self._type_filter.clear()
        self._type_filter.addItem("All types")
        self._type_filter.addItems(types)
        if current in types:
            self._type_filter.setCurrentText(current)
        self._type_filter.blockSignals(False)
        self._apply_filter()

    def _apply_filter(self, _text: str = "") -> None:
        search = self._search.text().lower()
        type_filter = self._type_filter.currentText()

        self._filtered = []
        for m in self._all_markups:
            if type_filter != "All types" and m.subtype != type_filter:
                continue
            if search:
                haystack = f"{m.subtype} {m.subject} {m.author} {m.text}".lower()
                if search not in haystack:
                    continue
            self._filtered.append(m)

        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(self._filtered))
        for row, m in enumerate(self._filtered):
            self._table.setItem(row, 0, self._num_item(m.page_index + 1))
            self._table.setItem(row, 1, QTableWidgetItem(m.subtype))
            self._table.setItem(row, 2, QTableWidgetItem(m.subject or "—"))
            self._table.setItem(row, 3, QTableWidgetItem(m.author or "—"))
            text = m.text[:60] + "..." if len(m.text) > 60 else m.text
            self._table.setItem(row, 4, QTableWidgetItem(text or "—"))
        self._table.setSortingEnabled(True)
        self._count_label.setText(f"{len(self._filtered)} markup(s)")

    @staticmethod
    def _num_item(value: int) -> QTableWidgetItem:
        item = QTableWidgetItem()
        item.setData(Qt.DisplayRole, value)
        return item

    def _on_click(self, row: int, _col: int) -> None:
        if 0 <= row < len(self._filtered):
            m = self._filtered[row]
            self.markup_selected.emit(m.page_index, m.xref)

    def select_markup(self, page_index: int, xref: int) -> None:
        """Highlight the row for a given markup (called when canvas selection changes)."""
        for row, m in enumerate(self._filtered):
            if m.xref == xref and m.page_index == page_index:
                self._table.selectRow(row)
                return
