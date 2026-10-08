"""Capture PDF artwork, outlined text and source images without paper fills."""
from __future__ import annotations

import base64
import re
import xml.etree.ElementTree as ET

import pymupdf
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QImage, QPainterPath, QTransform
from PySide6.QtSvg import QSvgRenderer

from ..items.base import MarkupItem, Style, register_item
from .pdfvector import PdfFile, _colour_of

ET.register_namespace("", "http://www.w3.org/2000/svg")
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")


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
        self.fill_alpha = None
        # The PDF's own line ends and corners (0 butt/miter, 1 round, 2
        # square/bevel): a PDF miter that overshoots its limit becomes a bevel,
        # where Qt's plain miter draws a clipped spike — which made a line
        # drawn there and back come out longer than the drawing's.
        self.cap = 0
        self.join = 0
        self.miter_limit = 10.0
        self._path = QPainterPath()

    def local_rect(self):
        return self._path.boundingRect().adjusted(-self.style.width, -self.style.width,
                                                 self.style.width, self.style.width)

    def paint_content(self, painter):
        painter.save()
        for commands, even_odd in self.clips:
            painter.setClipPath(path_from(commands, even_odd), Qt.IntersectClip)
        if self.style.stroke:
            pen = self.style.pen()
            pen.setCapStyle({1: Qt.RoundCap, 2: Qt.SquareCap}.get(self.cap, Qt.FlatCap))
            pen.setJoinStyle({1: Qt.RoundJoin, 2: Qt.BevelJoin}.get(self.join, Qt.SvgMiterJoin))
            pen.setMiterLimit(self.miter_limit)
            painter.setPen(pen)
        else:
            painter.setPen(Qt.NoPen)
        brush = self.style.brush()
        if self.fill_alpha is not None:
            colour = brush.color()
            colour.setAlphaF(max(0.0, min(1.0, self.fill_alpha)))
            brush.setColor(colour)
        painter.setBrush(brush)
        painter.drawPath(self._path)
        painter.restore()

    def serialize(self):
        data = self.base_dict()
        data.update(commands=self.commands, clips=self.clips, even_odd=self.even_odd,
                    fill_alpha=self.fill_alpha, cap=self.cap, join=self.join,
                    miter_limit=self.miter_limit)
        return data

    def deserialize(self, data):
        self.load_base(data)
        self.fill_alpha = data.get("fill_alpha")
        self.commands = data.get("commands", [])
        self.clips = data.get("clips", [])
        self.even_odd = data.get("even_odd", False)
        self.cap = int(data.get("cap", 0) or 0)
        self.join = int(data.get("join", 0) or 0)
        self.miter_limit = float(data.get("miter_limit", 10.0) or 10.0)
        self._path = path_from(self.commands, self.even_odd)


@register_item
class PdfSvgItem(MarkupItem):
    """Full PDF appearance, including outlined fonts and original image pixels."""

    TYPE = "pdf_svg"
    NAME = "PDF content"

    def __init__(self):
        super().__init__()
        self.svg = ""
        self._rect = QRectF()
        self._renderer = None
        self.style = Style(stroke="", fill="", width=0)

    def local_rect(self):
        return QRectF(self._rect)

    def paint_content(self, painter):
        if self._renderer is None:
            self._renderer = QSvgRenderer(QByteArray(self.svg.encode()))
            if not self._renderer.isValid():
                raise ValueError("PDF snapshot appearance could not be decoded")
        # Whatever pen the painter was left holding would otherwise outline
        # every glyph the SVG only fills, turning text bold in a PDF.
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(Qt.NoBrush)
        self._renderer.render(painter, self._rect)
        painter.restore()

    def serialize(self):
        data = self.base_dict()
        data.update(svg=self.svg, rect=[self._rect.x(), self._rect.y(),
                                      self._rect.width(), self._rect.height()])
        return data

    def deserialize(self, data):
        self.load_base(data)
        self.svg = inline_glyphs(data["svg"])
        self._rect = QRectF(*data["rect"])
        self._renderer = None

    def change_colours(self, source, target, tolerance=40):
        from .recolour import _near
        root = ET.fromstring(self.svg)
        changed = 0
        masks = {child for node in root.iter()
                 if node.tag.rsplit("}", 1)[-1] in ("mask", "clipPath")
                 for child in node.iter()}
        for node in root.iter():
            if node in masks:
                continue
            if node.tag.rsplit("}", 1)[-1] in ("use", "path", "text", "stop"):
                fields = ("stop-color",) if node.tag.endswith("stop") else ("fill", "stroke")
                for field in fields:
                    colour = node.get(field, "#000000" if field == "fill" else "none")
                    if colour != "none" and (source is None or _near(colour, source, tolerance)):
                        node.set(field, target.name())
                        changed += 1
        def recolour_images(node, in_mask=False):
            nonlocal changed
            from .recolour import colourise, swap_colour
            tag = node.tag.rsplit("}", 1)[-1]
            in_mask = in_mask or tag in ("mask", "clipPath")
            if tag == "image" and not in_mask:
                key = "{http://www.w3.org/1999/xlink}href"
                uri = node.get(key, "")
                if uri.startswith("data:image/") and ";base64," in uri:
                    before = QImage.fromData(base64.b64decode(uri.split(",", 1)[1]))
                    after = colourise(before, target) if source is None else swap_colour(before, source, target, tolerance)
                    if after != before:
                        buffer = QBuffer()
                        buffer.open(QIODevice.WriteOnly)
                        after.save(buffer, "PNG")
                        node.set(key, "data:image/png;base64," + base64.b64encode(bytes(buffer.data())).decode())
                        changed += 1
            for child in node:
                recolour_images(child, in_mask)
        recolour_images(root)
        if changed:
            self.svg = ET.tostring(root, encoding="unicode")
            self._renderer = None
        return changed


_SVG = "{http://www.w3.org/2000/svg}"
NORMALISED_ATTRIBUTE = "data-calcforge-normalised"
NORMALISED = NORMALISED_ATTRIBUTE + '="2"'
_HREF = "{http://www.w3.org/1999/xlink}href"


def _svg_d(path: QPainterPath) -> str:
    """A path as SVG path data, in absolute coordinates."""
    out = []
    count = path.elementCount()
    index = 0
    while index < count:
        element = path.elementAt(index)
        if element.type == QPainterPath.MoveToElement:
            out.append(f"M{element.x:.4f} {element.y:.4f}")
        elif element.type == QPainterPath.LineToElement:
            out.append(f"L{element.x:.4f} {element.y:.4f}")
        elif element.type == QPainterPath.CurveToElement and index + 2 < count:
            one, two = path.elementAt(index + 1), path.elementAt(index + 2)
            out.append(f"C{element.x:.4f} {element.y:.4f} {one.x:.4f} {one.y:.4f} "
                       f"{two.x:.4f} {two.y:.4f}")
            index += 2
        index += 1
    return "".join(out)


def _matrix_of(node) -> QTransform:
    found = re.fullmatch(r"matrix\(([^)]+)\)", node.get("transform", "").strip())
    if not found:
        return QTransform()
    values = [float(v) for v in re.split(r"[,\s]+", found[1].strip())]
    return QTransform(*values) if len(values) == 6 else QTransform()


def inline_glyphs(svg: str) -> str:
    """Replace each ``<use>`` of a glyph with the glyph's own path, placed.

    MuPDF writes text as glyph outlines a unit high, reused through ``<use>``
    with a scaling transform. Qt's PDF writer keeps too few decimals of those
    tiny coordinates, so in any other viewer the letters of an exported
    snapshot came out as fat black blobs. Written out at their real size,
    in page coordinates, they are the same letters everywhere.
    """
    if NORMALISED in svg[:600]:
        return svg
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return svg
    glyphs = {node.get("id"): node for node in root.iter()
              if node.get("id") and node.tag == _SVG + "path"}
    for parent in list(root.iter()):
        for position, child in enumerate(list(parent)):
            if child.tag != _SVG + "use":
                continue
            glyph = glyphs.get(child.get(_HREF, "").lstrip("#"))
            if glyph is None:
                continue
            outline = _svg_path(glyph.get("d", ""))
            if outline is None:
                continue
            placed = _matrix_of(child).map(outline)
            attributes = {key: value for key, value in glyph.attrib.items()
                          if key not in ("id", "d", "transform")}
            attributes.update({key: value for key, value in child.attrib.items()
                               if key not in (_HREF, "transform", "x", "y",
                                              "width", "height")})
            attributes["d"] = _svg_d(placed)
            parent.remove(child)
            parent.insert(position, ET.Element(_SVG + "path", attributes))
    # A shape the SVG only fills says so outright, twice over. Qt's SVG
    # renderer strokes even a stroke="none" path with a one-unit default pen
    # when writing a PDF — which made every letter of an exported snapshot
    # bold — but it does honour a stroke that cannot be seen.
    for node in root.iter():
        if node.tag not in (_SVG + "path", _SVG + "use"):
            continue
        if node.get("stroke", "none") == "none":
            node.set("stroke", "none")
            node.set("stroke-opacity", "0")
    root.set(NORMALISED_ATTRIBUTE, "2")
    return ET.tostring(root, encoding="unicode")


def _svg_path(value):
    """Read the absolute path operators emitted by MuPDF's SVG device."""
    tokens = re.findall(r"[A-Za-z]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?", value)
    path, i, op = QPainterPath(), 0, None
    sizes = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "Q": 4}
    while i < len(tokens):
        if tokens[i].isalpha():
            op = tokens[i]
            i += 1
        if op == "Z" or op == "z":
            path.closeSubpath()
            op = None
            continue
        if op not in sizes:
            return None  # Unknown geometry must never be mistaken for paper.
        n = sizes[op]
        values = list(map(float, tokens[i:i+n]))
        if len(values) != n:
            return None
        i += n
        if op == "M":
            path.moveTo(*values)
            op = "L"
        elif op == "L": path.lineTo(*values)
        elif op == "H": path.lineTo(values[0], path.currentPosition().y())
        elif op == "V": path.lineTo(path.currentPosition().x(), values[0])
        elif op == "C": path.cubicTo(*values)
        elif op == "Q": path.quadTo(*values)
    return path


def full_appearance(pdf_page, width, height):
    """Preserve PDF paint order, font outlines, image resolution and clipping."""
    root = ET.fromstring(pdf_page.get_svg_image(text_as_path=True))
    whole = QRectF(0, 0, pdf_page.rect.width, pdf_page.rect.height)

    def visit(node, transform=QTransform(), definitions=False, in_mask=False):
        tag = node.tag.rsplit("}", 1)[-1]
        definitions = definitions or tag in ("defs", "clipPath", "mask")
        in_mask = in_mask or tag in ("mask", "clipPath")
        matrix = re.fullmatch(r"matrix\(([^)]+)\)", node.get("transform", ""))
        if matrix:
            values = [float(v) for v in re.split(r"[,\s]+", matrix[1].strip())]
            transform = QTransform(*values) * transform
        if tag == "path" and not definitions and node.get("fill", "black") != "none":
            path = _svg_path(node.get("d", ""))
            if path is not None:
                path.setFillRule(Qt.OddEvenFill if node.get("fill-rule") == "evenodd" else Qt.WindingFill)
                if transform.map(path).contains(whole.adjusted(.5, .5, -.5, -.5)):
                    node.set("fill", "none")
        # White paper embedded in a scan should not cover the destination.
        if tag == "image" and not in_mask:
            key = "{http://www.w3.org/1999/xlink}href"
            uri = node.get(key, "")
            if uri.startswith("data:image/") and ";base64," in uri:
                image = QImage.fromData(base64.b64decode(uri.split(",", 1)[1]))
                if not image.isNull():
                    mask = image.createMaskFromColor(0xffffffff, Qt.MaskOutColor)
                    image.setAlphaChannel(mask)
                    buffer = QBuffer()
                    buffer.open(QIODevice.WriteOnly)
                    image.save(buffer, "PNG")
                    node.set(key, "data:image/png;base64," + base64.b64encode(bytes(buffer.data())).decode())
        for child in node:
            visit(child, transform, definitions, in_mask)
    visit(root)
    empty = {node.get("id") for node in root.iter()
             if node.get("id") and node.tag.endswith("}path") and not node.get("d", "").strip()}
    for parent in root.iter():
        for child in list(parent):
            if (child.get("id") in empty and child.tag.endswith("}path")
                    or child.get("{http://www.w3.org/1999/xlink}href", "").lstrip("#") in empty):
                parent.remove(child)
    item = PdfSvgItem()
    item.svg = inline_glyphs(ET.tostring(root, encoding="unicode"))
    item._rect = QRectF(0, 0, width, height)
    item.setZValue(-1000000)
    return item


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
        if pdf_page.get_text("text").strip() or pdf_page.get_image_info():
            return [full_appearance(pdf_page, page.width_pt, page.height_pt)]
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
            item.fill_alpha = float(entry.get("fill_opacity") if entry.get("fill_opacity") is not None else 1.0) * opacity
            dash = re.search(r"\[([^]]*)\]", str(entry.get("dashes", "")))
            if dash and width:
                item.style.dash_array = tuple(float(n) * max(sx, sy)
                                             for n in dash[1].split())
            item.commands, item._path = commands, path
            item.even_odd = entry.get("even_odd", False)
            caps = entry.get("lineCap") or (0,)
            item.cap = int(caps[0] if isinstance(caps, (tuple, list)) else caps or 0)
            item.join = int(entry.get("lineJoin") or 0)
            item.clips = [clip for _, clip, _ in contexts if clip is not None]
            item.setZValue(-1000000 + order)
            result.append(item)
    return result


def drawn_over(frame, region) -> "PdfSvgItem | None":
    """Everything CalcForge draws over the page inside *region*, as line work.

    What a snapshot takes is what can be seen in the box (2026-09-30): every
    markup whole or in part, typed words, equations, plots, Calculation text,
    the running header and footer, a picture page's picture. It is drawn once,
    exactly as the page draws it, into a PDF, and read back as vector line
    work with the letters as outlines and photos as their own pixels. It is not
    live: it is the drawing as it stood, which is why nothing in it can come
    out different from what was on screen — a measurement away from its
    page's scale, a markup away from the file it was drawn from.

    The page's own PDF content is not in it: that comes from the file itself
    (:func:`source_paths`), sharper than any redrawing of it.
    """
    from PySide6.QtCore import QMarginsF, QSizeF
    from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter

    box = QRectF(region).normalized().intersected(frame.page_rect())
    scene = frame.scene()
    if box.width() < 1 or box.height() < 1 or scene is None:
        return None
    page = frame.page
    on_a_pdf = bool(page.pdf_key and page.pdf_page_index is not None)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    writer = QPdfWriter(buffer)
    writer.setResolution(96)
    writer.setPageLayout(QPageLayout(QPageSize(QSizeF(box.width(), box.height()),
                                               QPageSize.Point),
                                     QPageLayout.Portrait, QMarginsF(0, 0, 0, 0)))
    painter = QPainter(writer)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    previous = frame.print_mode, frame._pdf_overlay
    hidden, chrome, handles, cached = [], [], [], []
    try:
        frame.print_mode = True
        frame._pdf_overlay = on_a_pdf          # the file's own drawing comes from the file
        for item in frame.markups():
            if hasattr(item, "set_chrome") and item.show_chrome:
                chrome.append(item)
                item.set_chrome(False)
            if item._handles_visible:
                handles.append(item)
                item._handles_visible = False
            if item.cacheMode() != item.CacheMode.NoCache:
                cached.append((item, item.cacheMode()))
                item.setCacheMode(item.CacheMode.NoCache)
            # line work read out of the PDF duplicates the file's own drawing
            if on_a_pdf and item.from_drawing and item.isVisible():
                hidden.append(item)
                item.setVisible(False)
        source = frame.mapRectToScene(box)
        target = QRectF(0, 0, writer.width(), writer.height())
        from ..ui.scene import only_this_page
        frame.layer.suspend()                 # the other pages are not drawn
        with only_this_page(scene, frame):
            scene.render(painter, target, source, Qt.IgnoreAspectRatio)
    finally:
        painter.end()
        buffer.close()
        frame.print_mode, frame._pdf_overlay = previous
        for item in hidden:
            item.setVisible(True)
        for item in chrome:
            item.set_chrome(True)
        for item in handles:
            item._handles_visible = True
            item.update()
        for item, mode in cached:
            item.setCacheMode(mode)
    try:
        with pymupdf.open("pdf", bytes(data)) as drawn:
            if not drawn.page_count:
                return None
            sheet = drawn[0]
            if not sheet.get_drawings() and not sheet.get_text("text").strip() \
                    and not sheet.get_image_info():
                return None                    # nothing drawn over the page here
            svg = sheet.get_svg_image(text_as_path=True)
    except Exception:                                  # noqa: BLE001
        return None
    item = PdfSvgItem()
    item.svg = inline_glyphs(svg)
    item._rect = QRectF(0, 0, box.width(), box.height())
    item.setPos(box.topLeft())
    return item
