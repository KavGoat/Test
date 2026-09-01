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


def paint_pages(device, document: Document, pages: Iterable, resolution: float) -> None:
    """Render *pages* onto a paged paint device."""
    painter = QPainter()
    started = False
    for page in pages:
        if page.scene is None:
            continue
        _apply_layout(device, page)
        if not started:
            if not painter.begin(device):
                raise OSError("Could not start the print job")
            started = True
        else:
            device.newPage()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        scale = resolution / 72.0
        target = QRectF(0, 0, page.width_pt * scale, page.height_pt * scale)
        page.scene.render_page(painter, target, for_print=True)
    if started:
        painter.end()


def export_pdf(document: Document, path: str, pages: Optional[list] = None,
               resolution: int = 300) -> None:
    writer = QPdfWriter(path)
    writer.setResolution(resolution)
    writer.setTitle(document.title)
    writer.setCreator("CalcForge")
    paint_pages(writer, document, pages if pages is not None else document.pages, resolution)


def print_document(document: Document, printer: QPrinter,
                   pages: Optional[list] = None) -> None:
    paint_pages(printer, document, pages if pages is not None else document.pages,
                printer.resolution())


def export_images(document: Document, folder: str, dpi: float = 200.0,
                  prefix: str = "page") -> list[str]:
    written = []
    for index, page in enumerate(document.pages):
        if page.scene is None:
            continue
        image = page.scene.render_image(dpi=dpi, for_print=True)
        path = f"{folder}/{prefix}_{index + 1:02d}.png"
        image.save(path, "PNG")
        written.append(path)
    return written


def export_markups_csv(document: Document, path: str) -> int:
    pass

    rows = []
    for index, page in enumerate(document.pages):
        if page.scene is None:
            continue
        for item in page.scene.ordered_markups():
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
