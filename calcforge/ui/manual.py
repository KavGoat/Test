"""Help ▸ User Manual: the manual (docs/USER_MANUAL.md, shipped as
``calcforge/data/USER_MANUAL.md``) in a window of its own.

The Markdown is shown as it is written, by Qt's own reader (``setMarkdown``);
down the left are its headings, and a click on one goes there; above, a search
box finds a word in the page — Enter or Next for the next one, Shift+Enter or
Previous for the one before, every match marked. The window follows the
application's theme, can be resized, and remembers its size and where its
divider was. ``open_at`` opens it at a heading.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEvent, QSignalBlocker, Qt, QUrl
from PySide6.QtGui import (QColor, QDesktopServices, QKeySequence, QPalette, QShortcut,
                           QTextCharFormat, QTextCursor, QTextDocument, QTextFrameFormat,
                           QTextLength, QTextTable)
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QSplitter, QTextBrowser,
                               QTextEdit, QToolButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from ..settings import app_settings

#: Where the manual ships: beside the dictionary, in the package's data.
MANUAL_PATH = Path(__file__).resolve().parent.parent / "data" / "USER_MANUAL.md"

#: The headings listed on the left, down to this level (# is 1).
CONTENTS_DEPTH = 4

_COMMENT = re.compile(r"<!--.*?-->\n?", re.S)
_SETTINGS = "manual/"


def manual_text() -> str:
    """The manual's Markdown, without the generator's markers."""
    try:
        text = MANUAL_PATH.read_text(encoding="utf-8")
    except OSError:
        return ("# User Manual\n\nThe manual could not be found. It belongs at "
                f"`{MANUAL_PATH}`.\n")
    return _COMMENT.sub("", text)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


class ManualWindow(QWidget):
    """The manual: its contents on the left, the page on the right, a search
    box above."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        self.setObjectName("userManual")
        # its keys are its own: the main window's filter does not cancel the
        # canvas on its Escape or keep its function keys (mainwindow.OWN_KEYS)
        self.setProperty("cf_own_keys", True)
        self.setWindowTitle("CalcForge User Manual")
        self.setMinimumSize(520, 360)
        self._headings: list[tuple[int, str, int]] = []     # (level, words, block)
        self._items: list[QTreeWidgetItem] = []
        self._restyling = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        bar = QHBoxLayout()
        bar.setSpacing(4)
        self.search = QLineEdit()
        self.search.setObjectName("manualSearch")
        self.search.setPlaceholderText("Find in the manual…")
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip("Enter: the next match · Shift+Enter: the one before")
        self.search.textEdited.connect(lambda _text: self.find(from_start_of_match=True))
        self.search.installEventFilter(self)
        bar.addWidget(self.search, 1)
        self.previous_button = QToolButton()
        self.previous_button.setObjectName("manualPrevious")
        self.previous_button.setText("Previous")
        self.previous_button.setToolTip("The match before (Shift+Enter, Shift+F3)")
        self.previous_button.clicked.connect(lambda: self.find(backwards=True))
        bar.addWidget(self.previous_button)
        self.next_button = QToolButton()
        self.next_button.setObjectName("manualNext")
        self.next_button.setText("Next")
        self.next_button.setToolTip("The next match (Enter, F3)")
        self.next_button.clicked.connect(lambda: self.find())
        bar.addWidget(self.next_button)
        self.found_label = QLabel("")
        self.found_label.setObjectName("manualFound")
        self.found_label.setMinimumWidth(90)
        bar.addWidget(self.found_label)
        outer.addLayout(bar)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setObjectName("manualSplitter")
        self.contents = QTreeWidget()
        self.contents.setObjectName("manualContents")
        self.contents.setHeaderHidden(True)
        self.contents.setIndentation(12)
        self.contents.itemClicked.connect(self._heading_clicked)
        self.contents.itemActivated.connect(self._heading_clicked)
        self.splitter.addWidget(self.contents)
        self.browser = QTextBrowser()
        self.browser.setObjectName("manualText")
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(self._link)
        self.browser.verticalScrollBar().valueChanged.connect(self._follow_scroll)
        self.splitter.addWidget(self.browser)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([260, 760])
        outer.addWidget(self.splitter, 1)

        for keys, slot in ((QKeySequence.Find, self._focus_search),
                           (QKeySequence(Qt.Key_F3), lambda: self.find()),
                           (QKeySequence(Qt.SHIFT | Qt.Key_F3), lambda: self.find(backwards=True)),
                           (QKeySequence(Qt.Key_Escape), self.close)):
            shortcut = QShortcut(keys, self)
            shortcut.activated.connect(slot)

        self.load()
        self._restore()

    # -- the page -----------------------------------------------------------
    def load(self) -> None:
        """Read the manual and lay it out, keeping the place being read."""
        bar = self.browser.verticalScrollBar()
        kept = bar.value()
        self.browser.setMarkdown(manual_text())
        self._style_tables()
        self._read_headings()
        bar.setValue(kept)

    def _style_tables(self) -> None:
        """Tables drawn with thin rules in the theme's colours, so they read in
        dark and light alike."""
        palette = self.palette()
        rule = palette.color(QPalette.Mid)
        document = self.browser.document()
        for frame in document.rootFrame().childFrames():
            if not isinstance(frame, QTextTable):
                continue
            table_format = frame.format()
            table_format.setBorder(1)
            table_format.setBorderBrush(rule)
            table_format.setBorderStyle(QTextFrameFormat.BorderStyle_Solid)
            table_format.setBorderCollapse(True)
            table_format.setCellPadding(3)
            table_format.setCellSpacing(0)
            table_format.setWidth(QTextLength(QTextLength.PercentageLength, 100))
            frame.setFormat(table_format)

    def _read_headings(self) -> None:
        self._headings = []
        block = self.browser.document().begin()
        while block.isValid():
            level = block.blockFormat().headingLevel()
            if 0 < level <= CONTENTS_DEPTH and block.text().strip():
                self._headings.append((level, block.text().strip(), block.blockNumber()))
            block = block.next()
        self.contents.clear()
        self._items = []
        parents: list[tuple[int, QTreeWidgetItem]] = []
        for index, (level, words, _number) in enumerate(self._headings):
            while parents and parents[-1][0] >= level:
                parents.pop()
            item = QTreeWidgetItem([words])
            item.setData(0, Qt.UserRole, index)
            item.setToolTip(0, words)
            if parents:
                parents[-1][1].addChild(item)
            else:
                self.contents.addTopLevelItem(item)
            parents.append((level, item))
            self._items.append(item)
        for item, (level, _words, _number) in zip(self._items, self._headings):
            item.setExpanded(level <= 2)

    def headings(self) -> list[str]:
        """The headings listed on the left, in order."""
        return [words for _level, words, _number in self._headings]

    def _block_top(self, number: int) -> int:
        document = self.browser.document()
        block = document.findBlockByNumber(number)
        return int(document.documentLayout().blockBoundingRect(block).top())

    def show_heading(self, index: int) -> None:
        """Bring heading *index* (of ``headings()``) to the top of the page."""
        if not 0 <= index < len(self._headings):
            return
        number = self._headings[index][2]
        document = self.browser.document()
        cursor = QTextCursor(document.findBlockByNumber(number))
        self.browser.setTextCursor(cursor)
        self.browser.verticalScrollBar().setValue(self._block_top(number))
        self._mark_heading(index)

    def open_at(self, heading: str) -> bool:
        """Show the window at the heading whose words are, or start with, or
        contain *heading* (ignoring case and punctuation). False if there is
        none — the window is shown anyway."""
        self.show_window()
        wanted = _slug(heading)
        slugs = [_slug(words) for words in self.headings()]
        for test in (lambda s: s == wanted, lambda s: s.startswith(wanted),
                     lambda s: wanted in s):
            for index, slug in enumerate(slugs):
                if wanted and test(slug):
                    self.show_heading(index)
                    return True
        return False

    def show_window(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def _heading_clicked(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        index = item.data(0, Qt.UserRole)
        if index is not None:
            self.show_heading(int(index))

    def _mark_heading(self, index: int) -> None:
        if 0 <= index < len(self._items):
            with QSignalBlocker(self.contents):
                self.contents.setCurrentItem(self._items[index])
            self.contents.scrollToItem(self._items[index])

    def _follow_scroll(self, value: int) -> None:
        """The heading being read is the one picked on the left."""
        current = -1
        for index, (_level, _words, number) in enumerate(self._headings):
            if self._block_top(number) <= value + 4:
                current = index
            else:
                break
        if current >= 0:
            self._mark_heading(current)

    def _link(self, url: QUrl) -> None:
        if url.scheme() in ("http", "https", "mailto"):
            QDesktopServices.openUrl(url)
            return
        if url.fragment():
            self.open_at(url.fragment().replace("-", " "))

    # -- finding words ----------------------------------------------------------
    def _focus_search(self) -> None:
        self.search.setFocus(Qt.ShortcutFocusReason)
        self.search.selectAll()

    def matches(self, word: Optional[str] = None) -> list[QTextCursor]:
        """Every place *word* (the search box's, by default) is found."""
        word = self.search.text() if word is None else word
        found: list[QTextCursor] = []
        if not word:
            return found
        document = self.browser.document()
        cursor = QTextCursor(document)
        while len(found) < 5000:
            cursor = document.find(word, cursor)
            if cursor.isNull():
                break
            found.append(QTextCursor(cursor))
        return found

    def find(self, backwards: bool = False, from_start_of_match: bool = False) -> bool:
        """The next (or previous) place the search box's words are, wrapping
        round at the end. True when there is one."""
        word = self.search.text()
        everywhere = self.matches(word)
        self._mark_matches(everywhere)
        if not word:
            self.found_label.setText("")
            return False
        if not everywhere:
            self.found_label.setText("Not found")
            return False
        document = self.browser.document()
        cursor = QTextCursor(self.browser.textCursor())
        if from_start_of_match:
            cursor.setPosition(cursor.selectionStart())
        flags = QTextDocument.FindBackward if backwards else QTextDocument.FindFlag(0)
        if backwards and cursor.hasSelection():
            cursor.setPosition(cursor.selectionStart())
        got = document.find(word, cursor, flags)
        if got.isNull():
            start = QTextCursor(document)
            if backwards:
                start.movePosition(QTextCursor.End)
            got = document.find(word, start, flags)
        if got.isNull():
            self.found_label.setText("Not found")
            return False
        self.browser.setTextCursor(got)
        self.browser.ensureCursorVisible()
        at = next((k for k, c in enumerate(everywhere)
                   if c.selectionStart() == got.selectionStart()), 0)
        self.found_label.setText(f"{at + 1} of {len(everywhere)}")
        return True

    def _mark_matches(self, everywhere: list[QTextCursor]) -> None:
        marks = []
        look = QTextCharFormat()
        look.setBackground(QColor(255, 214, 10, 110))
        for cursor in everywhere:
            mark = QTextEdit.ExtraSelection()
            mark.cursor = cursor
            mark.format = look
            marks.append(mark)
        self.browser.setExtraSelections(marks)

    # -- the window -----------------------------------------------------------------
    def eventFilter(self, watched, event) -> bool:              # noqa: N802
        if watched is self.search and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.find(backwards=bool(event.modifiers() & Qt.ShiftModifier))
                return True
            if event.key() == Qt.Key_Escape:
                self.close()             # the box keeps Escape to itself otherwise
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event) -> None:                     # noqa: N802
        """Esc closes it, F3 and Shift+F3 find again, Ctrl+F goes to the
        search box — wherever in the window the keyboard is."""
        key, mods = event.key(), event.modifiers()
        if key == Qt.Key_Escape:
            self.close()
        elif key == Qt.Key_F3:
            self.find(backwards=bool(mods & Qt.ShiftModifier))
        elif key == Qt.Key_F and mods & Qt.ControlModifier:
            self._focus_search()
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def changeEvent(self, event) -> None:                       # noqa: N802
        if event.type() in (QEvent.PaletteChange, QEvent.StyleChange) \
                and not self._restyling and self._headings:
            self._restyling = True
            try:
                self._style_tables()
            finally:
                self._restyling = False
        super().changeEvent(event)

    def _restore(self) -> None:
        settings = app_settings()
        geometry = settings.value(_SETTINGS + "geometry")
        if geometry is None or not self.restoreGeometry(geometry):
            self.resize(1040, 760)
        divider = settings.value(_SETTINGS + "splitter")
        if divider is not None:
            self.splitter.restoreState(divider)

    def remember(self) -> None:
        settings = app_settings()
        settings.setValue(_SETTINGS + "geometry", self.saveGeometry())
        settings.setValue(_SETTINGS + "splitter", self.splitter.saveState())

    def hideEvent(self, event) -> None:                         # noqa: N802
        self.remember()
        super().hideEvent(event)

    def resizeEvent(self, event) -> None:                       # noqa: N802
        super().resizeEvent(event)
        if self.isVisible():
            self.remember()
