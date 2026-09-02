"""Printing and export: PDF, images and the markups list."""
from __future__ import annotations

import csv
from typing import Iterable, Optional

from PySide6.QtCore import QMarginsF, QRectF, QSizeF
from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter
from PySide6.QtPrintSupport import QPrinter

from ..core.document import Document


def page_size_for(page) -> QPageSize:
    """Qt page size matching a document page, in points."""
    setup = page.setup
    return QPageSize(QSizeF(setup.width_pt, setup.height_pt), QPageSize.Point,
                     setup.size_name or "Custom", QPageSize.ExactMatch)


def _apply_layout(device, page) -> None:
    layout = QPageLayout()
    layout.setPageSize(page_size_for(page))
    layout.setOrientation(QPageLayout.Portrait)     # size already carries orientation
    layout.setMode(QPageLayout.FullPageMode)
    layout.setMargins(QMarginsF(0, 0, 0, 0))
    device.setPageLayout(layout)


def paint_pages(device, document: Document, pages: Iterable, resolution: float,
                per_page_layout: bool = True) -> None:
    """Render *pages* onto a paged paint device.

    ``QPdfWriter`` accepts a new page size for every page, so an export can mix
    A4 and A3 sheets faithfully.  ``QPrinter`` refuses to change its layout once
    printing has started, so for a real printer the layout is fixed by the first
    page and every other page is scaled to fit it — pass ``per_page_layout=False``
    for that.  The painter is always ended, even if a page fails to draw, because
    leaving it open crashes the print-preview dialog on its next repaint.
    """
    painter = QPainter()
    started = False
    try:
        for page in pages:
            if page.frame is None:
                continue
            if not started:
                _apply_layout(device, page)
                if not painter.begin(device):
                    raise OSError("Could not start the print job")
                started = True
            else:
                if per_page_layout:
                    _apply_layout(device, page)
                device.newPage()
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            page.frame.render_page(painter, _target_rect(painter, page, resolution,
                                                         per_page_layout),
                                   for_print=True)
    finally:
        if started:
            painter.end()


def _target_rect(painter: QPainter, page, resolution: float,
                 per_page_layout: bool) -> QRectF:
    """Where this page lands on the device, in device pixels."""
    if per_page_layout:
        scale = resolution / 72.0
        return QRectF(0, 0, page.width_pt * scale, page.height_pt * scale)
    device = painter.device()
    available = QRectF(0, 0, device.width(), device.height())
    scale = min(available.width() / max(page.width_pt, 1.0),
                available.height() / max(page.height_pt, 1.0))
    width = page.width_pt * scale
    height = page.height_pt * scale
    return QRectF((available.width() - width) / 2, (available.height() - height) / 2,
                  width, height)


def export_pdf(document: Document, path: str, pages: Optional[list] = None,
               resolution: int = 300) -> None:
    writer = QPdfWriter(path)
    writer.setResolution(resolution)
    writer.setTitle(document.title)
    writer.setCreator("CalcForge")
    paint_pages(writer, document, pages if pages is not None else document.pages, resolution)


def pages_for_printer(document: Document, printer: QPrinter) -> list:
    """The pages the print dialog actually asked for."""
    try:
        selection = printer.printRange()
    except Exception:
        return list(document.pages)
    if selection == QPrinter.PageRange:
        first = max(printer.fromPage(), 1)
        last = printer.toPage() or len(document.pages)
        return document.pages[first - 1:last]
    if selection == QPrinter.CurrentPage:
        return list(document.pages)
    return list(document.pages)


def print_document(document: Document, printer: QPrinter,
                   pages: Optional[list] = None) -> None:
    chosen = pages if pages is not None else pages_for_printer(document, printer)
    paint_pages(printer, document, chosen, printer.resolution(), per_page_layout=False)


def export_images(document: Document, folder: str, dpi: float = 200.0,
                  prefix: str = "page") -> list[str]:
    written = []
    for index, page in enumerate(document.pages):
        if page.frame is None:
            continue
        image = page.frame.render_image(dpi=dpi, for_print=True)
        path = f"{folder}/{prefix}_{index + 1:02d}.png"
        image.save(path, "PNG")
        written.append(path)
    return written


def export_markups_csv(document: Document, path: str) -> int:
    rows = []
    for index, page in enumerate(document.pages):
        if page.frame is None:
            continue
        for item in page.frame.ordered_markups():
            rows.append([index + 1, item.display_name(), item.subject,
                         getattr(item, "value_text", ""), item.author,
                         item.created[:10], item.modified[:10], item.layer,
                         item.summary()])
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Page", "Type", "Subject", "Value", "Author", "Created",
                         "Modified", "Layer", "Comment"])
        writer.writerows(rows)
    return len(rows)


def export_variables_csv(document: Document, path: str) -> int:
    from ..core.units import format_quantity

    workspace = document.workspace
    rows = []
    for name, info in sorted(workspace.variables.items(), key=lambda kv: kv[1].order):
        rows.append([name, format_quantity(info.value, 8), info.expression, info.source])
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Name", "Value", "Expression", "Defined in"])
        writer.writerows(rows)
    return len(rows)
