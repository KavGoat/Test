"""The calculation region: typeset, live-evaluated engineering maths."""
from __future__ import annotations

import ast
import re
from functools import lru_cache
from typing import Any, Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QPainter, QPen, QSyntaxHighlighter,
                           QTextCharFormat, QTextCursor)
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsTextItem, QStyle,
                               QStyleOptionGraphicsItem)

from ..core import engine
from ..core.mathrender import (Box, MathStyle, Row, Spacer, Typesetter,
                               caret_in, offset_in)
from .base import MarkupItem, Style, register_item

DEFAULT_SOURCE = ""

# Vertical step used when Enter opens the next calculation line below this one.
LINE_STEP = 6.0


class _MathEditor(QGraphicsTextItem):
    """The plain-text editor shown while a calculation is being typed.

    Enter finishes a single-line region and asks for the next one below it, the
    way pressing Enter in SMath drops you onto a new line of the sheet.  Shift
    with Enter keeps the old behaviour and grows this region into a block.
    """

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner

    def paint(self, painter, option, widget=None) -> None:
        """Draw nothing at all.

        This item exists to hold the text and the cursor and to take the
        keystrokes — Qt's text editing is worth having. What the reader sees
        is the typeset working the region paints itself, with the caret in it.
        Painting this as well would put a second copy of the expression on the
        page in a different shape, which is the thing being got rid of.
        """
        return

    # Nothing in maths needs a space. A unit goes straight after its number —
    # 5kN, not 5 kN — and an operator needs no room around it. So a space in a
    # calculation is a keystroke with no meaning, and it is refused.
    #
    # It used to turn the whole entry into a note instead. That reads well
    # written down and badly in the hand: every calculation is started by
    # typing, so every stray space — the one that follows a comma out of
    # habit, the one that lands while you think — threw the expression away
    # and left a sentence behind. Turning a line into a note is now something
    # you ask for, with Shift and the space bar, and never something that
    # happens to you.
    MATHS_MARKS = set("+-*/^()=:<>,")

    def keyPressEvent(self, event) -> None:
        if event.text() == " ":
            deliberate = bool(event.modifiers() & Qt.ShiftModifier)
            if deliberate and self.owner.started_by_typing:
                # A line still being entered for the first time: nothing has
                # been worked out yet, so there is nothing to lose in saying
                # it was prose after all.
                self.owner.wantsWords.emit()
            elif deliberate:
                self.owner.saySomething.emit(
                    "This is a calculation, not a note — Escape, then the text "
                    "tool, for words")
            else:
                self.owner.saySomething.emit(
                    "A calculation has no spaces in it — a unit goes straight "
                    "after its number, as in 5kN"
                    + (". Shift and the space bar makes this a note instead"
                       if self.owner.started_by_typing else ""))
            event.accept()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                super().keyPressEvent(event)
                return
            if self.owner.wants_next_region:
                self.owner.enterPressed.emit()
                event.accept()
                return
        super().keyPressEvent(event)


def _top_level_hash(text: str) -> int:
    """Where an inline comment starts, or -1 — brackets and quotes respected."""
    depth = 0
    quote = ""
    for index, character in enumerate(text):
        if quote:
            if character == quote:
                quote = ""
            continue
        if character in "\"'":
            quote = character
        elif character in "([{":
            depth += 1
        elif character in ")]}":
            depth = max(depth - 1, 0)
        elif character == "#" and depth == 0:
            return index
    return -1


@lru_cache(maxsize=512)
def _is_a_unit_name(word: str) -> bool:
    """True when pint knows this word as a unit."""
    from ..core.units import parse_unit
    try:
        return parse_unit(word) is not None
    except Exception:                          # noqa: BLE001
        return False


class _MathRow:
    """One laid-out source line."""

    __slots__ = ("statement", "left", "result", "error_box", "top", "height",
                 "baseline", "line", "head_width")

    def __init__(self, statement, left: Optional[Box], result: Optional[Box],
                 error_box: Optional[Box], line: int = 0):
        self.statement = statement
        self.left = left
        # How wide the name and its "≔" are, so a click on the left of the
        # line can be put in the name rather than dragged into the expression.
        self.head_width = 0.0
        self.result = result
        self.error_box = error_box
        self.line = line
        self.top = 0.0
        self.height = 0.0
        self.baseline = 0.0


def _blocks_keep_their_names() -> bool:
    """Whether a new block keeps its names to itself, per the preferences."""
    try:
        from ..ui import preferences
        return preferences.current().self_contained_blocks
    except Exception:            # the engine is usable with no interface at all
        return False


def _parse_for_layout(statement) -> None:
    """Give a freshly typed line the tree its layout needs, without running it.

    A line is only parsed here, never evaluated: working a half-finished line
    out against the document would define names that are still being spelt.
    But the tree is what the typesetter reads, and without it the line falls
    back to the source text — which is why a calculation used to turn into
    ``b*d^2/6`` the moment the caret entered it and back into a fraction the
    moment it left. There is one view now, and this is what keeps it.

    A line that is genuinely half-typed — ``b*d^`` — cannot be parsed, and
    that one line shows what has been typed so far until it can be.
    """
    if statement.tree is not None or not statement.expression:
        return
    try:
        _code, tree = engine.compile_expression(statement.expression)
    except Exception:                     # noqa: BLE001 — any half-typed line
        return
    statement.tree = tree


@register_item
class MathItem(MarkupItem):
    """A calculation region — one line by default, so each can be moved alone."""

    TYPE = "math"
    NAME = "Calculation"
    ROTATABLE = False

    enterPressed = Signal()
    wantsWords = Signal()        # a space, typed before this became maths
    saySomething = Signal(str)   # a line for the status bar

    def __init__(self, source: str = DEFAULT_SOURCE, block: bool = False):
        super().__init__()
        self.source = source
        # Two kinds of calculation, chosen by which tool drew it. A line is one
        # line that defines for the whole document; a block holds as many lines
        # as you like and keeps its working to itself. Which it is decides what
        # Enter does while typing, and whether its names escape.
        self.block = bool(block)
        self.statements: list[engine.Statement] = []
        self.rows: list[_MathRow] = []
        self.digits = 4
        self.number_format = "auto"
        # How one line's answer is shown, when it is not shown the way the
        # rest of the region is: {line number: (digits, mode)}. A capacity
        # wanted to three significant figures and a deflection wanted to two
        # decimal places sit on the same sheet, and neither should force the
        # other.
        self.line_figures: dict[int, tuple] = {}
        self.show_definition_results = False
        # SMath puts the result immediately after the expression rather than in
        # a column down the right-hand side of the page.
        self.align_results = False
        self.show_comments = True
        self.line_gap = 4.0
        self.result_gap = 10.0
        self.title = ""
        # By default every calculation defines for the whole document, which is
        # what a calculation sheet reads like — a block included. Turning this
        # on makes a block self-contained: it still reads what is defined
        # above it, but its own names stay inside it. Whoever works the other
        # way round can say so once, in the preferences.
        self.local_scope = _blocks_keep_their_names() if block else False
        self.local_values: dict[str, Any] = {}
        # Set when this region was begun by typing on bare paper rather than
        # chosen from a tool. Only those can still turn out to be prose.
        self.started_by_typing = False
        self.auto_width = True
        self._width = 260.0
        self._height = 40.0
        self._left_column = 0.0
        self._editor: Optional[QGraphicsTextItem] = None
        self._editing = False
        self._known_names: set[str] = set()
        self.style = Style(stroke="", fill="", width=0.0, font_size=10.0,
                           text_color="#111318", padding=6.0)
        self.layer = "Calculations"

    # -- identity ----------------------------------------------------------
    @property
    def single_line(self) -> bool:
        """True while this region holds at most one line of maths."""
        return len([line for line in self.source.split("\n") if line.strip()]) <= 1

    def split_lines(self) -> list["MathItem"]:
        """One region per source line, stacked where this one sits.

        Each line then moves on its own, and reading order across the page —
        not membership of a block — decides what is defined before what.
        """
        lines = [line for line in self.source.split("\n")]
        while lines and not lines[-1].strip():
            lines.pop()
        if len(lines) <= 1:
            return []
        pieces: list[MathItem] = []
        offset = 0.0
        for index, line in enumerate(lines):
            piece = MathItem(line)
            piece.style = self.style.copy()
            piece.digits = self.digits
            piece.number_format = self.number_format
            piece.show_definition_results = self.show_definition_results
            piece.show_comments = self.show_comments
            piece.author = self.author
            piece.layer = self.layer
            row = self.rows[index] if index < len(self.rows) else None
            piece.setPos(self.pos() + QPointF(0, offset))
            piece.setZValue(self.zValue() + index * 0.001)
            offset += (row.height + self.line_gap) if row else (self.style.font_size * 1.8)
            pieces.append(piece)
        return pieces

    def display_name(self) -> str:
        if self.label:
            return self.label
        first = next((line.strip() for line in self.source.split("\n") if line.strip()), "")
        return f"Calc · {first[:40]}" if first else "Calculation"

    def summary(self) -> str:
        names = [s.name for s in self.statements if s.kind in (engine.DEFINE, engine.FUNCTION)]
        return self.comment or (", ".join(names[:8]) if names else "")

    def defined_names(self) -> list[str]:
        return [s.name for s in self.statements
                if s.kind in (engine.DEFINE, engine.FUNCTION) and s.ok]

    def published_names(self) -> set[str]:
        """Names this region gives to the rest of the document."""
        return set() if self.scoped else self.declared_names()

    def declared_names(self) -> set[str]:
        """Names this region assigns, read from the source without evaluating.

        The document needs these up front so that a name the author defines is
        never resolved as a unit merely because it is used before its own line.
        """
        names = set()
        for line in self.source.split("\n"):
            statement = engine.parse_statement(line)
            if statement.kind in (engine.DEFINE, engine.FUNCTION) and statement.name:
                names.add(statement.name)
        return names

    # -- geometry ----------------------------------------------------------
    def local_rect(self) -> QRectF:
        return QRectF(0, 0, max(self._width, 24.0), max(self._height, 18.0))

    def set_local_rect(self, rect: QRectF) -> None:
        self._width = max(rect.width(), 40.0)
        self.auto_width = False
        self.relayout()

    def math_style(self) -> MathStyle:
        return MathStyle(
            family=self.style.font_family if self.style.font_family else "Cambria Math",
            size=self.style.font_size,
            color=QColor(self.style.text_color),
            result_color=QColor(self.style.text_color),
        )

    # -- evaluation --------------------------------------------------------
    @property
    def scoped(self) -> bool:
        """True when this region's definitions stay inside it."""
        return self.local_scope and self.block

    @property
    def wants_next_region(self) -> bool:
        """Enter opens the next line below, rather than growing this one.

        True for a calculation line, which is one line by definition. In a
        block Enter does what Enter does in any text box: a new line.
        """
        return not self.block

    def refresh(self, workspace=None, page=None) -> None:
        if workspace is None:
            scene = self.scene()
            workspace = getattr(scene, "workspace", None) if scene is not None else None
        if workspace is None:
            return
        label = self.label or "Calculation"
        target = workspace.child() if self.scoped else workspace
        self.statements = engine.evaluate_source(self.source, target, label,
                                                 new_pass=False)
        if self.scoped:
            self.local_values = {
                name: info for name, info in target.variables.items()
                if workspace.variables.get(name) is not info}
        else:
            self.local_values = {}
        self._known_names = set(target.variables) | set(target.functions)
        self.relayout()

    def relayout(self) -> None:
        style = self.math_style()
        setter = Typesetter(style, variables=getattr(self, "_known_names", set()))
        size = style.size
        rows: list[_MathRow] = []

        for line_number, statement in enumerate(self.statements):
            if statement.kind == engine.BLANK:
                blank = _MathRow(statement, Spacer(0, size * 0.5, 0), None, None,
                                 line_number)
                rows.append(blank)
                continue
            if statement.kind == engine.COMMENT:
                if not self.show_comments:
                    continue
                text = setter.text(statement.comment, size * 0.95, italic=True,
                                   color=style.comment_color)
                rows.append(_MathRow(statement, text, None, None, line_number))
                continue

            left_parts: list[Box] = []
            if statement.kind in (engine.DEFINE, engine.FUNCTION):
                if statement.kind == engine.FUNCTION:
                    inner: list[Box] = []
                    for index, param in enumerate(statement.params):
                        if index:
                            inner += [setter.text(",", size), Spacer(size * 0.24)]
                        inner.append(setter.name_box(param, size))
                    head = Row([setter.name_box(statement.name, size),
                                setter.bracket(Row(inner), size)])
                else:
                    head = setter.name_box(statement.name, size)
                left_parts += [head, Spacer(size * 0.34),
                               setter.text("≔", size), Spacer(size * 0.34)]

            expression = self._expression_box(statement, setter, size)
            if expression is not None:
                left_parts.append(expression)
            shows_result = statement.ok and self._wants_result(statement)
            if statement.target_unit and statement.kind != engine.FUNCTION and not shows_result:
                left_parts += [Spacer(size * 0.3), setter.text("→", size, color=style.comment_color),
                               Spacer(size * 0.2),
                               setter.unit_text_box(statement.target_unit, size * 0.95,
                                                    style.comment_color)]
            left = Row(left_parts)
            head_width = sum(part.width for part in left_parts[:4]) \
                if statement.kind in (engine.DEFINE, engine.FUNCTION) else 0.0

            result: Optional[Box] = None
            error_box: Optional[Box] = None
            if statement.error:
                error_box = setter.text("✖ " + statement.error, size * 0.9,
                                        color=style.error_color)
            elif shows_result:
                value = statement.result
                unit = statement.display_unit()
                if unit:
                    from ..core.units import convert
                    try:
                        value = convert(value, unit)
                    except Exception:
                        pass
                digits, mode = self.figures_for(line_number)
                result = Row([setter.text("=", size), Spacer(size * 0.34),
                              setter.value_box(value, size, digits, mode)])
            if statement.comment and statement.kind != engine.COMMENT and self.show_comments:
                note = setter.text("   " + statement.comment, size * 0.9, italic=True,
                                   color=style.comment_color)
                result = Row([result, Spacer(size * 0.4), note]) if result else note
            row = _MathRow(statement, left, result, error_box, line_number)
            row.head_width = head_width
            rows.append(row)

        self.rows = rows
        self._measure()

    # -- how many figures ---------------------------------------------------
    def figures_for(self, line: int) -> tuple:
        """(digits, mode) for one line: its own, or the region's."""
        found = self.line_figures.get(line)
        if not found:
            return self.digits, self.number_format
        digits, mode = found
        return digits, mode

    def set_figures(self, line: int, digits: Optional[int], mode: str = "") -> None:
        """How one line's answer is shown. *digits* None puts it back."""
        if digits is None:
            self.line_figures.pop(line, None)
        else:
            self.line_figures[int(line)] = (int(digits), mode or "auto")
        self.prepareGeometryChange()
        self.relayout()
        self.touch()
        self.update()

    def _expression_box(self, statement, setter: Typesetter, size: float) -> Optional[Box]:
        if statement.tree is None:
            if statement.expression:
                return setter.text(statement.expression, size)
            return None
        written = statement.written
        value = written if written is not None else statement.result
        if statement.ok and value is not None and self._is_unit_literal(statement.tree):
            # "12 kN/m" is an input, not a calculation: show it as a quantity —
            # in the unit it was written in. Asking to see the answer in
            # newtons must not rewrite the kilonewtons on the other side of
            # the equals sign.
            #
            # Only once there is a value to show. While the line is being
            # typed there is none — nothing is evaluated until the caret
            # leaves — and drawing the quantity anyway put an empty box where
            # "300 mm" had just been typed.
            return setter.value_box(value, size, self.digits, self.number_format,
                                    color=setter.color)
        try:
            return setter.build(statement.tree.body if isinstance(statement.tree, ast.Expression)
                                else statement.tree, size)
        except Exception:
            return setter.text(statement.expression, size)

    def _wants_result(self, statement) -> bool:
        """Whether this line's answer is printed.

        A line that ends with "=" asks for its answer, the way SMath does;
        every other line is worked out in the background so that the names it
        defines are there for later lines, and shows nothing. Turning
        "Show every line's result" on in the properties panel puts the old
        behaviour back for a region, for anyone who prefers it.
        """
        if statement.result is None:
            return False
        if statement.kind == engine.FUNCTION:
            return False
        if statement.show_result:
            return True
        if not self.show_definition_results:
            return False
        if statement.kind == engine.EVALUATE:
            return True
        return not self._is_literal(statement.tree)

    @classmethod
    def _is_literal(cls, tree) -> bool:
        """True for plain inputs such as ``300`` or ``12 kN/m`` — no result needed."""
        if tree is None:
            return True
        node = tree.body if isinstance(tree, ast.Expression) else tree
        if isinstance(node, ast.Constant):
            return True
        if isinstance(node, ast.UnaryOp) and isinstance(node.operand, ast.Constant):
            return True
        return cls._is_unit_literal(tree)

    @staticmethod
    def _is_unit_literal(tree) -> bool:
        """An entered value such as ``12 kN/m`` — shown as typed, with no result."""
        return engine.is_unit_literal(tree)

    def _measure(self) -> None:
        self.prepareGeometryChange()
        pad = self.style.padding
        left_widths = [row.left.width for row in self.rows if row.left is not None]
        self._left_column = max(left_widths, default=0.0)
        y = pad
        widest = 0.0
        for row in self.rows:
            ascent = max((box.ascent for box in (row.left, row.result, row.error_box)
                          if box is not None), default=6.0)
            descent = max((box.descent for box in (row.left, row.result, row.error_box)
                           if box is not None), default=2.0)
            row.top = y
            row.baseline = y + ascent
            row.height = ascent + descent
            y += row.height + self.line_gap
            left_width = row.left.width if row.left else 0.0
            extra = row.result.width if row.result else 0.0
            extra = max(extra, row.error_box.width if row.error_box else 0.0)
            if extra:
                if self.align_results:
                    widest = max(widest, self._left_column + self.result_gap + extra)
                else:
                    widest = max(widest, left_width + self.result_gap + extra)
            widest = max(widest, left_width)
        self._height = max(y - self.line_gap + pad, 20.0)
        if self.auto_width:
            self._width = widest + 2 * pad
        else:
            self._width = max(self._width, 40.0)
        self.update()

    # -- editing -----------------------------------------------------------
    @property
    def editing(self) -> bool:
        return self._editing

    def begin_edit(self) -> None:
        if self.locked:
            return
        if self._editor is None:
            self._editor = _MathEditor(self)
            self._editor.setFlag(QGraphicsItem.ItemIsFocusable, True)
            # The same face and the same size as the printed line, so entering
            # an edit does not change what the page looks like.
            self._editor.setDefaultTextColor(QColor(self.style.text_color))
        from ..core.typography import page_font
        self._editor.setFont(page_font(self.style.font_family, self.style.font_size))
        self._editor.setPlainText(self.source)
        self._editor.setTextInteractionFlags(Qt.TextEditorInteraction)
        self._editor.setPos(self.style.padding, self.style.padding)
        self._editor.setTextWidth(-1)
        # What the source said when the edit began, so end_edit can tell
        # whether anything actually changed: the text itself is kept level with
        # the typing as it goes, and by then it is too late to compare.
        self._source_at_edit_start = self.source
        self._editor.show()
        self._editing = True
        self._editor.setFocus(Qt.MouseFocusReason)
        cursor = self._editor.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._editor.setTextCursor(cursor)
        if not getattr(self, "_typeset_wired", False):
            # Keep the typeset working level with the typing. The answers wait
            # for the recalculation a moment later; the working itself must
            # not, or the caret would be standing in yesterday's expression.
            self._editor.document().contentsChanged.connect(self.retypeset_live)
            self._typeset_wired = True
        self.update()

    def looks_like_words(self, this_space_included: bool = False) -> bool:
        """Whether what is in the region reads as prose rather than as maths.

        A space can no longer be typed into a calculation at all — the editor
        refuses it, and in a region opened by typing it turns the whole entry
        into words there and then — so this is not what decides that any more.
        What is left for it is text that never went through a keystroke:
        pasted in, or built from something else. For that, two things say it
        is not prose. An operator, an equals sign or a bracket: that is a
        calculation, and a space in it came from whatever wrote it. And a
        *single* word: ``L`` waiting for its ``:=`` is the commonest thing on a
        calculation sheet.

        *this_space_included* counts the space now being typed as one of them.
        """
        if not self.started_by_typing:
            return False
        text = self._editor.toPlainText() if self._editor is not None else self.source
        if any(mark in text for mark in _MathEditor.MATHS_MARKS):
            return False
        words = text.split()
        if this_space_included:
            return len(words) >= 2 and text[-1:] != " "
        return len(words) >= 2

    def reads_as_a_sentence(self) -> bool:
        """A finished line with a space in it and nothing mathematical about it.

        The other half of the same job, for a line the caret has left. A line
        that never grew an operator, a number or a second line, and does have
        a space in it, was a sentence — however it got there.
        """
        if not self.started_by_typing:
            return False
        text = (self._editor.toPlainText() if self._editor is not None
                else self.source)
        if not text.strip() or "\n" in text:
            return False
        if any(mark in text for mark in _MathEditor.MATHS_MARKS):
            return False
        if any(character.isdigit() for character in text):
            return False
        return " " in text.strip() or text != text.strip()

    def retypeset_live(self) -> None:
        """Lay the working out again from what has been typed so far.

        Only parsed, never evaluated: working a half-finished line out against
        the document would define names that are still being spelt. The
        answers already on the page are kept for the lines that have not
        changed, so they stay put rather than blinking out at every keystroke.
        """
        if self._editor is None:
            return
        source = self._editor.toPlainText()
        if source == self.source and self.rows:
            self.update()
            return
        self.source = source
        previous = {(index, statement.raw): statement
                    for index, statement in enumerate(self.statements)}
        fresh = []
        for index, line in enumerate(source.split("\n")):
            parsed = engine.parse_statement(line)
            kept = previous.get((index, parsed.raw))
            if kept is None:
                _parse_for_layout(parsed)
            fresh.append(kept if kept is not None else parsed)
        self.statements = fresh
        self.prepareGeometryChange()
        self.relayout()
        self.update()

    def end_edit(self) -> bool:
        """Commit the editor contents; returns True when the source changed."""
        changed = False
        if self._editor is not None:
            text = self._editor.toPlainText()
            changed = text != getattr(self, "_source_at_edit_start", self.source)
            self.source = text
            self._editor.setTextInteractionFlags(Qt.NoTextInteraction)
            self._editor.hide()
            self._editor.clearFocus()
        self._editing = False
        self.touch()
        self.update()
        return changed

    def editor_rect(self) -> QRectF:
        if self._editor is None:
            return QRectF()
        return QRectF(self._editor.pos(), self._editor.boundingRect().size())

    # -- the result's own unit ---------------------------------------------
    def result_rect(self, index: int) -> QRectF:
        """Where the printed answer for row *index* sits, in item coordinates."""
        if not (0 <= index < len(self.rows)):
            return QRectF()
        row = self.rows[index]
        box = row.result or row.error_box
        if box is None:
            return QRectF()
        pad = self.style.padding
        x = pad + (self._left_column if self.align_results
                   else (row.left.width if row.left else 0.0)) + self.result_gap
        return QRectF(x, row.top, box.width, row.height)

    def result_at(self, point: QPointF) -> int:
        """The row whose printed answer is under *point*, or -1."""
        for index, row in enumerate(self.rows):
            if row.result is None:
                continue
            if self.result_rect(index).adjusted(-2, -1, 6, 1).contains(point):
                return index
        return -1

    def display_unit_of(self, index: int) -> str:
        """The unit that row is being shown in, whether asked for or chosen."""
        if not (0 <= index < len(self.rows)):
            return ""
        statement = self.rows[index].statement
        if statement.target_unit:
            return statement.target_unit
        from ..core.units import format_unit
        value = statement.result
        units = getattr(value, "units", None)
        return format_unit(units) if units is not None else ""

    def set_display_unit(self, index: int, unit: str) -> bool:
        """Show row *index* in *unit*; False when the line could not be found."""
        if not (0 <= index < len(self.rows)):
            return False
        statement = self.rows[index].statement
        try:
            line = self.statements.index(statement)
        except ValueError:
            return False
        lines = self.source.split("\n")
        if line >= len(lines):
            return False
        lines[line] = engine.set_display_unit(lines[line], unit)
        self.source = "\n".join(lines)
        self.touch()
        return True

    def line_at(self, local_y: float) -> int:
        for index, row in enumerate(self.rows):
            if row.top <= local_y <= row.top + row.height + self.line_gap:
                return index
        return max(len(self.rows) - 1, 0)

    # -- painting ----------------------------------------------------------
    def paint_content(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        rect = self.local_rect()
        if self.style.fill:
            painter.setBrush(self.style.brush())
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(rect, self.style.corner_radius, self.style.corner_radius)
        if self.style.stroke and self.style.width > 0:
            painter.setPen(self.style.pen())
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, self.style.corner_radius, self.style.corner_radius)
        if self._editing:
            # There is one view of a calculation, and this is it. While it is
            # being typed it stays typeset — fractions are still fractions,
            # powers are still powers — with a caret standing in the working
            # rather than a second, flatter copy of it underneath. That is how
            # SMath does it, and it is the only way the thing you are editing
            # is the thing you will print.
            painter.setPen(QPen(QColor(11, 107, 203, 90), 0.8))
            painter.setBrush(QColor(252, 253, 255, 210))
            painter.drawRoundedRect(rect, 2.0, 2.0)

        if self.scoped and self.rows:
            rule = QPen(QColor(120, 140, 170, 130))
            rule.setWidthF(1.2)
            painter.setPen(rule)
            painter.drawLine(QPointF(1.5, rect.top() + 2), QPointF(1.5, rect.bottom() - 2))

        pad = self.style.padding
        for row in self.rows:
            if row.left is not None:
                row.left.draw(painter, pad, row.baseline)
            x = pad + (self._left_column if self.align_results
                       else (row.left.width if row.left else 0.0)) + self.result_gap
            if row.result is not None:
                row.result.draw(painter, x, row.baseline)
            elif row.error_box is not None:
                row.error_box.draw(painter, x, row.baseline)
        if self._editing:
            self._paint_caret(painter)

    # -- the caret, inside the typeset working ------------------------------
    def caret_line_and_column(self) -> tuple:
        """Where the caret is, as (line, column), or (-1, 0) when not typing."""
        if self._editor is None or not self._editing:
            return (-1, 0)
        cursor = self._editor.textCursor()
        return (cursor.blockNumber(), cursor.positionInBlock())

    def row_for_line(self, line: int):
        for row in self.rows:
            if row.line == line:
                return row
        return None

    @staticmethod
    @lru_cache(maxsize=512)
    def _alignment(written: str, parsed: str) -> tuple:
        """Line the written expression up with the Python it is parsed as.

        "12 kN" is parsed as "( 12 * kN )", so a character of one is not the
        same character of the other, and the offsets in the box tree count the
        second. Lining them up character by character is what lets a click on
        the page find the right place in what was actually typed.
        """
        from difflib import SequenceMatcher

        forward: dict[int, int] = {}
        backward: dict[int, int] = {}
        matcher = SequenceMatcher(None, written, parsed, autojunk=False)
        for start_a, start_b, size in matcher.get_matching_blocks():
            for step in range(size):
                forward[start_a + step] = start_b + step
                backward[start_b + step] = start_a + step
        forward[len(written)] = len(parsed)
        backward[len(parsed)] = len(written)
        return forward, backward

    def alignment(self, statement) -> tuple:
        return self._alignment(statement.expression or "",
                               engine.python_form(statement.expression or ""))

    @staticmethod
    def _nearest(table: dict, offset: int) -> int:
        if offset in table:
            return table[offset]
        below = [key for key in table if key <= offset]
        return table[max(below)] if below else 0

    @staticmethod
    def expression_column(statement) -> int:
        """Where a statement's expression starts within the line as written.

        The parser hands back the expression on its own, having taken off the
        name, the arrow and the trailing "=". To put a caret in the right
        place, the offsets in the box tree — which count from the start of the
        expression — have to be moved along by however much came before it.
        """
        raw, expression = statement.raw or "", statement.expression or ""
        if not expression:
            return 0
        found = raw.rfind(expression)
        if found >= 0:
            return found
        return max(len(raw) - len(expression), 0)

    def caret_place(self):
        """The caret's place on the page: (x, baseline, ascent, descent)."""
        line, column = self.caret_line_and_column()
        if line < 0:
            return None
        row = self.row_for_line(line)
        if row is None or row.left is None:
            return None
        written = column - self.expression_column(row.statement)
        forward, _backward = self.alignment(row.statement)
        offset = self._nearest(forward, max(written, 0))
        found = caret_in(row.left, self.style.padding, row.baseline, offset)
        if found is not None:
            return found
        # Off the end of what could be typeset — the caret sits just past the
        # last thing drawn, which is where the next character will go.
        return (self.style.padding + row.left.width, row.baseline,
                row.left.ascent, row.left.descent)

    def offset_at(self, point) -> tuple:
        """The (line, column) nearest a point, for clicking into the working."""
        best = (-1, 0, float("inf"))
        for row in self.rows:
            if row.left is None:
                continue
            distance = abs(point.y() - row.baseline)
            # Left of the "≔" is the name being defined, and clicking it must
            # put the caret in the name — not shove it to the first character
            # of the expression, which is what happens when only the boxes the
            # expression built are looked at.
            head_end = self.style.padding + row.head_width
            if row.head_width and point.x() < head_end and distance < best[2]:
                name = row.statement.name or ""
                across = (point.x() - self.style.padding) / max(row.head_width, 1.0)
                column = min(max(round(across * len(name)), 0), len(name))
                best = (row.line, column, distance)
                continue
            offset = offset_in(row.left, self.style.padding, row.baseline, point)
            if offset is None:
                continue
            if distance < best[2]:
                _forward, backward = self.alignment(row.statement)
                written = self._nearest(backward, offset)
                best = (row.line, written + self.expression_column(row.statement),
                        distance)
        if best[0] < 0:
            return (-1, 0)
        return (best[0], best[1])

    def _paint_caret(self, painter: QPainter) -> None:
        place = self.caret_place()
        if place is None:
            return
        x, baseline, ascent, descent = place
        ascent = max(ascent, self.style.font_size * 0.75)
        descent = max(descent, self.style.font_size * 0.2)
        pen = QPen(QColor(11, 107, 203))
        pen.setWidthF(1.1)
        painter.setPen(pen)
        painter.drawLine(QPointF(x, baseline - ascent), QPointF(x, baseline + descent))

    def paint_handles(self, painter: QPainter) -> None:
        if self._editing:
            return
        super().paint_handles(painter)

    # -- serialisation -----------------------------------------------------
    def serialize(self) -> dict:
        data = self.base_dict()
        data.update({
            "source": self.source,
            "digits": self.digits,
            "number_format": self.number_format,
            "show_definition_results": self.show_definition_results,
            "align_results": self.align_results,
            "show_comments": self.show_comments,
            "block": self.block,
            "local_scope": self.local_scope,
            "auto_width": self.auto_width,
            "width": self._width,
            "line_gap": self.line_gap,
            "result_gap": self.result_gap,
            "line_figures": {str(line): list(figures)
                             for line, figures in self.line_figures.items()},
        })
        return data

    def deserialize(self, data: dict) -> None:
        self.source = data.get("source", "")
        self.digits = int(data.get("digits", 4))
        self.number_format = data.get("number_format", "auto")
        self.line_figures = {}
        for line, figures in (data.get("line_figures") or {}).items():
            try:
                self.line_figures[int(line)] = (int(figures[0]), str(figures[1]))
            except (TypeError, ValueError, IndexError):
                continue
        # Documents written before results waited for a trailing "=" showed
        # every line, so they keep doing that when reopened.
        self.show_definition_results = bool(data.get("show_definition_results", True))
        self.show_comments = bool(data.get("show_comments", True))
        # Before there were two kinds, a region with several lines was a block.
        self.block = bool(data.get("block", not self.single_line))
        self.local_scope = bool(data.get("local_scope", False))
        self.auto_width = bool(data.get("auto_width", True))
        self.align_results = bool(data.get("align_results", False))
        self._width = float(data.get("width", 260.0))
        self.line_gap = float(data.get("line_gap", 4.0))
        self.result_gap = float(data.get("result_gap", 10.0))
        self.load_base(data)
