"""The Search panel: words in the drawing and in the markups, on every page.

Bluebeam's Search lists every hit of a phrase in the document's own text;
here the markups are searched as well, and what was typed into the markups
can be replaced — one hit, or all of them as one undo step. The drawing's own
text is not markup and is left as it is.
"""
from __future__ import annotations

import re

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import (QCheckBox, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

DRAWING = "drawing"
MARKUP = "markup"


class SearchPanel(QWidget):
    """Find in the drawing and the markups; replace in the markups."""

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.hits: list[dict] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        grid = QGridLayout()
        self.query = QLineEdit()
        self.query.setObjectName("searchQuery")
        self.query.setPlaceholderText("Find")
        self.query.setClearButtonEnabled(True)
        self.query.returnPressed.connect(self.run)
        find = QPushButton("Find")
        find.clicked.connect(self.run)
        grid.addWidget(self.query, 0, 0)
        grid.addWidget(find, 0, 1)
        self.replacement = QLineEdit()
        self.replacement.setObjectName("searchReplace")
        self.replacement.setPlaceholderText("Replace with")
        replace = QPushButton("Replace")
        replace.setToolTip("Replace the chosen hit (markups only)")
        replace.clicked.connect(self.replace_current)
        grid.addWidget(self.replacement, 1, 0)
        grid.addWidget(replace, 1, 1)
        layout.addLayout(grid)
        options = QHBoxLayout()
        self.in_drawing = QCheckBox("Drawing")
        self.in_drawing.setToolTip("The PDF's own text, on every page")
        self.in_drawing.setChecked(True)
        self.in_markups = QCheckBox("Markups")
        self.in_markups.setToolTip("Words typed into markups, their subjects and comments")
        self.in_markups.setChecked(True)
        self.match_case = QCheckBox("Case")
        self.match_case.setToolTip("Match case (markups; the drawing ignores case)")
        self.whole_word = QCheckBox("Whole word")
        self.whole_word.setToolTip("Whole words only (markups)")
        for box in (self.in_drawing, self.in_markups, self.match_case, self.whole_word):
            options.addWidget(box)
        options.addStretch(1)
        layout.addLayout(options)
        self.results = QTreeWidget()
        self.results.setHeaderLabels(["Page", "Found", "In"])
        self.results.setRootIsDecorated(False)
        self.results.setAlternatingRowColors(True)
        self.results.itemClicked.connect(lambda node, _c: self.show_hit(node))
        self.results.currentItemChanged.connect(
            lambda node, _old: node is not None and self.show_hit(node))
        layout.addWidget(self.results, 1)
        bottom = QHBoxLayout()
        self.summary = QLabel("")
        bottom.addWidget(self.summary, 1)
        replace_all = QPushButton("Replace all")
        replace_all.setToolTip("Replace every hit in the markups, as one undo step")
        replace_all.clicked.connect(self.replace_all)
        bottom.addWidget(replace_all)
        layout.addLayout(bottom)

    # -- finding -----------------------------------------------------------
    def _pattern(self):
        needle = self.query.text()
        if not needle:
            return None
        body = re.escape(needle)
        if self.whole_word.isChecked():
            body = rf"\b{body}\b"
        return re.compile(body, 0 if self.match_case.isChecked() else re.IGNORECASE)

    def run(self) -> list[dict]:
        """Search every page; list and return the hits."""
        from ..io.pdfsearch import find_on_page

        self.hits = []
        needle = self.query.text()
        pattern = self._pattern()
        document = self.window.document
        if pattern is not None:
            for index, page in enumerate(document.pages):
                if self.in_drawing.isChecked() and page.pdf_key \
                        and page.pdf_page_index is not None:
                    data = document.asset(page.pdf_key)
                    for box, context in find_on_page(
                            data, int(page.pdf_page_index), needle,
                            page.width_pt, page.height_pt):
                        self.hits.append({"kind": DRAWING, "page": index,
                                          "box": QRectF(*box), "context": context})
                if self.in_markups.isChecked() and page.frame is not None:
                    for item in page.frame.ordered_markups():
                        if getattr(item, "from_drawing", False):
                            continue
                        for field, text in _searchable(item):
                            for match in pattern.finditer(text):
                                start = max(match.start() - 30, 0)
                                self.hits.append({
                                    "kind": MARKUP, "page": index, "item": item,
                                    "field": field, "start": match.start(),
                                    "length": match.end() - match.start(),
                                    "context": text[start:match.end() + 30]
                                    .replace("\n", " ")})
        self._fill()
        return self.hits

    def _fill(self) -> None:
        self.results.blockSignals(True)
        self.results.clear()
        for number, hit in enumerate(self.hits):
            where = ("Drawing" if hit["kind"] == DRAWING
                     else hit["item"].display_name())
            node = QTreeWidgetItem([str(hit["page"] + 1), hit["context"], where])
            node.setData(0, Qt.UserRole, number)
            self.results.addTopLevelItem(node)
        for column in range(3):
            self.results.resizeColumnToContents(column)
        self.results.blockSignals(False)
        drawing = sum(1 for hit in self.hits if hit["kind"] == DRAWING)
        self.summary.setText(f"{len(self.hits)} found — {drawing} in the drawing, "
                             f"{len(self.hits) - drawing} in markups")
        self._mark_all()

    def _mark_all(self, current=None) -> None:
        """Outline every drawing hit on the page; the chosen one strongest."""
        marks = []
        for hit in self.hits:
            if hit["kind"] != DRAWING:
                continue
            frame = self.window.document.pages[hit["page"]].frame
            if frame is None:
                continue
            marks.append((frame.mapRectToScene(hit["box"]), hit is current))
        self.window.view.set_search_marks(marks)

    def show_hit(self, node) -> None:
        number = node.data(0, Qt.UserRole)
        if number is None or not 0 <= number < len(self.hits):
            return
        hit = self.hits[number]
        if hit["kind"] == MARKUP:
            self.window.reveal_markup(hit["page"], hit["item"].uid)
            self._mark_all()
            return
        frame = self.window.document.pages[hit["page"]].frame
        if frame is None:
            return
        self.window.go_to_page(hit["page"])
        self.window.view.centerOn(frame.mapRectToScene(hit["box"]).center())
        self._mark_all(current=hit)

    # -- replacing ---------------------------------------------------------
    def replace_current(self) -> int:
        node = self.results.currentItem()
        if node is None:
            return 0
        number = node.data(0, Qt.UserRole)
        hit = self.hits[number] if number is not None and number < len(self.hits) else None
        if hit is None or hit["kind"] != MARKUP:
            self.summary.setText("Only words in markups can be replaced")
            return 0
        return self._replace([hit])

    def replace_all(self) -> int:
        return self._replace([hit for hit in self.hits if hit["kind"] == MARKUP])

    def _replace(self, hits) -> int:
        if not hits:
            return 0
        view = self.window.view
        view.end_item_edit()
        view.begin_snapshot(view.all_frames())
        new = self.replacement.text()
        changed = 0
        # From the end of each field backwards, so earlier positions hold.
        for hit in sorted(hits, key=lambda h: (id(h["item"]), h["field"], -h["start"])):
            item = hit["item"]
            if hit["field"] == "text" and hasattr(item, "doc"):
                cursor = QTextCursor(item.doc)
                cursor.setPosition(hit["start"])
                cursor.setPosition(hit["start"] + hit["length"], QTextCursor.KeepAnchor)
                cursor.insertText(new)
                item.written = item.doc.toPlainText()
            else:
                text = getattr(item, hit["field"], "") or ""
                setattr(item, hit["field"],
                        text[:hit["start"]] + new + text[hit["start"] + hit["length"]:])
            item.touch()
            item.update()
            changed += 1
        view.commit_snapshot(f"Replace ({changed})")
        self.window.refresh_lists()
        self.run()
        self.summary.setText(f"Replaced {changed} — " + self.summary.text())
        return changed


def _searchable(item) -> list[tuple[str, str]]:
    """The words on a markup that can be searched, by where they are kept."""
    fields = []
    if hasattr(item, "doc") and isinstance(item.doc, QTextDocument):
        fields.append(("text", item.doc.toPlainText()))
    for field in ("subject", "comment", "label"):
        value = getattr(item, field, "")
        if isinstance(value, str) and value:
            fields.append((field, value))
    return fields
