"""Equations inside a text box (the user, 2026-10-29: "typing \\ in a text
box or markup should open a CalcForge-style equation where I can do quick
math").

Typing ``\\`` in a box being written opens one: ``{\\5+2=}`` shows 7,
``{\\test=}`` a variable's value, ``{\\t:=5}`` defines t for every equation
after the box, and ``{\\!test*test=}`` shows the working too, "test*test =
50" (right-click ▸ Show Expression). While the box is typed into the codes
show, as every field's do (items/fields.py); otherwise their results.

Each one is an ordinary region of the document's worksheet, typed as SMath
would type it, at the box's top-left — read in reading order as an equation
there would be, listed in the Variables panel as a "Text box", known to the
equations and cells after it — the way a named measurement defines its
variable (items/calc.MeasureVariable). The box is what the reader sees.
"""
from __future__ import annotations

import re
from typing import Optional

#: what opens an inline equation in a field: {\...}
PREFIX = "\\"
#: and, first inside it, asks for the working to be shown: {\!a*b=}
SHOW = "!"

_ASSIGN = re.compile(r"\s*:=\s*")


def has_inline(text: str) -> bool:
    return "{" + PREFIX in (text or "")


def inline_fields(raw: str) -> list:
    """[(match, body)] of the inline equations in *raw*, in order (body is
    what follows the backslash, the ! flag included)."""
    from .fields import FIELD
    return [(m, m.group(1)[1:]) for m in FIELD.finditer(raw or "")
            if m.group(1).startswith(PREFIX)]


def shown_in_full(body: str) -> bool:
    return body.lstrip().startswith(SHOW)


def typed(body: str) -> str:
    """The equation as typed, without the flag."""
    text = body.strip()
    if text.startswith(SHOW):
        text = text[1:].strip()
    return text


def keys_for(body: str) -> Optional[str]:
    """The keystrokes that make the region in SMath's editor — ``t:=5`` is
    typed ``t:5`` (the colon is the definition), ``5+2=`` as it is — or None
    for nothing to work out."""
    text = typed(body)
    if not text:
        return None
    return _ASSIGN.sub(":", text)


def expression_text(body: str) -> str:
    """The equation as it is shown beside its result: ``t*t`` of ``t*t=``,
    ``t := 5`` of ``t:=5``."""
    text = typed(body)
    if text.endswith("=") and not text.endswith(":="):
        text = text[:-1].rstrip()
    return _ASSIGN.sub(" := ", text)


class InlineEquations:
    """The regions a text box's inline equations are worked out with."""

    SOURCE = "Text box"

    def __init__(self, item):
        self.item = item
        self.regions: list = []
        self._keys: Optional[tuple] = None
        self._sheet = None
        self._listening = False

    # -- where the box is ----------------------------------------------------
    def _frame(self):
        frame = self.item.parentItem()
        return frame if frame is not None and hasattr(frame, "page") \
            and hasattr(frame, "document") else None

    def _position(self, frame) -> tuple:
        from .calc import PX_PER_PT, unturned_px
        item = self.item
        box = item.mapRectToParent(item.local_rect().normalized())
        turns = int(round(item.rotation() / 90.0)) % 4
        return unturned_px(frame, box.left(), box.top(), turns) if turns \
            else (box.left() * PX_PER_PT, box.top() * PX_PER_PT)

    # -- keeping the regions in step with the words ------------------------------
    def sync(self) -> None:
        """The regions as the box's text and place now say: moved with it,
        made afresh when an equation was typed or changed, gone with the box."""
        from ..calc.docsheet import sheet_for
        from .calc import _connect, _typed_region_data
        item = self.item
        frame = self._frame()
        try:
            on_scene = item.scene() is not None
        except RuntimeError:
            on_scene = False
        wanted = [keys_for(body) for _m, body in inline_fields(item.doc.toPlainText())] \
            if frame is not None and on_scene else []
        if not any(wanted):
            self.drop()
            return
        x, y = self._position(frame)
        keys = tuple(wanted)
        if self.regions and keys == self._keys and self._sheet is not None:
            for k, region in enumerate(self.regions):
                if region is not None:
                    # a whisker lower each: the box's equations read in order
                    self._sheet.move(region, frame.page.uid, x, y + k * 0.01)
            return
        self.drop()
        self._sheet = sheet_for(frame.document)
        _connect(self._sheet, frame.scene())
        for k, key in enumerate(keys):
            region = None
            if key:
                try:
                    region = self._sheet.add(_typed_region_data(key), frame.page.uid,
                                             x, y + k * 0.01)
                    region.calcforge_source = self.SOURCE
                except Exception:  # noqa: BLE001 - what can't be typed shows as typed
                    region = None
            self.regions.append(region)
        self._keys = keys
        if not self._listening:
            self._sheet.listeners.append(self._calculated)
            self._listening = True
        self._calculated()

    def drop(self) -> None:
        if self._sheet is not None:
            for region in self.regions:
                if region is not None:
                    self._sheet.remove(region)
            if self._listening:
                try:
                    self._sheet.listeners.remove(self._calculated)
                except ValueError:
                    pass
        self.regions = []
        self._keys = None
        self._listening = False

    def _calculated(self) -> None:
        """A calculation ran: the box shows its results afresh."""
        item = self.item
        try:
            item._fields_shown = None
            item.update()
        except RuntimeError:                   # the box is gone
            self.drop()

    # -- what the box shows for each ---------------------------------------------
    def text_of(self, k: int, body: str) -> str:
        from ..ui.variablespanel import _value_text
        region = self.regions[k] if k < len(self.regions) else None
        expr = expression_text(body)
        if region is None or self._sheet is None:
            return expr                                   # nothing to work out
        if region.pending:
            return expr + " = …" if shown_in_full(body) else "…"
        error = region.error.message if region.error is not None else ""
        worksheet = self._sheet.worksheet
        fmt = region.fmt or worksheet.format
        if region.defined_vars:
            # a definition, shown as typed (t := 5); in full, with its value
            if error:
                return f"{expr}: {error}"
            if shown_in_full(body):
                name, value = next(iter(region.defined_vars.items()))
                shown, problem = _value_text(worksheet, region, value, fmt)
                return f"{expr} = {shown}" if not problem else f"{expr}: {problem}"
            return expr
        if error:
            return f"{expr}: {error}"
        shown, problem = _value_text(worksheet, region, region.value, fmt)
        if problem:
            return f"{expr}: {problem}"
        return f"{expr} = {shown}" if shown_in_full(body) else shown


def inline_text(item, k: int, body: str) -> str:
    """What the box shows for its k-th inline equation."""
    link = getattr(item, "_equations_link", None)
    if link is None:
        return expression_text(body)
    return link.text_of(k, body)
