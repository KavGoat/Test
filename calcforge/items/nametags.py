"""Name tags (the user's request, 2026-10-14).

A named cell or block, a table and a sheet carry a small tag with the name
at their top-left corner, on screen and on paper, so a printed page says
what each thing is. View ▸ Name tags hides them (a document setting).

Only cells named as CalcForge variables (the cell's Variable box,
DefinedName.variable) carry one: a spreadsheet's own names (Define Name,
the Name Box, the Name Manager, an Excel file's) are the sheet's, read as
Sheet.Name, and are not tagged (the user, 2026-10-21).
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPen

from ..core.typography import page_font

INK = QColor("#3d434b")
FILL = QColor("#eef1f4")
EDGE = QColor("#8a929c")
CELL_PT = 5.0          # a named cell's tag, inside its top-left corner
OUTER_PT = 6.5         # a table's or sheet's tag, above its top-left corner


def shown(item) -> bool:
    """Name tags are on for the document *item* is on."""
    frame = item.parentItem() if item is not None else None
    document = getattr(frame, "document", None)
    settings = getattr(document, "settings", None)
    return bool(getattr(settings, "show_name_tags", True))


def tag_size(text: str, points: float) -> tuple:
    metrics = QFontMetricsF(page_font("", points))
    return metrics.horizontalAdvance(text) + points * 0.9, metrics.height() + 1.0


def draw_tag(painter: QPainter, at: QPointF, text: str, points: float,
             above: bool = False) -> QRectF:
    """A small tag of *text*: its top-left at *at* (its bottom-left, *above*)."""
    w, h = tag_size(text, points)
    rect = QRectF(at.x(), at.y() - h if above else at.y(), w, h)
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(EDGE, 0.5)
    painter.setPen(pen)
    painter.setBrush(FILL)
    painter.drawRoundedRect(rect, 1.5, 1.5)
    painter.setFont(page_font("", points))
    painter.setPen(INK)
    painter.drawText(rect, Qt.AlignCenter, text)
    painter.restore()
    return rect


def _signature(wb) -> tuple:
    # (a scope is a sheet id, an imported workbook's id or None: sorted as text)
    return tuple(sorted(((key[0], str(key[1])), dn.refers_to, dn.variable)
                        for key, dn in wb.names.items())), \
        tuple((s.id, s.name) for s in wb.sheets)


def named_blocks(sheet) -> list:
    """The CalcForge variables that name cells of *sheet*: [(name, (t, l,
    b, r))], first come first (top to bottom, left to right)."""
    wb = sheet.workbook
    sig = _signature(wb)
    memo = getattr(wb, "_name_tag_memo", None)
    if memo is None or memo[0] != sig:
        memo = (sig, _resolve(wb))
        wb._name_tag_memo = memo
    return memo[1].get(sheet.id, [])


def _resolve(wb) -> dict:
    from ..sheet import formula as F
    from ..sheet.evaluate import Ctx, RefValue, ev

    out: dict = {}
    for dn in wb.names.values():
        if not dn.variable:
            continue                 # a spreadsheet's own name: no tag
        home = wb.sheet_by_id(dn.sheet) if dn.sheet else \
            (wb.sheet_by_id(dn.home) if dn.home else (wb.sheets[0] if wb.sheets else None))
        if home is None:
            continue
        try:
            got = ev(F.parse(dn.refers_to).tree, Ctx(wb, home, 0, 0))
        except Exception:  # noqa: BLE001 - a name that isn't cells has no tag
            continue
        if isinstance(got, RefValue) and got.sheet is not None:
            out.setdefault(got.sheet.id, []).append(
                (dn.name, (got.top, got.left, got.bottom, got.right)))
    for blocks in out.values():
        blocks.sort(key=lambda nb: (nb[1][0], nb[1][1], nb[0].lower()))
    return out


def paint_cell_tags(item, painter: QPainter, r0: int, r1: int, c0: int, c1: int) -> None:
    """The tags of the named cells and blocks whose top-left cell is in rows
    r0–r1, columns c0–c1 of table or sheet *item*."""
    sheet = item.sheet
    if sheet is None or not shown(item):
        return
    rows, cols = item.size
    taken: dict = {}
    for name, (t, l, _b, _r) in named_blocks(sheet):
        if not (r0 <= t <= r1 and c0 <= l <= c1) or t >= rows or l >= cols:
            continue
        rect = item.cell_rect(t, l)
        # two names on one cell: the second beside the first
        x = taken.get((t, l), rect.left() + 0.6)
        tag = draw_tag(painter, QPointF(x, rect.top() + 0.6), name, CELL_PT)
        taken[(t, l)] = tag.right() + 1.0
