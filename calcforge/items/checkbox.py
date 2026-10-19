"""The Checkbox markup: a column of options, each with a box to tick.

The user, 2026-10-19: "Create a new markup type called Checkbox … similar to
the checkbox used in the big PDF I sent. I can add as many options as I want.
… Should be like one markup with all the options inside it, be like a text
box so Alt+Z auto-fits, and making the width smaller would wrap the text onto
the line below, and only text size actually makes the whole thing bigger."

So it *is* a text box. Each paragraph of its words is one option; a box is
drawn at the start of each paragraph's first line, and the words are set in
from the left by the box and a gap of the same width, so a line that wraps
hangs under the words and not under the box. The box is sized from the font
size alone: a wider or narrower markup wraps its words afresh and never
changes the boxes.

Which options are ticked is kept beside the words, one flag per paragraph,
and follows its option as lines are added, taken away, split or joined while
typing (:meth:`CheckboxItem._follow_the_words`).
"""
from __future__ import annotations

import difflib
import math
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QPainter, QPainterPath, QPen, QPolygonF,
                           QTextBlockFormat, QTextCursor)

from .base import register_item
from .text import TextItem, _blocks

#: Box shapes, in the order the lists offer them, and their names.
SHAPES = (("square", "Square"), ("rounded", "Rounded square"),
          ("circle", "Circle"), ("diamond", "Diamond"))
#: What a ticked box shows, and its name.
MARKS = (("tick", "Tick"), ("cross", "Cross"), ("filled", "Filled"), ("dot", "Dot"))

SHAPE_NAMES = dict(SHAPES)
MARK_NAMES = dict(MARKS)

#: What a new Checkbox says until it is typed into.
DEFAULT_OPTIONS = "Option 1"

#: A box is about the height of a capital letter: this share of the font size.
BOX_SHARE = 0.75
#: The box's outline, as a share of the box (the stamp's: about a twelfth).
OUTLINE_SHARE = 1.0 / 12.0
#: The tick's stroke, as a share of the box (the stamp's: about a sixth).
TICK_SHARE = 1.0 / 6.0
#: The space between options, as a share of the font size, on top of the
#: line itself: a single line of 10 pt Helvetica is about 11.5 pt, so the
#: rows are about 1.6 times the text height apart, as on the stamp.
OPTION_GAP = 0.45


def _ticks_after(old_rows: list, old: list, rows: list) -> list:
    """Which of *rows* are ticked, given which of *old_rows* were.

    A line kept is kept with its tick; a line typed into keeps it; a line
    split in two leaves it on the first half; two lines joined are ticked if
    either was; a new line starts unticked.
    """
    old = (list(old) + [False] * len(old_rows))[:len(old_rows)]
    ticks = [False] * len(rows)
    matcher = difflib.SequenceMatcher(None, old_rows, rows, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            ticks[j1:j2] = old[i1:i2]
        elif tag == "replace":
            was, now = i2 - i1, j2 - j1
            if was == now:
                ticks[j1:j2] = old[i1:i2]
            elif now < was:                      # joined
                for k in range(now - 1):
                    ticks[j1 + k] = old[i1 + k]
                ticks[j2 - 1] = any(old[i1 + now - 1:i2])
            else:                                # split
                for k in range(was):
                    ticks[j1 + k] = old[i1 + k]
    return ticks


def box_path(shape: str, box: QRectF, inset: float = 0.0) -> QPainterPath:
    """The outline of a box of *shape*."""
    box = box.adjusted(inset, inset, -inset, -inset)
    path = QPainterPath()
    if shape == "circle":
        path.addEllipse(box)
    elif shape == "rounded":
        radius = box.width() * 0.25
        path.addRoundedRect(box, radius, radius)
    elif shape == "diamond":
        centre = box.center()
        path.addPolygon(QPolygonF([QPointF(centre.x(), box.top()),
                                   QPointF(box.right(), centre.y()),
                                   QPointF(centre.x(), box.bottom()),
                                   QPointF(box.left(), centre.y()),
                                   QPointF(centre.x(), box.top())]))
        path.closeSubpath()
    else:
        path.addRect(box)
    return path


def draw_mark(painter: QPainter, mark: str, shape: str, box: QRectF, ink: QColor) -> None:
    """What a ticked box of *shape* shows: a tick, a cross, the box filled,
    or a dot (the box's shape, smaller, filled)."""
    side = box.width()
    if mark in ("filled", "dot"):
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(ink))
        painter.drawPath(box_path(shape, box, side * 0.25 if mark == "dot" else 0.0))
        return
    pen = QPen(ink)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setBrush(Qt.NoBrush)
    if mark == "cross":
        pen.setWidthF(max(side / 7.0, 0.1))
        painter.setPen(pen)
        inner = box.adjusted(side * 0.22, side * 0.22, -side * 0.22, -side * 0.22)
        painter.drawLine(inner.topLeft(), inner.bottomRight())
        painter.drawLine(inner.topRight(), inner.bottomLeft())
        return
    # the stamp's tick: heavy, a short stroke down from the box's left edge
    # at half its height to near its foot, then a long one up just past its
    # top right-hand corner — nearly a right angle between them (the user's
    # WSP stamp; the tick before ran far out and looked too steep)
    pen.setWidthF(max(side * TICK_SHARE, 0.1))
    painter.setPen(pen)
    tick = QPainterPath(QPointF(box.left() + side * 0.06, box.top() + side * 0.50))
    tick.lineTo(QPointF(box.left() + side * 0.40, box.top() + side * 0.88))
    tick.lineTo(QPointF(box.right() + side * 0.10, box.top() + side * 0.06))
    painter.drawPath(tick)


@register_item
class CheckboxItem(TextItem):
    """Options with boxes to tick, as one markup typed like a text box."""

    TYPE = "checkbox"
    NAME = "Checkbox"

    # what it is drawn with (and their defaults, before __init__ sets them)
    box_shape = "square"
    mark = "tick"
    multiple = True
    box_color = ""             # "" is the words' colour
    mark_color = ""            # "" is the words' colour
    option_gap = OPTION_GAP
    _holding = False           # the ticks are being set, not followed
    # Put down with a click: it widens to what is typed, until its width is
    # set by hand (a handle dragged).
    auto_width = False
    _sized_for = 0.0           # the font size its width was last set for

    def __init__(self, text: str = DEFAULT_OPTIONS, rect: Optional[QRectF] = None):
        self._holding = True
        super().__init__(text, rect)
        # As on the stamp: words and boxes, no frame and no fill.
        self.style.stroke = ""
        self.style.fill = ""
        self.style.fill_opacity = 0.0
        self.style.width = 0.0
        self.style.text_color = "#111318"
        self.subject = self.NAME
        self.box_shape = "square"
        self.mark = "tick"
        self.multiple = True
        self.box_color = ""
        self.mark_color = ""
        self.option_gap = OPTION_GAP
        self.auto_width = False
        self._rows = self.options()
        self.checked = [False] * len(self._rows)
        self._holding = False
        self._sized_for = float(self.style.font_size)
        self.apply_style()

    # -- the options -------------------------------------------------------
    def options(self) -> list:
        """Each option's words, one per paragraph."""
        return [block.text() for block in _blocks(self.doc)]

    def ticks(self) -> list:
        """Which options are ticked, one flag per option."""
        count = self.doc.blockCount()
        return (list(self.checked) + [False] * count)[:count]

    def checked_options(self) -> list:
        """The words of each ticked option."""
        return [words.strip() for words, on in zip(self.options(), self.ticks())
                if on and words.strip()]

    def checked_text(self) -> str:
        """The ticked options as the Markups List's Checked column says them:
        "Satisfactory", or "A; C" for several."""
        return "; ".join(self.checked_options())

    def is_checked(self, index: int) -> bool:
        ticks = self.ticks()
        return 0 <= index < len(ticks) and bool(ticks[index])

    def set_checked(self, index: int, on: bool) -> None:
        """Tick or untick one option. With Multiple selection off, ticking
        one unticks the rest, as a set of radio buttons does."""
        ticks = self.ticks()
        if not 0 <= index < len(ticks):
            return
        if on and not self.multiple:
            ticks = [False] * len(ticks)
        ticks[index] = bool(on)
        self.checked = ticks
        self.touch()
        self.update()
        self.contentChanged.emit()

    def toggle(self, index: int) -> None:
        self.set_checked(index, not self.is_checked(index))

    def set_multiple(self, on: bool) -> None:
        """Allow several ticks, or one: turned off, only the first ticked
        option stays ticked."""
        self.multiple = bool(on)
        if not self.multiple:
            ticks, seen = self.ticks(), False
            for index, value in enumerate(ticks):
                ticks[index] = bool(value) and not seen
                seen = seen or bool(value)
            self.checked = ticks
        self.update()

    # editing the list itself (the Properties panel's Options)
    def _held(self, change) -> None:
        """Change the words without the ticks following them: the caller
        says what they are afterwards."""
        self._holding = True
        try:
            change()
        finally:
            self._holding = False
        self._rows = self.options()
        self.checked = self.ticks()
        self.written = self.doc.toPlainText()
        self.apply_style()
        self.touch()
        self.update()

    def _block_cursor(self, index: int) -> Optional[QTextCursor]:
        block = self.doc.findBlockByNumber(index)
        if not block.isValid():
            return None
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        return cursor

    def rename_option(self, index: int, words: str) -> None:
        """Give option *index* new words, keeping its look and its tick."""
        cursor = self._block_cursor(index)
        if cursor is None:
            return
        words = (words or "").replace("\r", " ").replace("\n", " ")
        ticks = self.ticks()

        def change():
            cursor.insertText(words)
        self._held(change)
        self.checked = ticks

    def add_option(self, words: str = "", at: Optional[int] = None) -> int:
        """Another option, after the last (or before *at*); says where it went."""
        ticks = self.ticks()
        count = len(ticks)
        at = count if at is None else max(0, min(int(at), count))
        words = (words or "").replace("\r", " ").replace("\n", " ")

        def change():
            if at >= count:
                cursor = QTextCursor(self.doc.lastBlock())
                cursor.movePosition(QTextCursor.EndOfBlock)
                cursor.insertBlock()
                cursor.insertText(words)
            else:
                cursor = QTextCursor(self.doc.findBlockByNumber(at))
                cursor.movePosition(QTextCursor.StartOfBlock)
                cursor.insertText(words)
                cursor.insertBlock()
        self._held(change)
        ticks.insert(at, False)
        self.checked = ticks
        return at

    def remove_option(self, index: int) -> None:
        """Take option *index* away, words and tick. The last one left stays,
        emptied: a Checkbox always has at least one option."""
        ticks = self.ticks()
        if not 0 <= index < len(ticks):
            return
        if len(ticks) == 1:
            self.rename_option(0, "")
            self.checked = [False]
            return

        def change():
            block = self.doc.findBlockByNumber(index)
            cursor = QTextCursor(block)
            if index == len(ticks) - 1:
                # the last: its words and the break before them
                cursor.movePosition(QTextCursor.StartOfBlock)
                cursor.movePosition(QTextCursor.PreviousCharacter)
                cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
            else:
                cursor.movePosition(QTextCursor.StartOfBlock)
                cursor.movePosition(QTextCursor.NextBlock, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
        self._held(change)
        del ticks[index]
        self.checked = ticks

    def move_option(self, index: int, step: int) -> int:
        """Move option *index* up (step -1) or down (+1), its words, look and
        tick together. Says where it is now."""
        ticks = self.ticks()
        other = index + step
        if not (0 <= index < len(ticks) and 0 <= other < len(ticks)) or step == 0:
            return index
        first, second = min(index, other), max(index, other)

        def change():
            upper = self._block_cursor(first)
            lower = self._block_cursor(second)
            top = upper.selection()
            bottom = lower.selection()
            # the lower one first, so the upper's position still holds
            for cursor, fragment in ((lower, top), (None, bottom)):
                cursor = cursor or self._block_cursor(first)
                cursor.removeSelectedText()
                if not fragment.isEmpty():
                    cursor.insertFragment(fragment)
        self._held(change)
        ticks[first], ticks[second] = ticks[second], ticks[first]
        self.checked = ticks
        return other

    def select_all_words(self) -> None:
        """While typed into: every option picked, so what is typed next
        takes their place — a new Checkbox's Option 1, 2 and 3."""
        editor = self._editor
        if editor is None:
            return
        cursor = editor.textCursor()
        cursor.select(QTextCursor.Document)
        editor.setTextCursor(cursor)

    # -- keeping the ticks with their words --------------------------------
    def _on_contents_changed(self) -> None:
        if not self._holding:
            self._follow_the_words()
        if not getattr(self, "_formatting", False):
            self._format_rows()
        if self.auto_width and not self._holding:
            self._widen_to_the_words()
        super()._on_contents_changed()

    def _widen_to_the_words(self) -> None:
        """Wide enough for its longest option on one line (never narrower)."""
        wanted, _height = self.natural_size()
        if wanted > self._rect.width() + 0.01:
            self.prepareGeometryChange()
            self._rect.setWidth(wanted)
            self.doc.setTextWidth(max(self.text_rect().width(), 8.0))
            self._sync_editor()

    def move_handle(self, key: str, local_pos: QPointF, keep_ratio: bool = False) -> None:
        if key not in self.leader_handles():
            self.auto_width = False         # its width set by hand from now on
        super().move_handle(key, local_pos, keep_ratio)

    def _follow_the_words(self) -> None:
        rows = self.options()
        old_rows = getattr(self, "_rows", None)
        if old_rows is None:
            return
        if rows == old_rows and len(self.checked) == len(rows):
            return
        ticks = _ticks_after(old_rows, self.checked, rows)
        if not self.multiple and sum(ticks) > 1:
            first = ticks.index(True)
            ticks = [index == first for index in range(len(ticks))]
        self._rows = rows
        self.checked = ticks

    # -- the layout --------------------------------------------------------
    def box_size(self) -> float:
        """How big each box is: from the font size alone."""
        return max(float(self.style.font_size or 10.0) * BOX_SHARE, 1.0)

    def gutter(self) -> float:
        """How far the words are set in: the box and a gap the box's width."""
        return 2.0 * self.box_size()

    def text_rect(self) -> QRectF:
        return super().text_rect().adjusted(self.gutter(), 0, 0, 0)

    def _format_rows(self) -> bool:
        """Every option spaced the same: the line spacing, and the gap after
        each option but the last. True when anything had to change."""
        if getattr(self, "_formatting", False):
            return False
        factor = float(self.line_height_factor())
        gap = max(float(self.option_gap), 0.0) * float(self.style.font_size or 10.0)
        proportional = int(getattr(QTextBlockFormat.ProportionalHeight, "value",
                                   QTextBlockFormat.ProportionalHeight))
        last = self.doc.lastBlock().blockNumber()
        wrong = []
        for block in _blocks(self.doc):
            form = block.blockFormat()
            wanted = 0.0 if block.blockNumber() == last else gap
            if (abs(form.bottomMargin() - wanted) > 1e-6
                    or int(form.lineHeightType()) != proportional
                    or abs(form.lineHeight() - factor * 100.0) > 1e-6):
                wrong.append((block.position(), wanted))
        if not wrong:
            return False
        self._formatting = True
        try:
            cursor = QTextCursor(self.doc)
            cursor.joinPreviousEditBlock()
            for position, wanted in wrong:
                form = QTextBlockFormat()
                form.setBottomMargin(wanted)
                form.setLineHeight(factor * 100.0, proportional)
                cursor.setPosition(position)
                cursor.mergeBlockFormat(form)
            cursor.endEditBlock()
            if not self._editing:
                # Not typing: the spacing is the Checkbox's own doing, not
                # a step for Ctrl+Z to take back once its words are opened
                # (it took that before the markup's own steps).
                self.doc.clearUndoRedoStacks()
        finally:
            self._formatting = False
        return True

    def apply_style(self) -> None:
        if not hasattr(self, "checked"):
            return                      # still being made
        self._format_rows()
        self._follow_the_font()
        super().apply_style()

    def _follow_the_font(self) -> None:
        """A bigger or smaller font makes the whole Checkbox bigger or
        smaller: its width goes with the font, so its words wrap where they
        did (the user, 2026-10-19: "only text size actually makes the whole
        thing bigger"). Narrowed or widened by hand, it only re-wraps."""
        size = float(self.style.font_size or 10.0)
        before = float(self._sized_for or 0.0)
        self._sized_for = size
        if before <= 0 or abs(size - before) < 1e-6 or self.style.font_auto:
            return
        ratio = size / before
        left, top, right, bottom = self.margins()
        rect = self._rect.normalized()
        inner = max(rect.width() - left - right, 1.0)
        self.prepareGeometryChange()
        self._rect = QRectF(rect.left(), rect.top(), inner * ratio + left + right,
                            max(rect.height() - top - bottom, 1.0) * ratio + top + bottom)

    def _laid_out_document(self):
        """The document as it is drawn: its fields filled in, unless being
        typed into."""
        if self._editing:
            return self.doc
        from .fields import shown_document
        return shown_document(self, on_screen=not getattr(self.parentItem(), "print_mode", False))

    def _words_origin(self) -> QPointF:
        """Where the document's own (0, 0) is drawn, in the item."""
        rect = self.text_rect()
        self.doc.setTextWidth(max(rect.width(), 8.0))
        offset = 0.0
        if self.style.valign in ("middle", "bottom"):
            spare = rect.height() - self.doc.size().height()
            offset = max(spare, 0) * (0.5 if self.style.valign == "middle" else 1.0)
        nudge = self._bluebeam_nudge(rect.height(), offset)
        return rect.topLeft() + QPointF(0, offset + nudge)

    def box_rects(self) -> list:
        """Each option's box, in the item's coordinates: at the start of its
        first line, sitting on the line as a capital letter does."""
        side = self.box_size()
        document = self._laid_out_document()
        document.setTextWidth(max(self.text_rect().width(), 8.0))
        document.size()                                  # laid out
        origin = self._words_origin()
        boxes = []
        for block in _blocks(document):
            layout = block.layout()
            if layout is None or layout.lineCount() == 0:
                boxes.append(QRectF())
                continue
            line = layout.lineAt(0)
            place = layout.position()
            baseline = origin.y() + place.y() + line.y() + line.ascent()
            start = origin.x() + place.x() + line.naturalTextRect().left()
            if not block.text():
                # an empty option: its box where its words will start
                start = origin.x() + place.x() + line.x()
            boxes.append(QRectF(start - self.gutter(), baseline - side, side, side))
        return boxes

    def box_at(self, local: QPointF) -> Optional[int]:
        """Which option's box is at *local* (item coordinates), if any."""
        reach = max(self.box_size() * 0.2, 1.5)
        for index, box in enumerate(self.box_rects()):
            if box.isValid() and box.adjusted(-reach, -reach, reach, reach).contains(local):
                return index
        return None

    def natural_size(self) -> tuple:
        """The width and height that hold every option on one line."""
        left, top, right, bottom = self.margins()
        probe = self.doc.clone()
        probe.setTextWidth(-1)
        width = math.ceil(probe.idealWidth()) + 1.0
        probe.setTextWidth(width)
        height = probe.size().height()
        return (left + self.gutter() + width + right, top + height + bottom)

    def size_to_text(self) -> None:
        """Alt+Z: brought in round its options, as a text box is round its
        words. The width only ever comes in (a narrowed Checkbox stays
        wrapped); the height is what the options need."""
        left, top, right, bottom = self.margins()
        self.prepareGeometryChange()
        self.doc.setTextWidth(max(self.text_rect().width(), 8.0))
        ideal = math.ceil(self.doc.idealWidth()) + 1.0
        rect = QRectF(self._rect.normalized())
        least = left + self.gutter() + right + 8.0
        rect.setWidth(max(min(rect.width(), left + self.gutter() + ideal + right), least))
        self._rect = rect
        self.doc.setTextWidth(max(self.text_rect().width(), 8.0))
        self._rect.setHeight(max(self.doc.size().height() + top + bottom, top + bottom + 8.0))
        self.apply_style()
        self.touch()
        self.update()

    def bounds_without_chrome(self) -> QRectF:
        """What it covers: its box, the ticks that run out past their boxes'
        corners, and any leader — not its handles' room."""
        rect = QRectF(self._rect.normalized())
        for point in self.leader_points():
            rect = rect.united(QRectF(point.x() - 1, point.y() - 1, 2, 2))
        for box in self.box_rects():
            if box.isValid():
                side = box.width()
                rect = rect.united(box.adjusted(-side * 0.1, -side * 0.45,
                                                side * 0.45, side * 0.1))
        grow = max(float(self.style.width or 0.0), 0.0) / 2.0 + 0.5
        return rect.adjusted(-grow, -grow, grow, grow)

    def pdf_reading(self) -> str:
        """The Checkbox as plain words, for another reader's search and a
        screen reader: one option a line, ticked or not."""
        return "\n".join(("\u2611 " if on else "\u2610 ") + words
                         for words, on in zip(self.options(), self.ticks()))

    # -- painting ----------------------------------------------------------
    def _colour(self, own: str) -> QColor:
        colour = QColor(own) if own else QColor(self.style.text_qcolor())
        if not colour.isValid():
            colour = QColor(self.style.text_qcolor())
        colour.setAlphaF(max(0.0, min(1.0, self.style.opacity)))
        return colour

    def box_path(self, box: QRectF, inset: float = 0.0) -> QPainterPath:
        """The outline of one box, in its shape."""
        return box_path(self.box_shape, box, inset)

    def paint_content(self, painter: QPainter) -> None:
        super().paint_content(painter)
        self.paint_boxes(painter)

    def paint_boxes(self, painter: QPainter) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        ticks = self.ticks()
        outline = QPen(self._colour(self.box_color))
        outline.setJoinStyle(Qt.MiterJoin)
        ink = self._colour(self.mark_color)
        for index, box in enumerate(self.box_rects()):
            if not box.isValid():
                continue
            side = box.width()
            outline.setWidthF(max(side * OUTLINE_SHARE, 0.1))
            painter.setPen(outline)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(self.box_path(box))
            if index < len(ticks) and ticks[index]:
                self.paint_mark(painter, box, ink)
        painter.restore()

    def paint_mark(self, painter: QPainter, box: QRectF, ink: QColor) -> None:
        """What a ticked box shows."""
        draw_mark(painter, self.mark, self.box_shape, box, ink)

    # -- serialisation -----------------------------------------------------
    def serialize(self) -> dict:
        data = super().serialize()
        data.update({
            "box_shape": self.box_shape,
            "mark": self.mark,
            "multiple": bool(self.multiple),
            "box_color": self.box_color,
            "mark_color": self.mark_color,
            "option_gap": float(self.option_gap),
            "checked": [bool(value) for value in self.ticks()],
        })
        if self.auto_width:
            data["auto_width"] = True
        return data

    def deserialize(self, data: dict) -> None:
        shape = str(data.get("box_shape", "square"))
        self.box_shape = shape if shape in SHAPE_NAMES else "square"
        mark = str(data.get("mark", "tick"))
        self.mark = mark if mark in MARK_NAMES else "tick"
        self.multiple = bool(data.get("multiple", True))
        self.box_color = str(data.get("box_color", "") or "")
        self.mark_color = str(data.get("mark_color", "") or "")
        try:
            self.option_gap = max(float(data.get("option_gap", OPTION_GAP)), 0.0)
        except (TypeError, ValueError):
            self.option_gap = OPTION_GAP
        self.auto_width = bool(data.get("auto_width", False))
        self._holding = True
        self._sized_for = 0.0             # read as it was saved, not scaled
        try:
            super().deserialize(data)
        finally:
            self._holding = False
        self._sized_for = float(self.style.font_size)
        self._rows = self.options()
        stored = data.get("checked")
        if isinstance(stored, (list, tuple)):
            self.checked = [bool(value) for value in stored]
        self.checked = self.ticks()
        if not self.multiple:
            self.set_multiple(False)
        self.update()
