"""Fields in a text box (the user, 2026-10-15): the page number, the date,
the document's properties — the codes a running header takes, with SMath's
formats — and an equation's variable, written {=name}. While the box is being
typed into it shows the codes; otherwise, on screen and in print, their
values. A variable's value follows its equation as it is recalculated.
"""
from __future__ import annotations

import re
import time

#: {page}, {date:DD.MM.YYYY}, {title} … and {=L.beam}
FIELD = re.compile(r"\{(=[^{}]+|[a-z]+(?::[^{}]*)?)\}")

#: How long the values worked out for a box are kept before being asked again.
FRESH_FOR = 0.5


def has_fields(text: str) -> bool:
    return "{" in (text or "") and FIELD.search(text) is not None


def variable_value(document, name: str) -> str:
    """An equation's value as the Variables panel shows it ("12.5 kN"), the
    last definition of *name* in reading order; "?" when there is none."""
    try:
        from ..ui.variablespanel import variable_rows
        rows = [row for row in variable_rows(document) if row.name == name]
    except Exception:  # noqa: BLE001 - a field is never worth an error box
        return "?"
    if not rows:
        return "?"
    row = rows[-1]
    if row.error:
        return "?"
    return f"{row.value} {row.unit}".strip()


#: What a blank document property is called on screen, «Author»: one left
#: empty would otherwise go into the box as nothing at all, to be neither
#: seen nor picked out (exercise round 1, F-15). On paper it is still blank.
PLACEHOLDER_NAMES = {"id": "Document id", "filename": "File name"}


def placeholder(body: str) -> str:
    name = body.split(":", 1)[0]
    return "«" + PLACEHOLDER_NAMES.get(name, name.capitalize()) + "»"


def expand(text: str, document, page_index: int, placeholders: bool = False) -> str:
    """*text* with every field replaced by its value — and, with
    *placeholders*, a blank one by its name in «»."""
    if document is None:
        return text

    def one(match):
        body = match.group(1)
        if body.startswith("="):
            return variable_value(document, body[1:].strip())
        value = document.expand_fields(match.group(0), page_index)
        if placeholders and not value.strip():
            return placeholder(body)
        return value
    return FIELD.sub(one, text or "")


def shown_document(item, on_screen: bool = False):
    """The box's words with their fields filled in — a copy of its document,
    each field's place keeping the look it was typed in; kept for a moment.
    *on_screen*, a blank document property shows as «its name»."""
    from PySide6.QtGui import QTextCursor
    doc = item.doc
    raw = doc.toPlainText()
    if not has_fields(raw):
        return doc
    frame = item.parentItem()
    document = getattr(frame, "document", None)
    page = getattr(frame, "page", None)
    pages = getattr(document, "pages", []) or []
    index = pages.index(page) if page in pages else 0
    kept = getattr(item, "_fields_shown", None)
    now = time.monotonic()
    key = (raw, index, doc.textWidth(), bool(on_screen))
    if kept is not None and kept[0] == key and now - kept[1] < FRESH_FOR:
        return kept[2]
    copy = doc.clone(item)
    matches = list(FIELD.finditer(raw))
    for match in reversed(matches):
        cursor = QTextCursor(copy)
        cursor.setPosition(match.start())
        cursor.setPosition(match.end(), QTextCursor.KeepAnchor)
        look = cursor.charFormat()
        cursor.insertText(expand(match.group(0), document, index, on_screen), look)
    copy.setTextWidth(doc.textWidth())
    if kept is not None and kept[2] is not doc:
        kept[2].deleteLater()
    item._fields_shown = (key, now, copy)
    return copy


def shown_text(item) -> str:
    """The box's plain words with their fields filled in."""
    return shown_document(item).toPlainText()
