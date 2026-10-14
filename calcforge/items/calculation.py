"""Calculation region — unit-aware, typeset math expressions with inline editing."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QFontMetricsF
from PySide6.QtWidgets import QGraphicsItem

from .base import PageItem
from ..core.document import Region
from ..core.evaluator import EvalContext, eval_line, EvalResult
from ..core.mathrender import MathLayout, MathPainter, TextBox
from ..core.typography import serif_family


class CalculationItem(PageItem):
    """A calculation region on the page with inline editing."""

    LINE_H = 22.0

    def __init__(self, region: Region, parent=None):
        super().__init__(region, parent)
        self.lines: list[str] = region.data.get("lines", [""])
        self.results: list[EvalResult] = []
        self.editing = False
        self.cursor_line = 0
        self.cursor_pos = 0
        self._cursor_visible = True
        self._cursor_timer = QTimer()
        self._cursor_timer.setInterval(530)
        self._cursor_timer.timeout.connect(self._blink_cursor)
        self._math_layout = MathLayout(14.0)
        self._math_painter = MathPainter()
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)

    def _blink_cursor(self):
        self._cursor_visible = not self._cursor_visible
        self.update()

    def _font(self) -> QFont:
        font = QFont(serif_family(), 14)
        font.setPixelSize(14)
        return font

    def _font_italic(self) -> QFont:
        font = self._font()
        font.setItalic(True)
        return font

    def evaluate(self, ctx: EvalContext) -> list[EvalResult]:
        self.results = []
        for line in self.lines:
            result = eval_line(line, ctx)
            self.results.append(result)
        self._update_size()
        return self.results

    def _update_size(self):
        total_h = max(self.LINE_H * len(self.lines), self.LINE_H)
        max_w = 100.0
        fm = QFontMetricsF(self._font())
        for i, line in enumerate(self.lines):
            display = self.results[i].display_text if i < len(self.results) else line
            w = fm.horizontalAdvance(display) + 30
            max_w = max(max_w, w)
        self.region.width = max_w
        self.region.height = total_h
        self.setRect(QRectF(0, 0, max_w, total_h))

    def _update_size_edit(self):
        total_h = max(self.LINE_H * len(self.lines), self.LINE_H)
        max_w = 100.0
        fm = QFontMetricsF(self._font())
        for line in self.lines:
            w = fm.horizontalAdvance(line) + 30
            max_w = max(max_w, w)
        self.region.width = max_w
        self.region.height = total_h
        self.setRect(QRectF(0, 0, max_w, total_h))

    # --- Editing lifecycle ---

    def start_edit(self):
        if self.editing:
            return
        self.editing = True
        self._cursor_visible = True
        self._cursor_timer.start()
        self.cursor_line = len(self.lines) - 1
        self.cursor_pos = len(self.lines[self.cursor_line])
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self._update_size_edit()
        self.update()

    def end_edit(self):
        if not self.editing:
            return
        self._cursor_timer.stop()
        self.editing = False
        while len(self.lines) > 1 and not self.lines[-1].strip():
            self.lines.pop()
        self.region.data["lines"] = self.lines
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
            self.lines.insert(self.cursor_line + 1, "")
            self.cursor_line += 1
            self.cursor_pos = 0
        elif key == Qt.Key.Key_Backspace:
            if self.cursor_pos > 0:
                line = self.lines[self.cursor_line]
                self.lines[self.cursor_line] = line[:self.cursor_pos - 1] + line[self.cursor_pos:]
                self.cursor_pos -= 1
            elif self.cursor_line > 0:
                prev = self.lines[self.cursor_line - 1]
                self.cursor_pos = len(prev)
                self.lines[self.cursor_line - 1] = prev + self.lines[self.cursor_line]
                self.lines.pop(self.cursor_line)
                self.cursor_line -= 1
        elif key == Qt.Key.Key_Delete:
            line = self.lines[self.cursor_line]
            if self.cursor_pos < len(line):
                self.lines[self.cursor_line] = line[:self.cursor_pos] + line[self.cursor_pos + 1:]
            elif self.cursor_line < len(self.lines) - 1:
                self.lines[self.cursor_line] = line + self.lines[self.cursor_line + 1]
                self.lines.pop(self.cursor_line + 1)
        elif key == Qt.Key.Key_Left:
            if self.cursor_pos > 0:
                self.cursor_pos -= 1
            elif self.cursor_line > 0:
                self.cursor_line -= 1
                self.cursor_pos = len(self.lines[self.cursor_line])
        elif key == Qt.Key.Key_Right:
            if self.cursor_pos < len(self.lines[self.cursor_line]):
                self.cursor_pos += 1
            elif self.cursor_line < len(self.lines) - 1:
                self.cursor_line += 1
                self.cursor_pos = 0
        elif key == Qt.Key.Key_Up:
            if self.cursor_line > 0:
                self.cursor_line -= 1
                self.cursor_pos = min(self.cursor_pos, len(self.lines[self.cursor_line]))
        elif key == Qt.Key.Key_Down:
            if self.cursor_line < len(self.lines) - 1:
                self.cursor_line += 1
                self.cursor_pos = min(self.cursor_pos, len(self.lines[self.cursor_line]))
        elif key == Qt.Key.Key_Home:
            self.cursor_pos = 0
        elif key == Qt.Key.Key_End:
            self.cursor_pos = len(self.lines[self.cursor_line])
        elif text and text.isprintable():
            line = self.lines[self.cursor_line]
            self.lines[self.cursor_line] = line[:self.cursor_pos] + text + line[self.cursor_pos:]
            self.cursor_pos += len(text)
        else:
            super().keyPressEvent(event)
            return

        self.region.data["lines"] = self.lines
        self._cursor_visible = True
        self._update_size_edit()
        self.update()

    # --- Mouse interaction ---

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.editing:
            pos = event.pos()
            clicked_line = int(pos.y() / self.LINE_H)
            clicked_line = max(0, min(clicked_line, len(self.lines) - 1))
            self.cursor_line = clicked_line

            fm = QFontMetricsF(self._font_italic())
            line = self.lines[self.cursor_line]
            best_pos = 0
            best_dist = abs(pos.x() - 4)
            for i in range(1, len(line) + 1):
                x = fm.horizontalAdvance(line[:i]) + 4
                dist = abs(pos.x() - x)
                if dist < best_dist:
                    best_dist = dist
                    best_pos = i
            self.cursor_pos = best_pos
            self._cursor_visible = True
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if not self.editing:
            self.setFocus()
        event.accept()

    def insert_text_at_cursor(self, text: str):
        if not self.editing:
            self.start_edit()
            self.setFocus()
        line = self.lines[self.cursor_line]
        self.lines[self.cursor_line] = line[:self.cursor_pos] + text + line[self.cursor_pos:]
        self.cursor_pos += len(text)
        self.region.data["lines"] = self.lines
        self._cursor_visible = True
        self._update_size_edit()
        self.update()

    # --- Painting ---

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font_italic = self._font_italic()
        font_normal = self._font()

        if self.editing:
            self._paint_editing(painter, font_italic)
        else:
            self._paint_results(painter, font_italic, font_normal)
            self.paint_selection(painter)

    def _paint_editing(self, painter: QPainter, font: QFont):
        painter.setFont(font)
        fm = QFontMetricsF(font)

        for i, line in enumerate(self.lines):
            y = i * self.LINE_H
            painter.setPen(QPen(QColor(0, 0, 0)))
            painter.drawText(
                QRectF(4, y, self.rect().width() - 8, self.LINE_H),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                line,
            )

        if self._cursor_visible:
            line = self.lines[self.cursor_line]
            cx = fm.horizontalAdvance(line[:self.cursor_pos]) + 4
            cy = self.cursor_line * self.LINE_H + 2
            painter.setPen(QPen(QColor(0, 0, 0), 1.5))
            painter.drawLine(int(cx), int(cy), int(cx), int(cy + self.LINE_H - 4))

        painter.setPen(QPen(QColor(0, 120, 215), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect().adjusted(-1, -1, 1, 1))

    def _paint_results(self, painter: QPainter, font_italic: QFont, font_normal: QFont):
        for i, line in enumerate(self.lines):
            y = i * self.LINE_H
            if i < len(self.results):
                result = self.results[i]
                if result.error:
                    painter.setPen(QPen(QColor(200, 0, 0)))
                    painter.setFont(font_italic)
                    painter.drawText(
                        QRectF(4, y, self.rect().width() - 8, self.LINE_H),
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                        f"{line}  → Error: {result.error}",
                    )
                elif result.defined_name:
                    painter.setPen(QPen(QColor(0, 0, 0)))
                    painter.setFont(font_italic)
                    parts = line.split(":=") if ":=" in line else line.split(":", 1)
                    lhs = parts[0].strip()
                    painter.drawText(
                        QRectF(4, y, self.rect().width() - 8, self.LINE_H),
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                        f"{lhs} := {result.display_text}",
                    )
                else:
                    painter.setPen(QPen(QColor(0, 0, 0)))
                    painter.setFont(font_italic)
                    expr_text = line.split("->")[0].strip() if "->" in line else line
                    display = result.display_text
                    if result.is_bool:
                        label = "true" if result.value.value else "false"
                        color = QColor(0, 128, 0) if result.value.value else QColor(200, 0, 0)
                        painter.drawText(
                            QRectF(4, y, self.rect().width() - 8, self.LINE_H),
                            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                            f"{expr_text} = ",
                        )
                        painter.setPen(QPen(color))
                        bw = painter.fontMetrics().horizontalAdvance(f"{expr_text} = ")
                        painter.drawText(
                            QRectF(4 + bw, y, self.rect().width(), self.LINE_H),
                            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                            label,
                        )
                    else:
                        painter.drawText(
                            QRectF(4, y, self.rect().width() - 8, self.LINE_H),
                            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                            f"{expr_text} = {display}",
                        )
            else:
                painter.setPen(QPen(QColor(0, 0, 0)))
                painter.setFont(font_italic)
                painter.drawText(
                    QRectF(4, y, self.rect().width() - 8, self.LINE_H),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    line,
                )

    def set_lines(self, lines: list[str]):
        self.lines = lines
        self.region.data["lines"] = lines

    def add_line(self, text: str = ""):
        self.lines.append(text)
        self.region.data["lines"] = self.lines
