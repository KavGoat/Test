"""WYSIWYG math editor for SMath Studio GUI.

Provides a canvas-based inline math editor that renders typed expressions
as proper mathematical notation in real-time, matching SMath Studio's
editing experience: fraction layout on /, superscripts on ^, Tab navigation
between slots, blinking cursor, and live evaluation preview.
"""

from __future__ import annotations

import math as _math
import tkinter as tk
from tkinter import font as tkfont
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..expression import (
    ASTNode, Number, Variable, UnitRef, StringLiteral,
    BinaryOp, UnaryOp, FunctionCall, Evaluation,
)


# ---- Edit tree nodes ----

class EditItem:
    pass


@dataclass
class EText(EditItem):
    text: str = ""


@dataclass
class EOp(EditItem):
    op: str = ""


@dataclass
class EFraction(EditItem):
    numerator: EditSlot = field(default_factory=lambda: EditSlot())
    denominator: EditSlot = field(default_factory=lambda: EditSlot())


@dataclass
class ESuperscript(EditItem):
    exponent: EditSlot = field(default_factory=lambda: EditSlot())


@dataclass
class EParens(EditItem):
    inner: EditSlot = field(default_factory=lambda: EditSlot())


@dataclass
class EUnit(EditItem):
    name: str = ""


@dataclass
class EditSlot:
    items: list[EditItem] = field(default_factory=list)
    cursor_pos: int = 0


@dataclass
class _Box:
    width: float = 0
    height: float = 0
    baseline: float = 0


# ---- Style constants matching SMath Studio ----

_NUMBER_COLOR = "#000000"
_UNIT_COLOR = "#0000ff"
_OPERATOR_COLOR = "#000000"
_STRING_COLOR = "#a31515"
_CURSOR_COLOR = "#000000"
_PLACEHOLDER_COLOR = "#999999"
_RESULT_COLOR = "#000000"
_ERROR_COLOR = "#ff0000"

_OP_DISPLAY = {
    ":": " := ",
    "+": " + ",
    "-": " − ",
    "*": " · ",
    "=": " = ",
    ",": ", ",
    "<": " < ",
    ">": " > ",
    "≤": " ≤ ",
    "≥": " ≥ ",
    "≠": " ≠ ",
    "!": "!",
}

_BUILTIN_VARS = {
    "π", "pi", "e", "i", "∞", "inf",
    "g.e", "c", "m.e", "m.p", "m.n", "u",
    "G.N", "h", "N.A", "k", "R.m",
    "ε.0", "μ.0",
}

_SUP_SCALE = 0.70
_FRAC_HPAD = 4
_FRAC_VPAD = 3


class MathEditor:
    """Canvas-based WYSIWYG math expression editor."""

    def __init__(
        self,
        canvas: tk.Canvas,
        x: int,
        y: int,
        font_size: int = 12,
        eval_callback: Optional[Callable[[str], Any]] = None,
    ):
        self.canvas = canvas
        self.x = x
        self.y = y
        self.font_size = font_size
        self._eval_callback = eval_callback

        self.root = EditSlot()
        self._active_slot: EditSlot = self.root
        self._slot_stack: list[EditSlot] = []

        self._eval_result: Any = None
        self._eval_error: Optional[str] = None

        self._items: list[int] = []
        self._cursor_item: Optional[int] = None
        self._cursor_visible = True
        self._blink_id: Optional[str] = None

        self._cursor_rx: Optional[float] = None
        self._cursor_ry: Optional[float] = None
        self._cursor_rh: Optional[float] = None

        self._font_family = "serif"
        self._font_cache: dict[tuple, tkfont.Font] = {}
        self._detect_font()

        self.render()
        self._start_blink()

    # ================================================================
    # Font helpers
    # ================================================================

    def _detect_font(self):
        for family in ("Cambria Math", "STIX Two Math", "DejaVu Serif",
                       "Liberation Serif", "serif"):
            try:
                f = tkfont.Font(root=self.canvas, family=family, size=12)
                if f.actual("family"):
                    self._font_family = family
                    return
            except Exception:
                continue

    def _get_font(self, size: int, style: str = "") -> tkfont.Font:
        key = (self._font_family, size, style)
        if key not in self._font_cache:
            weight = "bold" if "bold" in style else "normal"
            slant = "italic" if "italic" in style else "roman"
            self._font_cache[key] = tkfont.Font(
                root=self.canvas, family=self._font_family,
                size=max(size, 6), weight=weight, slant=slant,
            )
        return self._font_cache[key]

    def _text_size(self, text: str, size: int, style: str = "") -> tuple[float, float]:
        f = self._get_font(size, style)
        return f.measure(text), f.metrics("linespace")

    def _line_height(self, fs: int) -> float:
        _, h = self._text_size("Xg", fs)
        return h

    # ================================================================
    # Key handling
    # ================================================================

    def handle_key(self, event: tk.Event) -> str:
        """Handle a key event. Returns 'commit', 'cancel', or 'consumed'."""
        keysym = event.keysym
        char = event.char

        if keysym in ("Return", "KP_Enter"):
            return "commit"
        if keysym == "Escape":
            return "cancel"

        if keysym == "BackSpace":
            self._do_backspace()
        elif keysym == "Delete":
            self._do_delete()
        elif keysym == "Left":
            self._move_left()
        elif keysym == "Right":
            self._move_right()
        elif keysym == "Up":
            self._move_up()
        elif keysym == "Down":
            self._move_down()
        elif keysym == "Tab":
            if event.state & 0x1:
                self._tab_prev()
            else:
                self._tab_next()
        elif keysym == "Home":
            self._active_slot.cursor_pos = 0
        elif keysym == "End":
            self._active_slot.cursor_pos = len(self._active_slot.items)
        elif char and ord(char) >= 32:
            self._insert_char(char)
        else:
            return "consumed"

        self._update_eval()
        self.render()
        return "consumed"

    # ---- Character insertion ----

    def _insert_char(self, ch: str):
        slot = self._active_slot
        pos = slot.cursor_pos

        if ch == "/":
            self._do_fraction()
            return
        if ch == "^":
            self._do_superscript()
            return
        if ch == "(":
            self._do_open_paren()
            return
        if ch == ")":
            self._do_close_paren()
            return

        if ch == ":":
            slot.items.insert(pos, EOp(":"))
            slot.cursor_pos = pos + 1
            return

        if ch == "=":
            if pos > 0 and isinstance(slot.items[pos - 1], EOp):
                prev = slot.items[pos - 1]
                if prev.op == "<":
                    prev.op = "≤"
                    return
                if prev.op == ">":
                    prev.op = "≥"
                    return
                if prev.op == "!":
                    prev.op = "≠"
                    return
                if prev.op == ":":
                    return
            slot.items.insert(pos, EOp("="))
            slot.cursor_pos = pos + 1
            return

        if ch in ("+", "-", "*", "<", ">", "!"):
            slot.items.insert(pos, EOp(ch))
            slot.cursor_pos = pos + 1
            return

        if ch == ",":
            slot.items.insert(pos, EOp(","))
            slot.cursor_pos = pos + 1
            return

        if ch == "'":
            if pos > 0 and isinstance(slot.items[pos - 1], EUnit):
                return
            unit = EUnit("")
            slot.items.insert(pos, unit)
            slot.cursor_pos = pos + 1
            return

        if pos > 0 and isinstance(slot.items[pos - 1], EText):
            slot.items[pos - 1].text += ch
        elif pos > 0 and isinstance(slot.items[pos - 1], EUnit):
            slot.items[pos - 1].name += ch
        else:
            slot.items.insert(pos, EText(ch))
            slot.cursor_pos = pos + 1

    def _do_fraction(self):
        slot = self._active_slot
        pos = slot.cursor_pos
        frac = EFraction()

        if pos > 0 and isinstance(slot.items[pos - 1], (EText, EParens, ESuperscript)):
            prev = slot.items.pop(pos - 1)
            pos -= 1
            frac.numerator.items.append(prev)
            frac.numerator.cursor_pos = len(frac.numerator.items)

        slot.items.insert(pos, frac)
        slot.cursor_pos = pos + 1
        self._slot_stack.append(slot)
        self._active_slot = frac.denominator
        self._active_slot.cursor_pos = 0

    def _do_superscript(self):
        slot = self._active_slot
        pos = slot.cursor_pos
        sup = ESuperscript()
        slot.items.insert(pos, sup)
        slot.cursor_pos = pos + 1
        self._slot_stack.append(slot)
        self._active_slot = sup.exponent
        self._active_slot.cursor_pos = 0

    def _do_open_paren(self):
        slot = self._active_slot
        pos = slot.cursor_pos
        parens = EParens()
        slot.items.insert(pos, parens)
        slot.cursor_pos = pos + 1
        self._slot_stack.append(slot)
        self._active_slot = parens.inner
        self._active_slot.cursor_pos = 0

    def _do_close_paren(self):
        if self._slot_stack:
            parent = self._slot_stack[-1]
            for i, item in enumerate(parent.items):
                if isinstance(item, EParens) and item.inner is self._active_slot:
                    self._active_slot = self._slot_stack.pop()
                    self._active_slot.cursor_pos = i + 1
                    return
            self._active_slot = self._slot_stack.pop()

    # ---- Deletion ----

    def _do_backspace(self):
        slot = self._active_slot
        pos = slot.cursor_pos

        if pos > 0:
            item = slot.items[pos - 1]
            if isinstance(item, EText) and len(item.text) > 1:
                item.text = item.text[:-1]
            elif isinstance(item, EUnit) and len(item.name) > 1:
                item.name = item.name[:-1]
            elif isinstance(item, (EFraction, ESuperscript, EParens)):
                contents = self._flatten_structure(item)
                slot.items.pop(pos - 1)
                for j, c in enumerate(contents):
                    slot.items.insert(pos - 1 + j, c)
                slot.cursor_pos = pos - 1 + len(contents)
            else:
                slot.items.pop(pos - 1)
                slot.cursor_pos = pos - 1
        elif self._slot_stack:
            self._active_slot = self._slot_stack.pop()

    def _do_delete(self):
        slot = self._active_slot
        pos = slot.cursor_pos
        if pos < len(slot.items):
            item = slot.items[pos]
            if isinstance(item, EText) and len(item.text) > 1:
                item.text = item.text[1:]
            elif isinstance(item, EUnit) and len(item.name) > 1:
                item.name = item.name[1:]
            else:
                slot.items.pop(pos)

    def _flatten_structure(self, item: EditItem) -> list[EditItem]:
        if isinstance(item, EFraction):
            result = list(item.numerator.items)
            if item.denominator.items:
                result.append(EOp("/"))
                result.extend(item.denominator.items)
            return result if result else []
        if isinstance(item, ESuperscript):
            return list(item.exponent.items)
        if isinstance(item, EParens):
            return list(item.inner.items)
        return [item]

    # ---- Navigation ----

    def _get_child_slots(self, item: EditItem) -> list[EditSlot]:
        if isinstance(item, EFraction):
            return [item.numerator, item.denominator]
        if isinstance(item, ESuperscript):
            return [item.exponent]
        if isinstance(item, EParens):
            return [item.inner]
        return []

    def _move_left(self):
        slot = self._active_slot
        if slot.cursor_pos > 0:
            slot.cursor_pos -= 1
            item = slot.items[slot.cursor_pos]
            if isinstance(item, EFraction):
                self._slot_stack.append(slot)
                self._active_slot = item.denominator
                self._active_slot.cursor_pos = len(self._active_slot.items)
            elif isinstance(item, ESuperscript):
                self._slot_stack.append(slot)
                self._active_slot = item.exponent
                self._active_slot.cursor_pos = len(self._active_slot.items)
            elif isinstance(item, EParens):
                self._slot_stack.append(slot)
                self._active_slot = item.inner
                self._active_slot.cursor_pos = len(self._active_slot.items)
        elif self._slot_stack:
            parent = self._slot_stack[-1]
            for i, item in enumerate(parent.items):
                children = self._get_child_slots(item)
                if slot in children:
                    idx = children.index(slot)
                    if idx > 0:
                        self._active_slot = children[idx - 1]
                        self._active_slot.cursor_pos = len(self._active_slot.items)
                        return
                    self._active_slot = self._slot_stack.pop()
                    self._active_slot.cursor_pos = i
                    return
            self._active_slot = self._slot_stack.pop()

    def _move_right(self):
        slot = self._active_slot
        if slot.cursor_pos < len(slot.items):
            item = slot.items[slot.cursor_pos]
            if isinstance(item, EFraction):
                self._slot_stack.append(slot)
                self._active_slot = item.numerator
                self._active_slot.cursor_pos = 0
            elif isinstance(item, ESuperscript):
                self._slot_stack.append(slot)
                self._active_slot = item.exponent
                self._active_slot.cursor_pos = 0
            elif isinstance(item, EParens):
                self._slot_stack.append(slot)
                self._active_slot = item.inner
                self._active_slot.cursor_pos = 0
            else:
                slot.cursor_pos += 1
        elif self._slot_stack:
            parent = self._slot_stack[-1]
            for i, item in enumerate(parent.items):
                children = self._get_child_slots(item)
                if slot in children:
                    idx = children.index(slot)
                    if idx + 1 < len(children):
                        self._active_slot = children[idx + 1]
                        self._active_slot.cursor_pos = 0
                        return
                    self._active_slot = self._slot_stack.pop()
                    self._active_slot.cursor_pos = i + 1
                    return
            self._active_slot = self._slot_stack.pop()
            self._active_slot.cursor_pos = min(
                self._active_slot.cursor_pos + 1,
                len(self._active_slot.items),
            )

    def _move_up(self):
        if self._slot_stack:
            parent = self._slot_stack[-1]
            for item in parent.items:
                if isinstance(item, EFraction):
                    if self._active_slot is item.denominator:
                        self._active_slot = item.numerator
                        self._active_slot.cursor_pos = min(
                            self._active_slot.cursor_pos,
                            len(self._active_slot.items),
                        )
                        return

    def _move_down(self):
        if self._slot_stack:
            parent = self._slot_stack[-1]
            for item in parent.items:
                if isinstance(item, EFraction):
                    if self._active_slot is item.numerator:
                        self._active_slot = item.denominator
                        self._active_slot.cursor_pos = min(
                            self._active_slot.cursor_pos,
                            len(self._active_slot.items),
                        )
                        return

    def _tab_next(self):
        if not self._slot_stack:
            return
        parent = self._slot_stack[-1]
        for i, item in enumerate(parent.items):
            children = self._get_child_slots(item)
            if self._active_slot in children:
                idx = children.index(self._active_slot)
                if idx + 1 < len(children):
                    self._active_slot = children[idx + 1]
                    self._active_slot.cursor_pos = len(self._active_slot.items)
                    return
                self._active_slot = self._slot_stack.pop()
                self._active_slot.cursor_pos = i + 1
                return
        self._active_slot = self._slot_stack.pop()

    def _tab_prev(self):
        if not self._slot_stack:
            return
        parent = self._slot_stack[-1]
        for i, item in enumerate(parent.items):
            children = self._get_child_slots(item)
            if self._active_slot in children:
                idx = children.index(self._active_slot)
                if idx > 0:
                    self._active_slot = children[idx - 1]
                    self._active_slot.cursor_pos = len(self._active_slot.items)
                    return
                self._active_slot = self._slot_stack.pop()
                self._active_slot.cursor_pos = i
                return
        self._active_slot = self._slot_stack.pop()

    # ================================================================
    # Live evaluation
    # ================================================================

    def _update_eval(self):
        if not self._eval_callback:
            self._eval_result = None
            self._eval_error = None
            return

        text = self.to_text().strip()
        if text.endswith("="):
            expr_text = text[:-1].strip()
            if expr_text:
                try:
                    self._eval_result = self._eval_callback(expr_text)
                    self._eval_error = None
                except Exception as ex:
                    self._eval_result = None
                    self._eval_error = str(ex)[:60]
            else:
                self._eval_result = None
                self._eval_error = None
        else:
            self._eval_result = None
            self._eval_error = None

    # ================================================================
    # Rendering
    # ================================================================

    def render(self):
        for item_id in self._items:
            try:
                self.canvas.delete(item_id)
            except Exception:
                pass
        self._items.clear()
        self._cursor_rx = None
        self._cursor_ry = None
        self._cursor_rh = None

        box = self._render_slot(self.root, self.x, self.y, self.font_size)

        if self._eval_result is not None or self._eval_error:
            self._render_eval_result(self.x + box.width + 4, self.y, box)

        if self._cursor_visible and self._cursor_rx is not None:
            self._draw_cursor()

    def _render_eval_result(self, rx: float, ry: float, box: _Box):
        from ..units import Quantity

        f = self._get_font(self.font_size)
        base_y = ry + box.baseline - self._line_height(self.font_size) * 0.6

        if self._eval_error:
            tid = self.canvas.create_text(
                rx, base_y, text=self._eval_error,
                anchor="nw", font=f, fill=_ERROR_COLOR)
            self._items.append(tid)
            return

        val = self._eval_result
        if isinstance(val, Quantity):
            val_text = self._fmt(val.value)
            unit_str = val.display_unit if hasattr(val, "display_unit") else str(val.unit)
            tid = self.canvas.create_text(
                rx, base_y, text=val_text, anchor="nw", font=f, fill=_RESULT_COLOR)
            self._items.append(tid)
            if unit_str:
                vw, _ = self._text_size(val_text, self.font_size)
                sp, _ = self._text_size(" ", self.font_size)
                uid = self.canvas.create_text(
                    rx + vw + sp, base_y, text=unit_str,
                    anchor="nw", font=f, fill=_UNIT_COLOR)
                self._items.append(uid)
        else:
            res_text = self._fmt(val)
            tid = self.canvas.create_text(
                rx, base_y, text=res_text,
                anchor="nw", font=f, fill=_RESULT_COLOR)
            self._items.append(tid)

    def _render_slot(self, slot: EditSlot, x: float, y: float, fs: int) -> _Box:
        if not slot.items:
            ph_w = max(fs * 0.8, 8)
            ph_h = self._line_height(fs)
            if slot is self._active_slot:
                self._cursor_rx = x
                self._cursor_ry = y
                self._cursor_rh = ph_h
            else:
                rid = self.canvas.create_rectangle(
                    x + 1, y + 2, x + ph_w - 1, y + ph_h - 2,
                    outline=_PLACEHOLDER_COLOR, fill="", dash=(2, 2))
                self._items.append(rid)
            return _Box(ph_w, ph_h, ph_h * 0.6)

        measures = [self._measure_item(it, fs) for it in slot.items]
        max_bl = max(m.baseline for m in measures) if measures else 0
        max_desc = max(m.height - m.baseline for m in measures) if measures else 0
        total_h = max_bl + max_desc
        if total_h < 1:
            total_h = self._line_height(fs)
            max_bl = total_h * 0.6

        cx = x
        for i, (item, mbox) in enumerate(zip(slot.items, measures)):
            if slot is self._active_slot and i == slot.cursor_pos:
                self._cursor_rx = cx
                self._cursor_ry = y
                self._cursor_rh = total_h

            item_y = y + max_bl - mbox.baseline
            self._render_item(item, cx, item_y, fs)
            cx += mbox.width

        if slot is self._active_slot and slot.cursor_pos == len(slot.items):
            self._cursor_rx = cx
            self._cursor_ry = y
            self._cursor_rh = total_h

        return _Box(cx - x, total_h, max_bl)

    # ---- Measure ----

    def _measure_item(self, item: EditItem, fs: int) -> _Box:
        if isinstance(item, EText):
            style = self._text_style(item.text)
            w, h = self._text_size(item.text, fs, style)
            return _Box(w, h, h * 0.6)
        if isinstance(item, EOp):
            display = _OP_DISPLAY.get(item.op, f" {item.op} ")
            w, h = self._text_size(display, fs)
            return _Box(w, h, h * 0.6)
        if isinstance(item, EFraction):
            return self._measure_fraction(item, fs)
        if isinstance(item, ESuperscript):
            return self._measure_sup(item, fs)
        if isinstance(item, EParens):
            return self._measure_parens(item, fs)
        if isinstance(item, EUnit):
            w, h = self._text_size(item.name or " ", fs)
            return _Box(w, h, h * 0.6)
        return _Box(0, 0, 0)

    def _measure_slot(self, slot: EditSlot, fs: int) -> _Box:
        if not slot.items:
            ph_w = max(fs * 0.8, 8)
            ph_h = self._line_height(fs)
            return _Box(ph_w, ph_h, ph_h * 0.6)
        total_w = 0.0
        max_bl = 0.0
        max_desc = 0.0
        for item in slot.items:
            m = self._measure_item(item, fs)
            total_w += m.width
            max_bl = max(max_bl, m.baseline)
            max_desc = max(max_desc, m.height - m.baseline)
        return _Box(total_w, max_bl + max_desc, max_bl)

    def _measure_fraction(self, item: EFraction, fs: int) -> _Box:
        nb = self._measure_slot(item.numerator, fs)
        db = self._measure_slot(item.denominator, fs)
        w = max(nb.width, db.width) + 2 * _FRAC_HPAD
        h = nb.height + db.height + 2 * _FRAC_VPAD + 2
        return _Box(w, h, nb.height + _FRAC_VPAD + 1)

    def _measure_sup(self, item: ESuperscript, fs: int) -> _Box:
        sup_fs = max(int(fs * _SUP_SCALE), 6)
        eb = self._measure_slot(item.exponent, sup_fs)
        base_h = self._line_height(fs)
        raise_amt = base_h * 0.35
        w = eb.width + 1
        h = max(base_h, eb.height + raise_amt)
        return _Box(w, h, h * 0.6)

    def _measure_parens(self, item: EParens, fs: int) -> _Box:
        ib = self._measure_slot(item.inner, fs)
        pw, ph = self._text_size("(", fs)
        w = pw + ib.width + pw
        h = max(ph, ib.height)
        return _Box(w, h, max(ph * 0.6, ib.baseline))

    # ---- Render items ----

    def _render_item(self, item: EditItem, x: float, y: float, fs: int):
        if isinstance(item, EText):
            self._render_text(item, x, y, fs)
        elif isinstance(item, EOp):
            self._render_op(item, x, y, fs)
        elif isinstance(item, EFraction):
            self._render_fraction(item, x, y, fs)
        elif isinstance(item, ESuperscript):
            self._render_sup(item, x, y, fs)
        elif isinstance(item, EParens):
            self._render_parens(item, x, y, fs)
        elif isinstance(item, EUnit):
            self._render_unit(item, x, y, fs)

    def _render_text(self, item: EText, x: float, y: float, fs: int):
        style = self._text_style(item.text)
        color = _NUMBER_COLOR
        f = self._get_font(fs, style)
        tid = self.canvas.create_text(x, y, text=item.text, anchor="nw",
                                       font=f, fill=color)
        self._items.append(tid)

    def _render_op(self, item: EOp, x: float, y: float, fs: int):
        display = _OP_DISPLAY.get(item.op, f" {item.op} ")
        f = self._get_font(fs)
        tid = self.canvas.create_text(x, y, text=display, anchor="nw",
                                       font=f, fill=_OPERATOR_COLOR)
        self._items.append(tid)

    def _render_fraction(self, item: EFraction, x: float, y: float, fs: int):
        nb = self._measure_slot(item.numerator, fs)
        db = self._measure_slot(item.denominator, fs)
        bar_w = max(nb.width, db.width) + 2 * _FRAC_HPAD

        num_x = x + (bar_w - nb.width) / 2
        self._render_slot(item.numerator, num_x, y, fs)

        bar_y = y + nb.height + _FRAC_VPAD
        lid = self.canvas.create_line(x, bar_y, x + bar_w, bar_y,
                                       fill=_OPERATOR_COLOR, width=1)
        self._items.append(lid)

        den_y = bar_y + _FRAC_VPAD + 2
        den_x = x + (bar_w - db.width) / 2
        self._render_slot(item.denominator, den_x, den_y, fs)

    def _render_sup(self, item: ESuperscript, x: float, y: float, fs: int):
        sup_fs = max(int(fs * _SUP_SCALE), 6)
        self._render_slot(item.exponent, x, y, sup_fs)

    def _render_parens(self, item: EParens, x: float, y: float, fs: int):
        ib = self._measure_slot(item.inner, fs)
        f = self._get_font(fs)
        pw, ph = self._text_size("(", fs)

        lp = self.canvas.create_text(x, y, text="(", anchor="nw",
                                      font=f, fill=_OPERATOR_COLOR)
        self._items.append(lp)

        inner_y = y + max(0, (ph - ib.height) / 2)
        self._render_slot(item.inner, x + pw, inner_y, fs)

        rp = self.canvas.create_text(x + pw + ib.width, y, text=")",
                                      anchor="nw", font=f, fill=_OPERATOR_COLOR)
        self._items.append(rp)

    def _render_unit(self, item: EUnit, x: float, y: float, fs: int):
        f = self._get_font(fs)
        name = item.name or " "
        tid = self.canvas.create_text(x, y, text=name, anchor="nw",
                                       font=f, fill=_UNIT_COLOR)
        self._items.append(tid)

    # ---- Cursor ----

    def _draw_cursor(self):
        if self._cursor_rx is None:
            return
        x = self._cursor_rx
        y = self._cursor_ry
        h = self._cursor_rh or self._line_height(self.font_size)
        self._cursor_item = self.canvas.create_line(
            x, y, x, y + h, fill=_CURSOR_COLOR, width=2)
        self._items.append(self._cursor_item)

    def _start_blink(self):
        self._blink()

    def _blink(self):
        self._cursor_visible = not self._cursor_visible
        if self._cursor_item is not None:
            try:
                fill = _CURSOR_COLOR if self._cursor_visible else self.canvas["bg"]
                self.canvas.itemconfigure(self._cursor_item, fill=fill)
            except Exception:
                pass
        try:
            self._blink_id = self.canvas.after(530, self._blink)
        except Exception:
            pass

    def stop_blink(self):
        if self._blink_id:
            try:
                self.canvas.after_cancel(self._blink_id)
            except Exception:
                pass
            self._blink_id = None

    # ---- Helpers ----

    def _text_style(self, text: str) -> str:
        if not text:
            return "italic"
        if text[0].isdigit() or text[0] == ".":
            return ""
        if text in _BUILTIN_VARS:
            return "bold"
        return "italic"

    def _fmt(self, val: Any) -> str:
        if isinstance(val, float):
            if _math.isnan(val):
                return "NaN"
            if _math.isinf(val):
                return "∞" if val > 0 else "-∞"
            if val == int(val) and abs(val) < 1e15:
                return str(int(val))
            return f"{val:.4g}"
        if isinstance(val, int):
            return str(val)
        return str(val)

    # ================================================================
    # Text conversion
    # ================================================================

    def to_text(self) -> str:
        return self._slot_to_text(self.root)

    def _slot_to_text(self, slot: EditSlot) -> str:
        parts: list[str] = []
        for item in slot.items:
            if isinstance(item, EText):
                parts.append(item.text)
            elif isinstance(item, EOp):
                if item.op == ":":
                    parts.append(" := ")
                elif item.op in ("+", "-", "*", "=", "<", ">",
                                 "≤", "≥", "≠"):
                    parts.append(f" {item.op} ")
                elif item.op == ",":
                    parts.append(", ")
                else:
                    parts.append(item.op)
            elif isinstance(item, EFraction):
                num = self._slot_to_text(item.numerator) or "0"
                den = self._slot_to_text(item.denominator) or "1"
                parts.append(f"({num})/({den})")
            elif isinstance(item, ESuperscript):
                exp = self._slot_to_text(item.exponent) or "1"
                parts.append(f"^({exp})")
            elif isinstance(item, EParens):
                inner = self._slot_to_text(item.inner) or "0"
                parts.append(f"({inner})")
            elif isinstance(item, EUnit):
                parts.append(f"'{item.name}'")
        return "".join(parts)

    # ================================================================
    # Load from AST
    # ================================================================

    def from_ast(self, node: ASTNode, has_result: bool = False):
        self.root = EditSlot()
        self._active_slot = self.root
        self._slot_stack = []
        self._ast_to_slot(node, self.root)
        if has_result and not (isinstance(node, BinaryOp) and node.operator == ":"):
            self.root.items.append(EOp("="))
        self.root.cursor_pos = len(self.root.items)
        self._update_eval()
        self.render()

    def _ast_to_slot(self, node: ASTNode, slot: EditSlot):
        if isinstance(node, Number):
            v = node.value
            if isinstance(v, float) and v == int(v) and abs(v) < 1e15:
                slot.items.append(EText(str(int(v))))
            else:
                slot.items.append(EText(str(v)))
        elif isinstance(node, Variable):
            slot.items.append(EText(node.name))
        elif isinstance(node, UnitRef):
            slot.items.append(EUnit(node.name))
        elif isinstance(node, StringLiteral):
            slot.items.append(EText(f'"{node.value}"'))
        elif isinstance(node, UnaryOp):
            if node.operator == "-":
                slot.items.append(EOp("-"))
            self._ast_to_slot(node.operand, slot)
        elif isinstance(node, BinaryOp):
            if node.operator == "/":
                frac = EFraction()
                self._ast_to_slot(node.left, frac.numerator)
                frac.numerator.cursor_pos = len(frac.numerator.items)
                self._ast_to_slot(node.right, frac.denominator)
                frac.denominator.cursor_pos = len(frac.denominator.items)
                slot.items.append(frac)
            elif node.operator == "^":
                self._ast_to_slot(node.left, slot)
                sup = ESuperscript()
                self._ast_to_slot(node.right, sup.exponent)
                sup.exponent.cursor_pos = len(sup.exponent.items)
                slot.items.append(sup)
            elif node.operator == ":":
                self._ast_to_slot(node.left, slot)
                slot.items.append(EOp(":"))
                self._ast_to_slot(node.right, slot)
            elif node.operator == "*" and isinstance(node.right, UnitRef):
                self._ast_to_slot(node.left, slot)
                slot.items.append(EOp("*"))
                self._ast_to_slot(node.right, slot)
            else:
                self._ast_to_slot(node.left, slot)
                slot.items.append(EOp(node.operator))
                self._ast_to_slot(node.right, slot)
        elif isinstance(node, FunctionCall):
            slot.items.append(EText(node.name))
            parens = EParens()
            for i, arg in enumerate(node.args):
                if i > 0:
                    parens.inner.items.append(EOp(","))
                self._ast_to_slot(arg, parens.inner)
            parens.inner.cursor_pos = len(parens.inner.items)
            slot.items.append(parens)
        elif isinstance(node, Evaluation):
            self._ast_to_slot(node.expression, slot)
            slot.items.append(EOp("="))

    def from_text(self, text: str):
        from ..infix_parser import parse_infix
        ast = parse_infix(text)
        if ast is not None:
            has_result = text.strip().endswith("=")
            self.from_ast(ast, has_result=has_result)
        elif text.strip():
            self.root = EditSlot()
            self.root.items.append(EText(text.strip()))
            self.root.cursor_pos = 1
            self._active_slot = self.root
            self._slot_stack = []
            self.render()

    # ================================================================
    # Cleanup
    # ================================================================

    def destroy(self):
        self.stop_blink()
        for item_id in self._items:
            try:
                self.canvas.delete(item_id)
            except Exception:
                pass
        self._items.clear()

    def get_items(self) -> list[int]:
        return list(self._items)
