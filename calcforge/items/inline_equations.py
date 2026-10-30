"""Equations inside a text box (the user, 2026-10-29: "typing \\ in a text
box or markup should open a CalcForge-style equation where I can do quick
math"; 2026-10-30: "the moment I type \\, an SMath style input appears and I
type in that … the inside equation should have all the normal stuff like dp
sig figs etc like an SMath equation").

Typing ``\\`` while writing in a box opens SMath's equation editor at the
caret — the very editor an equation on the page is typed in (ui/calcedit.py)
— and Enter puts the caret back in the words after it. The finished
equation sits in the text as an inline object, drawn typeset as an equation
on the page is; right-clicked it has an equation's own menu (ui/calcmenu.py:
Show Expression, Decimal Places, Significant Figures, Font …); clicked or
double-clicked, it is typed into again.

Each one is a CalcItem of its own, a child of the box (InlineCalcItem): its
region is in the document's worksheet at the equation's place on the page,
so it reads in order with the equations round the box, defines for the
equations and cells after it, and is listed in the Variables panel as a
"Text box". In the box's QTextDocument it is one inline image the size of
the equation — a blank one, named for the equation (``calcforge-inline://``
and its id): the layout makes room for it where the words put it, and the
box draws the equation there itself (paint_equations). (PySide6 does not
let a Python QTextObjectInterface register as a text object handler, so an
image it is: the name survives the document's HTML too.)
"""
from __future__ import annotations

import re
import uuid
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, QSizeF, QUrl
from PySide6.QtGui import (QFontMetrics, QImage, QTextCharFormat, QTextCursor, QTextDocument,
                           QTextFormat, QTextImageFormat)
from PySide6.QtWidgets import QGraphicsItem

from ..calc.docsheet import PX_PER_PT
from .calc import CalcItem

#: the property on the placeholder's format naming the equation (kept
#: through copies of the document; the image's name carries it through HTML)
UID_PROPERTY = int(QTextFormat.UserProperty) + 7
#: the character an inline object is in the text
PLACEHOLDER = "￼"
#: the blank image's name: this and the equation's id
SCHEME = "calcforge-inline://"
#: how the Variables panel names where one is defined
SOURCE = "Text box"

_ASSIGN = re.compile(r"\s*(?::=|\u2254)\s*")      # := as typed, ≔ as the region says it
#: the codes of 29 Oct, {\5+2=} and {\!t*t=}, in a document saved then
CODE = re.compile(r"\{\\([^{}]*)\}")


def new_uid() -> str:
    return uuid.uuid4().hex[:12]


def resource_name(uid: str) -> str:
    return SCHEME + str(uid)


def uid_of(fmt) -> str:
    """The equation an inline object's format names, or ""."""
    if fmt is None:
        return ""
    uid = fmt.property(UID_PROPERTY)
    if uid:
        return str(uid)
    if fmt.isImageFormat():
        name = fmt.toImageFormat().name()
        if name.startswith(SCHEME):
            return name[len(SCHEME):]
    return ""


def is_equation(fmt) -> bool:
    return fmt is not None and fmt.objectType() == QTextFormat.ImageObject and bool(uid_of(fmt))


def equation_format(uid: str, like=None, size: Optional[QSizeF] = None) -> QTextImageFormat:
    """The format an inline equation's placeholder wears: a blank image the
    size of the equation, named for it, centred on the words' x-height."""
    fmt = like.toImageFormat() if like is not None else QTextImageFormat()
    fmt.setObjectType(QTextFormat.ImageObject)
    fmt.setName(resource_name(uid))
    fmt.setProperty(UID_PROPERTY, str(uid))
    fmt.setVerticalAlignment(QTextCharFormat.AlignMiddle)
    if size is not None:
        fmt.setWidth(max(float(size.width()), 1.0))
        fmt.setHeight(max(float(size.height()), 1.0))
    return fmt


_BLANK: list = []


def blank() -> QImage:
    if not _BLANK:
        image = QImage(1, 1, QImage.Format_ARGB32)
        image.fill(0)
        _BLANK.append(image)
    return _BLANK[0]


def add_resource(document, uid: str) -> None:
    document.addResource(QTextDocument.ImageResource, QUrl(resource_name(uid)), blank())


def install(document) -> None:
    """Have *document* know the blank image of each equation in it."""
    for _position, uid, _fmt in fragments(document):
        add_resource(document, uid)


def fragments(document) -> list:
    """[(position, uid, format)] of the inline equations in *document*, in
    order."""
    found = []
    block = document.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            fmt = fragment.charFormat()
            if is_equation(fmt):
                found.append((fragment.position(), uid_of(fmt), fmt))
            it += 1
        block = block.next()
    return found


def placeholders(document) -> list:
    """[(position, uid)] of the inline equations in *document*, in order."""
    return [(position, uid) for position, uid, _fmt in fragments(document)]


def object_rect(document, position: int, fmt, size: QSizeF) -> QRectF:
    """Where the layout draws the inline object at *position*, in document
    coordinates — as QTextDocumentLayout::resizeInlineObject places one
    aligned AlignMiddle: its middle half an x-height above the baseline."""
    width, height = max(float(size.width()), 1.0), max(float(size.height()), 1.0)
    block = document.findBlock(position)
    layout = block.layout() if block.isValid() else None
    if layout is None:
        return QRectF(0, 0, width, height)
    within = position - block.position()
    line = layout.lineForTextPosition(within)
    if not line.isValid():
        return QRectF(0, 0, width, height)
    x = layout.position().x() + line.cursorToX(within)[0]
    baseline = layout.position().y() + line.y() + line.ascent()
    half_x = QFontMetrics(fmt.toCharFormat().font()).xHeight() / 2.0
    ascent = (height + half_x) / 2.0
    return QRectF(x, baseline - ascent, width, height)


def paint_equations(painter, document, host) -> None:
    """Draw *host*'s equations where *document*'s layout left room for them
    (the one being typed in draws itself, caret and all)."""
    for position, uid, fmt in fragments(document):
        item = host.inline_equation(uid)
        if item is None or item.focused:
            continue
        item.paint_inline(painter, object_rect(document, position, fmt, item.local_rect().size()))


# -- the equation ----------------------------------------------------------------

class InlineCalcItem(CalcItem):
    """An equation inside a text box: the box's child, drawn in the words'
    picture where its placeholder is laid out, typed into in place."""

    INLINE = True
    MARKUP_LOOK = True     # part of the box's look, for the page's squares (ui/markuplayer.py)

    def __init__(self, host, uid: str, data: Optional[dict] = None):
        super().__init__(data)
        self.host = host
        self.inline_uid = str(uid)
        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setParentItem(host)

    # -- where it is -----------------------------------------------------------------
    def _page_frame(self):
        frame = self.parentItem()
        while frame is not None and not (hasattr(frame, "page") and hasattr(frame, "document")):
            frame = frame.parentItem()
        return frame

    def page_turns(self) -> int:
        host = self.host
        rotation = getattr(host, "_edit_rotation", None)
        if rotation is None:
            rotation = host.rotation() if host is not None else 0.0
        return int(round(float(rotation) / 90.0)) % 4

    def reading_position(self) -> tuple:
        frame = self._page_frame()
        if frame is None:
            return super().reading_position()
        point = self.mapToItem(frame, QPointF(0, 0))
        x, y = point.x(), point.y()
        width, height = frame.page.width_pt, frame.page.height_pt
        for _ in range(self.page_turns()):
            x, y = y, width - x
            width, height = height, width
        return x * PX_PER_PT, y * PX_PER_PT

    def snap_to_grid(self) -> None:
        return                  # on the words' line, not SMath's grid

    def show_upright(self, view_turn: float = 0.0) -> None:
        return                  # the box is shown upright while it is typed in

    def leave_upright(self) -> None:
        return

    def itemChange(self, change, value):
        result = super().itemChange(change, value)
        if change == QGraphicsItem.ItemSceneHasChanged and self.scene() is not None \
                and self.region is None and self._page_frame() is not None:
            self._attach()      # the box came onto a page with it inside
        return result

    def _attach(self) -> None:
        super()._attach()
        if self.region is not None:
            self.region.calcforge_source = SOURCE

    # -- its drawing -------------------------------------------------------------------
    def relayout(self) -> None:
        self.prepareGeometryChange()
        if self._view is not None:
            self._view.focused = self.focused
            self._view.max_width = 0.0            # never broken onto more lines
            with self._looking():
                self._view.relayout()
            from ..calc.condformat import look_for
            self._last_look = look_for(self, self._settings())
        self.geometryChanged.emit()
        self.update()
        host = self.host
        if host is not None:
            host.inline_equation_changed(self)

    def paint(self, painter, option, widget=None) -> None:
        if not self.focused:
            return              # the words' picture draws it (paint_inline)
        super().paint(painter, option, widget)

    def paint_inline(self, painter, rect: QRectF) -> None:
        """Drawn where the words' layout left room for it."""
        view = self._view or self._preview_view()
        if view is None:
            return
        painter.save()
        painter.translate(rect.topLeft())
        with self._looking():
            self._paint_view(painter, view)
        painter.restore()

    def summary_text(self) -> str:
        """The equation as words, for the Markups List, a bookmark's title
        and the PDF's own text of the box: "5+2 = 7", "t := 5"."""
        typed = (self.text() or "").replace("\u2254", ":=")
        region = self.region
        if region is None or getattr(region, "pending", False):
            return typed
        try:
            from ..ui.variablespanel import _value_text
            worksheet = self._sheet.worksheet
            fmt = region.fmt or worksheet.format
            expression = typed[:-1].rstrip() if typed.endswith("=") else typed
            if region.error is not None:
                return f"{expression}: {region.error.message}"
            if region.defined_vars:
                return _ASSIGN.sub(" := ", typed)
            shown, problem = _value_text(worksheet, region, region.value, fmt)
            if problem:
                return f"{expression}: {problem}"
            return f"{expression} = {shown}" if region.show_input else shown
        except Exception:  # noqa: BLE001 - words for a list, never worth an error
            return typed


def placeholder_cursor(document, position: int) -> QTextCursor:
    """A cursor over the inline object at *position*."""
    cursor = QTextCursor(document)
    cursor.setPosition(position)
    cursor.setPosition(position + 1, QTextCursor.KeepAnchor)
    return cursor


# -- the codes of 29 Oct --------------------------------------------------------------

def keys_for(body: str) -> Optional[str]:
    """The keystrokes that make the region in SMath's editor from a code's
    body — ``t:=5`` is typed ``t:5``, ``5+2=`` as it is — or None for an
    empty one."""
    text = body.strip()
    if text.startswith("!"):
        text = text[1:].strip()
    if not text:
        return None
    return _ASSIGN.sub(":", text)


def migrate_codes(text: str) -> tuple:
    """A box's words from a document saved on 29 Oct, its {\\5+2=} codes
    turned into equations: (the words with a placeholder character for
    each, [(uid, region record, show the expression)])."""
    from .calc import _typed_region_data
    made = []

    def one(match):
        body = match.group(1)
        keys = keys_for(body)
        if not keys:
            return ""
        try:
            data = _typed_region_data(keys)
        except Exception:  # noqa: BLE001 - what can't be typed is left as words
            return match.group(0)
        made.append((new_uid(), data, body.lstrip().startswith("!")))
        return PLACEHOLDER
    return CODE.sub(one, text or ""), made
