"""Text region — annotations and labels with inline editing."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QFontMetricsF
from PySide6.QtWidgets import QGraphicsItem

from .base import PageItem
from ..core.document import Region
from ..core.typography import sans_family


class TextItem(PageItem):
    """A text annotation on the page with inline editing."""

    LINE_H = 20.0

    def __init__(self, region: Region, parent=None):
        super().__init__(region, parent)
        self.text = region.data.get("text", "")
        self.font_size = region.data.get("font_size", 10.0)
        self.bold = region.data.get("bold", False)
        self.italic = region.data.get("italic", False)
        self.color = QColor(region.data.get("color", "#000000"))
        self.bg_color = QColor(region.data.get("bg_color", "#ffffff"))
        self.bg_color.setAlpha(0)
        self.editing = False
        self.cursor_pos = 0
        self._cursor_visible = True
        self._cursor_timer = QTimer()
        self._cursor_timer.setInterval(530)
        self._cursor_timer.timeout.connect(self._blink_cursor)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)

    def _blink_cursor(self):
        self._cursor_visible = not self._cursor_visible
        self.update()

    def _font(self) -> QFont:
        font = QFont(sans_family(), int(self.font_size))
        font.setPixelSize(int(self.font_size))
        font.setBold(self.bold)
        font.setItalic(self.italic)
        return font

    # --- Editing lifecycle ---

    def start_edit(self):
        if self.editing:
            return
        self.editing = True
        self._cursor_visible = True
        self._cursor_timer.start()
        self.cursor_pos = len(self.text)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self._update_size_edit()
        self.update()

    def end_edit(self):
        if not self.editing:
            return
        self._cursor_timer.stop()
        self.editing = False
        self.text = self.text.rstrip()
        self.region.data["text"] = self.text
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not self.region.locked)
        self.update()

    def focusInEvent(self, event):
        self.start_edit()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.end_edit()
        super().focusOutEvent(event)

    # --- Keyboard input ---

    def keyPressEvent(self, event):
        if not self.editing:
            super().keyPressEvent(event)
            return

        key = event.key()
        text = event.text()

        if key == Qt.Key.Key_Escape:
            self.clearFocus()
            return

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.text = self.text[:self.cursor_pos] + "\n" + self.text[self.cursor_pos:]
            self.cursor_pos += 1
        elif key == Qt.Key.Key_Backspace:
            if self.cursor_pos > 0:
                self.text = self.text[:self.cursor_pos - 1] + self.text[self.cursor_pos:]
                self.cursor_pos -= 1
        elif key == Qt.Key.Key_Delete:
            if self.cursor_pos < len(self.text):
                self.text = self.text[:self.cursor_pos] + self.text[self.cursor_pos + 1:]
        elif key == Qt.Key.Key_Left:
            if self.cursor_pos > 0:
                self.cursor_pos -= 1
        elif key == Qt.Key.Key_Right:
            if self.cursor_pos < len(self.text):
                self.cursor_pos += 1
        elif key == Qt.Key.Key_Home:
            line_start = self.text.rfind("\n", 0, self.cursor_pos)
            self.cursor_pos = line_start + 1 if line_start >= 0 else 0
        elif key == Qt.Key.Key_End:
            line_end = self.text.find("\n", self.cursor_pos)
            self.cursor_pos = line_end if line_end >= 0 else len(self.text)
        elif text and text.isprintable():
            self.text = self.text[:self.cursor_pos] + text + self.text[self.cursor_pos:]
            self.cursor_pos += len(text)
        else:
            super().keyPressEvent(event)
            return

        self.region.data["text"] = self.text
        self._cursor_visible = True
        self._update_size_edit()
        self.update()

    # --- Mouse interaction ---

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.editing:
            pos = event.pos()
            fm = QFontMetricsF(self._font())
            lines = self.text.split("\n")
            clicked_line = int((pos.y() - 2) / self.LINE_H)
            clicked_line = max(0, min(clicked_line, len(lines) - 1))

            line = lines[clicked_line]
            best_col = 0
            best_dist = abs(pos.x() - 4)
            for i in range(1, len(line) + 1):
                x = fm.horizontalAdvance(line[:i]) + 4
                dist = abs(pos.x() - x)
                if dist < best_dist:
                    best_dist = dist
                    best_col = i

            offset = sum(len(lines[j]) + 1 for j in range(clicked_line))
            self.cursor_pos = offset + best_col
            self._cursor_visible = True
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if not self.editing:
            self.setFocus()
        event.accept()

    def insert_text_at_cursor(self, text_str: str):
        if not self.editing:
            self.start_edit()
            self.setFocus()
        self.text = self.text[:self.cursor_pos] + text_str + self.text[self.cursor_pos:]
        self.cursor_pos += len(text_str)
        self.region.data["text"] = self.text
        self._cursor_visible = True
        self._update_size_edit()
        self.update()

    def _update_size_edit(self):
        lines = self.text.split("\n")
        total_h = max(self.LINE_H * len(lines), self.LINE_H) + 4
        max_w = 100.0
        fm = QFontMetricsF(self._font())
        for line in lines:
            w = fm.horizontalAdvance(line) + 30
            max_w = max(max_w, w)
        self.region.width = max_w
        self.region.height = total_h
        self.setRect(QRectF(0, 0, max_w, total_h))

    # --- Painting ---

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.bg_color.alpha() > 0:
            painter.fillRect(self.rect(), self.bg_color)

        font = self._font()
        painter.setFont(font)
        painter.setPen(QPen(self.color))
        fm = QFontMetricsF(font)

        lines = self.text.split("\n")
        for i, line in enumerate(lines):
            y = i * self.LINE_H + 2
            painter.drawText(
                QRectF(4, y, self.rect().width() - 8, self.LINE_H),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                line,
            )

        if self.editing:
            if self._cursor_visible:
                text_before = self.text[:self.cursor_pos]
                cur_line_idx = text_before.count("\n")
                last_nl = text_before.rfind("\n")
                col = self.cursor_pos - last_nl - 1 if last_nl >= 0 else self.cursor_pos
                cur_line = lines[cur_line_idx] if cur_line_idx < len(lines) else ""
                cx = fm.horizontalAdvance(cur_line[:col]) + 4
                cy = cur_line_idx * self.LINE_H + 4
                painter.setPen(QPen(QColor(0, 0, 0), 1.5))
                painter.drawLine(int(cx), int(cy), int(cx), int(cy + self.LINE_H - 4))

            painter.setPen(QPen(QColor(0, 120, 215), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.rect().adjusted(-1, -1, 1, 1))
        else:
            self.paint_selection(painter)

    def set_text(self, text: str):
        self.text = text
        self.region.data["text"] = text
        self.update()
