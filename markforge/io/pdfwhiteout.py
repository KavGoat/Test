"""Remove source artwork geometrically, retaining the surviving vector shapes."""
from __future__ import annotations

import base64
import copy
import re
import xml.etree.ElementTree as ET

import pymupdf
from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPainterPath, QPainterPathStroker, QTransform

from .pdfsnapshot import _svg_path

SVG = '{http://www.w3.org/2000/svg}'
HREF = '{http://www.w3.org/1999/xlink}href'


def _path_data(path):
    """Serialize Qt's boolean result, including surviving cubic curves."""
    out, i = [], 0
    while i < path.elementCount():
        element = path.elementAt(i)
        if element.isMoveTo():
            out.append(f'M{element.x:.8g} {element.y:.8g}')
        elif element.isLineTo():
            out.append(f'L{element.x:.8g} {element.y:.8g}')
        elif element.isCurveTo():
            b, c = path.elementAt(i + 1), path.elementAt(i + 2)
            out.append(f'C{element.x:.8g} {element.y:.8g} {b.x:.8g} {b.y:.8g} {c.x:.8g} {c.y:.8g}')
            i += 2
        i += 1
    return ''.join(out)


def erase_region(pdf_page, box):
    """Build a new page appearance with no painted geometry inside *box*.

    Text appearance becomes font outlines; the caller restores a search layer
    for surviving characters. Other pages, annotations, metadata and the
    application's undo source are managed by the caller.
    """
    root = ET.fromstring(pdf_page.get_svg_image(text_as_path=True))
    definitions = {node.get('id'): node for node in root.iter() if node.get('id')}
    hole = QPainterPath()
    hole.addRect(QRectF(box.x0, box.y0, box.width, box.height))
    style_keys = ('fill', 'stroke', 'fill-rule', 'stroke-width', 'stroke-linecap',
                  'stroke-linejoin', 'stroke-miterlimit', 'stroke-dasharray',
                  'stroke-dashoffset', 'fill-opacity', 'stroke-opacity')

    def visit(node, parent_transform, inherited):
        tag = node.tag.rsplit('}', 1)[-1]
        if tag in ('defs', 'clipPath', 'mask'):
            return
        if tag == 'use':
            ref = definitions.get(node.get(HREF, '').lstrip('#'))
            if ref is None:
                raise ValueError('Whiteout could not resolve a PDF drawing reference')
            attrs = dict(node.attrib)
            attrs.pop(HREF, None)
            node.tag = SVG + 'g'
            node.attrib.clear()
            node.attrib.update(attrs)
            node.append(copy.deepcopy(ref))
            tag = 'g'
        matrix = re.fullmatch(r'matrix\(([^)]+)\)', node.get('transform', ''))
        transform = parent_transform
        if matrix:
            transform = QTransform(*[float(v) for v in re.split(r'[,\s]+', matrix[1].strip())]) * parent_transform
        style = dict(inherited)
        style.update({key: node.get(key) for key in style_keys if key in node.attrib})
        inverse, valid = transform.inverted()
        if not valid:
            return  # A singular transform paints no area.
        local_hole = inverse.map(hole)
        if tag == 'path':
            path = _svg_path(node.get('d', ''))
            if path is None:
                raise ValueError('Whiteout encountered unsupported PDF path geometry')
            path.setFillRule(Qt.OddEvenFill if style.get('fill-rule') == 'evenodd' else Qt.WindingFill)
            pieces = []
            fill = style.get('fill', '#000000')
            if fill != 'none':
                pieces.append((path, fill, style.get('fill-opacity', '1')))
            stroke = style.get('stroke', 'none')
            if stroke != 'none':
                stroker = QPainterPathStroker()
                stroker.setWidth(float(style.get('stroke-width', '1')))
                stroker.setCapStyle({'round': Qt.RoundCap, 'square': Qt.SquareCap}.get(style.get('stroke-linecap'), Qt.FlatCap))
                stroker.setJoinStyle({'round': Qt.RoundJoin, 'bevel': Qt.BevelJoin}.get(style.get('stroke-linejoin'), Qt.MiterJoin))
                stroker.setMiterLimit(float(style.get('stroke-miterlimit', '4')))
                dash = style.get('stroke-dasharray', 'none')
                if dash != 'none' and stroker.width() > 0:
                    stroker.setDashPattern([float(n) / stroker.width() for n in re.split(r'[,\s]+', dash.strip())])
                    stroker.setDashOffset(float(style.get('stroke-dashoffset', '0')) / stroker.width())
                pieces.append((stroker.createStroke(path), stroke, style.get('stroke-opacity', '1')))
            # Keep enclosing transforms/clips/opacity, replacing the actual
            # drawing instructions rather than adding another clipping mask.
            node.tag = SVG + 'g'
            for key in ('d', *style_keys):
                node.attrib.pop(key, None)
            for shape, colour, opacity in pieces:
                remaining = shape.subtracted(local_hole)
                if not remaining.isEmpty():
                    ET.SubElement(node, SVG + 'path', {
                        'd': _path_data(remaining), 'fill': colour, 'stroke': 'none',
                        'fill-rule': 'evenodd' if remaining.fillRule() == Qt.OddEvenFill else 'nonzero',
                        'fill-opacity': opacity})
            return
        if tag == 'image':
            uri = node.get(HREF, '')
            if not uri.startswith('data:image/') or ';base64,' not in uri:
                raise ValueError('Whiteout encountered an unsupported PDF image')
            image = QImage.fromData(base64.b64decode(uri.split(',', 1)[1]))
            if image.isNull():
                raise ValueError('Whiteout could not decode a PDF image')
            image = image.convertToFormat(QImage.Format_ARGB32_Premultiplied)
            image_transform = QTransform()
            image_transform.translate(float(node.get('x', '0')), float(node.get('y', '0')))
            image_transform.scale(float(node.get('width', image.width())) / image.width(),
                                  float(node.get('height', image.height())) / image.height())
            pixel_inverse, valid = (image_transform * transform).inverted()
            if valid:
                painter = QPainter(image)
                painter.setCompositionMode(QPainter.CompositionMode_DestinationOut)
                painter.fillPath(pixel_inverse.map(hole), Qt.black)
                painter.end()
                buffer = QBuffer()
                buffer.open(QIODevice.WriteOnly)
                image.save(buffer, 'PNG')
                node.set(HREF, 'data:image/png;base64,' + base64.b64encode(bytes(buffer.data())).decode())
            return
        for child in list(node):
            visit(child, transform, style)

    visit(root, QTransform(), {})
    # Font outlines and referenced artwork have been expanded and cut. Drop
    # their unused originals, retaining only definitions needed by clips/masks.
    referenced = set()
    for node in root.iter():
        for value in node.attrib.values():
            referenced.update(re.findall(r'url\(#([^)]*)\)', value))
    for defs in root.findall(SVG + 'defs'):
        for child in list(defs):
            if child.get('id') not in referenced:
                defs.remove(child)
    with pymupdf.open(stream=ET.tostring(root), filetype='svg') as svg:
        return svg.convert_to_pdf()


def surviving_text(pdf_page, box):
    """Keep search text only for characters wholly outside the erased region."""
    native_hole = box * pdf_page.derotation_matrix
    kept = []
    for block in pdf_page.get_text('rawdict', flags=pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_PRESERVE_IMAGES)['blocks']:
        for line in block.get('lines', []):
            for span in line.get('spans', []):
                for char in span.get('chars', []):
                    if not pymupdf.Rect(char['bbox']).intersects(native_hole):
                        kept.append((char['origin'], char['c'], span['size'], line.get('dir', (1, 0))))
    return kept


def restore_search_text(pdf_page, characters):
    """Add an invisible search layer behind the exact, visible font outlines."""
    # A writer per text direction preserves rotated labels as well as ordinary
    # horizontal text. Positions remain in the page's unrotated coordinates.
    if not characters:
        return
    font = pymupdf.Font('helv')
    writers = {}
    for origin, text, size, direction in characters:
        if not text or size <= 0:
            continue
        direction = tuple(direction)
        if direction not in writers:
            writers[direction] = pymupdf.TextWriter(pdf_page.rect)
        writer = writers[direction]
        # Undo the line's rotation before applying it to the complete writer.
        matrix = pymupdf.Matrix(direction[0], direction[1], -direction[1], direction[0], 0, 0)
        position = pymupdf.Point(origin) * ~matrix
        writer.append(position, text, font=font, fontsize=size)
    for direction, writer in writers.items():
        matrix = pymupdf.Matrix(direction[0], -direction[1], direction[1], direction[0], 0, 0)
        writer.write_text(pdf_page, render_mode=3, morph=(pymupdf.Point(0, 0), matrix))
