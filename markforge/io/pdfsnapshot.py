"""Capture source PDF paths without raster previews or a paper fill."""
from __future__ import annotations

import re

import pymupdf
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainterPath

from ..items.base import MarkupItem, Style, register_item
from .pdfvector import PdfFile, _colour_of


def path_from(commands, even_odd=False):
    path = QPainterPath()
    path.setFillRule(Qt.OddEvenFill if even_odd else Qt.WindingFill)
    for command in commands:
        op, *args = command
        if op == "m":
            path.moveTo(*args)
        elif op == "l":
            path.lineTo(*args)
        elif op == "c":
            path.cubicTo(*args)
        elif op == "z":
            path.closeSubpath()
    return path


@register_item
class PdfPathItem(MarkupItem):
    """An exact, recolourable path kept inside a snapshot's source record."""

    TYPE = "pdf_path"
    NAME = "PDF path"

    def __init__(self):
        super().__init__()
        self.commands = []
        self.clips = []
        self.even_odd = False
        self._path = QPainterPath()

    def local_rect(self):
        return self._path.boundingRect().adjusted(-self.style.width, -self.style.width,
                                                 self.style.width, self.style.width)

    def paint_content(self, painter):
        painter.save()
        for commands, even_odd in self.clips:
            painter.setClipPath(path_from(commands, even_odd), Qt.IntersectClip)
        painter.setPen(self.style.pen() if self.style.stroke else Qt.NoPen)
        painter.setBrush(self.style.brush())
        painter.drawPath(self._path)
        painter.restore()

    def serialize(self):
        data = self.base_dict()
        data.update(commands=self.commands, clips=self.clips, even_odd=self.even_odd)
        return data

    def deserialize(self, data):
        self.load_base(data)
        self.commands = data.get("commands", [])
        self.clips = data.get("clips", [])
        self.even_odd = data.get("even_odd", False)
        self._path = path_from(self.commands, self.even_odd)


def _commands(entry, matrix):
    commands, current = [], None

    def point(p):
        p = pymupdf.Point(p) * matrix
        return [float(p.x), float(p.y)]

    for part in entry.get("items", []):
        kind = part[0]
        if kind in ("l", "c"):
            start = point(part[1])
            if current != start:
                commands.append(["m", *start])
            if kind == "l":
                current = point(part[2])
                commands.append(["l", *current])
            else:
                current = point(part[4])
                commands.append(["c", *point(part[2]), *point(part[3]), *current])
        elif kind in ("re", "qu"):
            shape = part[1]
            corners = ([shape.tl, shape.tr, shape.br, shape.bl] if kind == "re"
                       else [shape.ul, shape.ur, shape.lr, shape.ll])
            if kind == "re" and len(part) > 2 and part[2] < 0:
                corners.reverse()
            commands.append(["m", *point(corners[0])])
            commands.extend(["l", *point(p)] for p in corners[1:])
            commands.append(["z"])
            current = None
    if entry.get("closePath"):
        commands.append(["z"])
    return commands


def source_paths(document, page, region):
    """Read every path in the capture region, preserving curves and clips.

    Snapshot extraction is independent of the optional, capped snap geometry
    import. A full-page fill is paper, regardless of its colour.
    """
    data = document.asset(page.pdf_key) if page.pdf_key else None
    if not data or page.pdf_page_index is None:
        return []
    result, contexts = [], []
    with PdfFile.from_bytes(data) as source:
        pdf_page = source.bare_page(int(page.pdf_page_index))
        sx = page.width_pt / pdf_page.rect.width
        sy = page.height_pt / pdf_page.rect.height
        matrix = pdf_page.rotation_matrix * pymupdf.Matrix(sx, sy)
        whole = QRectF(0, 0, page.width_pt, page.height_pt)
        for order, entry in enumerate(pdf_page.get_drawings(extended=True)):
            level = entry.get("level", 0)
            while contexts and contexts[-1][0] >= level:
                contexts.pop()
            kind = entry["type"]
            commands = _commands(entry, matrix)
            if kind == "clip":
                contexts.append((level, (commands, entry.get("even_odd", False)), 1.0))
                continue
            if kind == "group":
                contexts.append((level, None, entry.get("opacity", 1.0)))
                continue
            path = path_from(commands, entry.get("even_odd", False))
            width = float(entry.get("width") or 0.0) * max(sx, sy)
            if not path.boundingRect().adjusted(-width, -width, width, width).intersects(region):
                continue
            fill = _colour_of(entry.get("fill"))
            # Do not mistake a large outlined shape for paper. Only suppress
            # a fill whose actual path covers the sheet, not merely its bounds.
            if fill and path.contains(whole.adjusted(0.5, 0.5, -0.5, -0.5)):
                fill = ""
            stroke = _colour_of(entry.get("color"))
            if not stroke and not fill:
                continue
            item = PdfPathItem()
            opacity = 1.0
            for _, _, group_opacity in contexts:
                opacity *= group_opacity
            item.style = Style(stroke=stroke, fill=fill, width=max(width, 0.01),
                               opacity=float(entry.get("stroke_opacity")
                                             if entry.get("stroke_opacity") is not None else 1.0) * opacity,
                               fill_opacity=float(entry.get("fill_opacity")
                                                  if entry.get("fill_opacity") is not None else 1.0))
            dash = re.search(r"\[([^]]*)\]", str(entry.get("dashes", "")))
            if dash and width:
                item.style.dash_array = tuple(float(n) * max(sx, sy) / width
                                             for n in dash[1].split())
            item.commands, item._path = commands, path
            item.even_odd = entry.get("even_odd", False)
            item.clips = [clip for _, clip, _ in contexts if clip is not None]
            item.setZValue(-1000000 + order)
            result.append(item)
    return result
