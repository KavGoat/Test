"""Calculation sections (the user's request, 2026-10-11).

A calc section break sits above a page: from that page on is a new document
for the calculation — variables, functions, tables and sheets defined before
it are not seen after it. Something can be made global instead (the user's
choice): an equation (right-click ▸ Global, or the Variables panel) or a
table's or sheet's cells (right-click ▸ Make Global); then every section
after it reads it as well (the user's choice: every later section).

The break is shown above its page on the canvas, as a band in the gap
between the pages; it never prints. The Variables panel lists the variables
section by section.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen

BAND = QColor("#7b3fbf")           # the section break's colour on the canvas


@dataclass
class Section:
    number: int                   # 1-based
    first: int                    # first page index
    last: int                     # last page index
    title: str

    @property
    def label(self) -> str:
        pages = f"page {self.first + 1}" if self.first == self.last else \
            f"pages {self.first + 1}–{self.last + 1}"
        name = f" · {self.title}" if self.title else ""
        return f"Section {self.number}{name} ({pages})"


def sections(document) -> list:
    """The document's calculation sections, first to last."""
    pages = document.pages
    starts = [0] + [i for i, page in enumerate(pages) if i and page.section_break]
    out = []
    for n, first in enumerate(starts):
        last = (starts[n + 1] - 1) if n + 1 < len(starts) else len(pages) - 1
        title = pages[first].section_title if first else ""
        out.append(Section(n + 1, first, last, title))
    return out


def section_of_page(document, index: int) -> Section:
    for section in sections(document):
        if section.first <= index <= section.last:
            return section
    return sections(document)[0]


def has_sections(document) -> bool:
    return any(i and page.section_break for i, page in enumerate(document.pages))


# -- breaks --------------------------------------------------------------------------------
def set_break(window, index: int, on: bool, title: Optional[str] = None) -> None:
    """Put a calc section break above page *index* (or take it out), one undo step."""
    pages = window.document.pages
    if not 0 < index < len(pages):
        window.status_hint.setText("The first page always starts the first section")
        return
    page = pages[index]
    if page.section_break == bool(on) and (title is None or title == page.section_title):
        return

    def mutate():
        page.section_break = bool(on)
        if title is not None:
            page.section_title = title
        elif not on:
            page.section_title = ""
    label = "Insert calc section break" if on and not page.section_break else \
        ("Remove calc section break" if not on else "Rename calc section")
    window._structural_change(label, mutate, preserve_view=True)
    recalculate(window)
    window.view.viewport().update()
    section = section_of_page(window.document, index)
    window.status_hint.setText(
        f"{section.label}: variables, tables and sheets start afresh here (global ones carry on)"
        if on else "Calc section break removed")


def rename(window, index: int) -> None:
    pages = window.document.pages
    if not 0 < index < len(pages) or not pages[index].section_break:
        return
    from PySide6.QtWidgets import QInputDialog
    if not getattr(window, "interactive_prompts", True):
        return
    text, ok = QInputDialog.getText(window, "Calc section", "Name of this section:",
                                    text=pages[index].section_title)
    if ok:
        set_break(window, index, True, text.strip())


def recalculate(window) -> None:
    """Sections changed: every equation, table and sheet calculates again."""
    from ..calc.docsheet import sheet_for
    from ..sheet.docbook import book_for

    sheet = sheet_for(window.document)
    sheet.recalculate()
    book_for(window.document).sections_changed()


def add_menu(window, menu, index: int) -> None:
    """The page menu's section entries."""
    pages = window.document.pages
    page = pages[index]
    entry = menu.addAction("Calc Section Break Above This Page")
    entry.setCheckable(True)
    entry.setChecked(bool(page.section_break))
    entry.setEnabled(index > 0)
    entry.setToolTip("From this page on, the calculation starts afresh: variables, tables "
                     "and sheets before it are not seen, except the ones made global")
    entry.toggled.connect(lambda on, i=index: set_break(window, i, on))
    if page.section_break:
        menu.addAction("Rename Calc Section…", lambda i=index: rename(window, i))


# -- global cells ----------------------------------------------------------------------------
def global_cells(sheet) -> list:
    return [list(r) for r in (sheet.page or {}).get("global_cells") or []]


def cells_global(sheet, area) -> bool:
    from ..sheet.docbook import DocumentBook
    return DocumentBook._within(tuple(area), global_cells(sheet))


def set_cells_global(window, item, area, on: bool) -> None:
    """Make a table's or sheet's cells global (read by every later section) or not."""
    from . import sheetlayout
    sheet = item.sheet
    t, l, b, r = area
    ranges = global_cells(sheet)
    if on:
        ranges.append([t, l, b, r])
    else:
        kept = []
        for rt, rl, rb, rr in ranges:
            if rb < t or rt > b or rr < l or rl > r:
                kept.append([rt, rl, rb, rr])
                continue
            # what is left of it outside the area, as up to four blocks
            if rt < t:
                kept.append([rt, rl, t - 1, rr])
            if rb > b:
                kept.append([b + 1, rl, rb, rr])
            top, bottom = max(rt, t), min(rb, b)
            if rl < l:
                kept.append([top, rl, bottom, l - 1])
            if rr > r:
                kept.append([top, r + 1, bottom, rr])
        ranges = kept
    sheetlayout.change_options(window, item, "Make cells global" if on else "Make cells local",
                               global_cells=ranges)
    from ..sheet.docbook import book_for
    book_for(window.document).sections_changed()
    from ..calc.docsheet import sheet_for
    sheet_for(window.document).recalculate()


# -- on the canvas ------------------------------------------------------------------------------
def paint_bands(scene, painter: QPainter, rect: QRectF) -> None:
    """The section breaks, as bands in the gap above their pages (screen only)."""
    document = getattr(scene, "document", None)
    if document is None or not has_sections(document):
        return
    from .scene import PAGE_GAP
    numbered = {s.first: s for s in sections(document)}
    for frame in scene.frames:
        page = frame.page
        try:
            index = document.pages.index(page)
        except ValueError:
            continue
        section = numbered.get(index)
        if section is None or index == 0:
            continue
        box = frame.mapRectToScene(frame.page_rect())
        band = QRectF(box.left(), box.top() - PAGE_GAP + 3, box.width(), PAGE_GAP - 6)
        if not band.intersects(rect):
            continue
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(BAND, 1.6, Qt.DashLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        middle = band.center().y()
        painter.drawLine(QPointF(band.left(), middle), QPointF(band.right(), middle))
        font = QFont()
        font.setPointSizeF(max(5.0, band.height() * 0.42))
        font.setBold(True)
        painter.setFont(font)
        text = f"  § {section.label} — calculation starts afresh  "
        width = painter.fontMetrics().horizontalAdvance(text)
        tag = QRectF(band.left() + 12, band.top(), width, band.height())
        painter.setPen(Qt.NoPen)
        painter.setBrush(BAND)
        painter.drawRoundedRect(tag, band.height() / 2, band.height() / 2)
        painter.setPen(QColor("white"))
        painter.drawText(tag, Qt.AlignCenter, text)
        painter.restore()
