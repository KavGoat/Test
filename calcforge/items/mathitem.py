"""The calculation region: typeset, live-evaluated engineering maths."""
from __future__ import annotations

import ast
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QColor, QPainter, QPen)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsTextItem

from ..core import engine
from ..core.mathrender import Box, MathStyle, Row, Spacer, Typesetter
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

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                super().keyPressEvent(event)
                return
            if self.owner.single_line:
                self.owner.enterPressed.emit()
                event.accept()
                return
        super().keyPressEvent(event)


class _MathRow:
    """One laid-out source line."""

    __slots__ = ("statement", "left", "result", "error_box", "top", "height", "baseline")

    def __init__(self, statement, left: Optional[Box], result: Optional[Box],
                 error_box: Optional[Box]):
        self.statement = statement
        self.left = left
        self.result = result
        self.error_box = error_box
        self.top = 0.0
        self.height = 0.0
        self.baseline = 0.0


@register_item
class MathItem(MarkupItem):
    """A calculation region — one line by default, so each can be moved alone."""

    TYPE = "math"
    NAME = "Calculation"
    ROTATABLE = False

    enterPressed = Signal()

    def __init__(self, source: str = DEFAULT_SOURCE):
        super().__init__()
        self.source = source
        self.statements: list[engine.Statement] = []
        self.rows: list[_MathRow] = []
        self.digits = 4
        self.number_format = "auto"
        self.show_definition_results = True
        # SMath puts the result immediately after the expression rather than in
        # a column down the right-hand side of the page.
        self.align_results = False
        self.show_comments = True
        self.line_gap = 4.0
        self.result_gap = 10.0
        self.title = ""
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
    def refresh(self, workspace=None, page=None) -> None:
        if workspace is None:
            scene = self.scene()
            workspace = getattr(scene, "workspace", None) if scene is not None else None
        if workspace is None:
            return
        label = self.label or "Calculation"
        self.statements = engine.evaluate_source(self.source, workspace, label,
                                                 new_pass=False)
        self._known_names = set(workspace.variables) | set(workspace.functions)
        self.relayout()

    def relayout(self) -> None:
        style = self.math_style()
        setter = Typesetter(style, variables=getattr(self, "_known_names", set()))
        size = style.size
        rows: list[_MathRow] = []

        for statement in self.statements:
            if statement.kind == engine.BLANK:
                blank = _MathRow(statement, Spacer(0, size * 0.5, 0), None, None)
                rows.append(blank)
                continue
            if statement.kind == engine.COMMENT:
                if not self.show_comments:
                    continue
                text = setter.text(statement.comment, size * 0.95, italic=True,
                                   color=style.comment_color)
                rows.append(_MathRow(statement, text, None, None))
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
                result = Row([setter.text("=", size), Spacer(size * 0.34),
                              setter.value_box(value, size, self.digits, self.number_format)])
            if statement.comment and statement.kind != engine.COMMENT and self.show_comments:
                note = setter.text("   " + statement.comment, size * 0.9, italic=True,
                                   color=style.comment_color)
                result = Row([result, Spacer(size * 0.4), note]) if result else note
            rows.append(_MathRow(statement, left, result, error_box))

        self.rows = rows
        self._measure()

    def _expression_box(self, statement, setter: Typesetter, size: float) -> Optional[Box]:
        if statement.tree is None:
            if statement.expression:
                return setter.text(statement.expression, size)
            return None
        if statement.ok and self._is_unit_literal(statement.tree):
            # "12 kN/m" is an input, not a calculation: show it as a quantity.
            return setter.value_box(statement.result, size, self.digits, self.number_format,
                                    color=setter.color)
        try:
            return setter.build(statement.tree.body if isinstance(statement.tree, ast.Expression)
                                else statement.tree, size)
        except Exception:
            return setter.text(statement.expression, size)

    def _wants_result(self, statement) -> bool:
        if statement.result is None:
            return False
        if statement.kind == engine.FUNCTION:
            return False
        if statement.kind == engine.EVALUATE:
            return True
        if not self.show_definition_results:
            return False
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
            from ..core.typography import MONO, page_font
            self._editor.setFont(page_font("", max(self.style.font_size * 1.05, 8.0),
                                           fallbacks=MONO))
            self._editor.setDefaultTextColor(QColor("#0b3d91"))
        self._editor.setPlainText(self.source)
        self._editor.setTextInteractionFlags(Qt.TextEditorInteraction)
        self._editor.setPos(self.style.padding, self.style.padding)
        self._editor.setTextWidth(max(self._width - 2 * self.style.padding, 120.0))
        self._editor.show()
        self._editing = True
        self._editor.setFocus(Qt.MouseFocusReason)
        self.update()

    def end_edit(self) -> bool:
        """Commit the editor contents; returns True when the source changed."""
        changed = False
        if self._editor is not None:
            text = self._editor.toPlainText()
            changed = text != self.source
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
            painter.setPen(QPen(QColor(30, 110, 220, 160), 0.8, Qt.DashLine))
            painter.setBrush(QColor(240, 246, 255, 200))
            painter.drawRect(rect)
            return

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
            "auto_width": self.auto_width,
            "width": self._width,
            "line_gap": self.line_gap,
            "result_gap": self.result_gap,
        })
        return data

    def deserialize(self, data: dict) -> None:
        self.source = data.get("source", "")
        self.digits = int(data.get("digits", 4))
        self.number_format = data.get("number_format", "auto")
        self.show_definition_results = bool(data.get("show_definition_results", True))
        self.show_comments = bool(data.get("show_comments", True))
        self.auto_width = bool(data.get("auto_width", True))
        self.align_results = bool(data.get("align_results", False))
        self._width = float(data.get("width", 260.0))
        self.line_gap = float(data.get("line_gap", 4.0))
        self.result_gap = float(data.get("result_gap", 10.0))
        self.load_base(data)
