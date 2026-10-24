"""An Excel workbook's pictures, read from its drawing parts.

openpyxl keeps only the pictures Pillow can open, and drops the rest
without a word: a company logo kept as a Windows metafile (WMF or EMF) went
missing, and the count of what was left out said nothing (the user,
2026-10-24: "photos etc did not work", 200PFC_WP30NC.xlsx). Here every
picture on a worksheet's drawing is read from the file itself — where
Excel anchors it (a cell, two cells, or a place on the sheet), inside a
group or not, cropped or not — with the bytes of the picture it shows.

    drawing_pictures(path) -> {sheet name: [picture, …]}

each picture {"data", "suffix", "anchor", "crop", "name", "place"}, the
anchor with ``_from`` (col, colOff, row, rowOff in EMU), ``to`` and ``ext``
as openpyxl gives them, or ``pos`` for one placed on the sheet; "place" its
part of a group's box. placed_pictures() gives each as CalcForge shows it:
at its cell, at its size, cropped, a metafile drawn (sheet/metafile.py).
"""
from __future__ import annotations

import posixpath
import zipfile
from types import SimpleNamespace
from xml.etree import ElementTree as ET

_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}
_R = "{%s}" % _NS["r"]
_SUFFIX = {"jpg": "jpeg", "jpe": "jpeg", "tif": "tiff"}


def _rels(z: zipfile.ZipFile, part: str) -> dict:
    """The relationships of *part*: id -> target path in the package."""
    folder, name = posixpath.split(part)
    path = posixpath.join(folder, "_rels", name + ".rels")
    try:
        root = ET.fromstring(z.read(path))
    except (KeyError, ET.ParseError):
        return {}
    out = {}
    for rel in root.findall("rel:Relationship", _NS):
        target = rel.get("Target", "")
        if rel.get("TargetMode") == "External":
            continue
        out[rel.get("Id")] = posixpath.normpath(
            target.lstrip("/") if target.startswith("/") else posixpath.join(folder, target))
    return out


def _marker(node) -> SimpleNamespace:
    def num(tag):
        found = node.find(f"xdr:{tag}", _NS)
        return int(found.text) if found is not None and found.text else 0
    return SimpleNamespace(col=num("col"), colOff=num("colOff"), row=num("row"),
                           rowOff=num("rowOff"))


def _size(node):
    if node is None:
        return None
    return SimpleNamespace(width=int(node.get("cx", 0)), height=int(node.get("cy", 0)))


def _anchor_of(node) -> SimpleNamespace:
    tag = node.tag.rsplit("}", 1)[1]
    start = node.find("xdr:from", _NS)
    end = node.find("xdr:to", _NS)
    pos = node.find("xdr:pos", _NS)
    return SimpleNamespace(
        kind=tag,
        _from=_marker(start) if start is not None else None,
        to=_marker(end) if end is not None and tag == "twoCellAnchor" else None,
        ext=_size(node.find("xdr:ext", _NS)),
        pos=(int(pos.get("x", 0)), int(pos.get("y", 0))) if pos is not None else None)


def _xfrm(node):
    """(x, y, cx, cy) of a shape's a:xfrm, in EMU, or None."""
    xfrm = node.find(".//a:xfrm", _NS) if node is not None else None
    if xfrm is None:
        return None
    off, ext = xfrm.find("a:off", _NS), xfrm.find("a:ext", _NS)
    if off is None or ext is None:
        return None
    return (int(off.get("x", 0)), int(off.get("y", 0)), int(ext.get("cx", 0)),
            int(ext.get("cy", 0)))


def _pictures_in(node, rels, z, anchor, out, group=None):
    """The pictures in *node* (an anchor's content, or a group's), each with
    its place in the anchor's box as fractions when inside a group."""
    for child in node:
        tag = child.tag.rsplit("}", 1)[1]
        if tag == "grpSp":
            props = child.find("xdr:grpSpPr/a:xfrm", _NS)
            box = None
            if props is not None:
                off, ext = props.find("a:off", _NS), props.find("a:ext", _NS)
                ch_off, ch_ext = props.find("a:chOff", _NS), props.find("a:chExt", _NS)
                if None not in (off, ext, ch_off, ch_ext):
                    box = tuple(int(v) for v in (
                        off.get("x", 0), off.get("y", 0), ext.get("cx", 0), ext.get("cy", 0),
                        ch_off.get("x", 0), ch_off.get("y", 0), ch_ext.get("cx", 0),
                        ch_ext.get("cy", 0)))
            _pictures_in(child, rels, z, anchor, out, group=(group or []) + [box])
        elif tag == "pic":
            nv = child.find("xdr:nvPicPr/xdr:cNvPr", _NS)
            if nv is not None and nv.get("hidden") in ("1", "true"):
                continue
            blip = child.find("xdr:blipFill/a:blip", _NS)
            target = rels.get(blip.get(_R + "embed")) if blip is not None else None
            if not target:
                continue
            try:
                data = z.read(target)
            except KeyError:
                continue
            suffix = posixpath.splitext(target)[1].lstrip(".").lower()
            crop = None
            rect = child.find("xdr:blipFill/a:srcRect", _NS)
            if rect is not None and any(rect.get(k) for k in "ltrb"):
                crop = tuple(int(rect.get(k, 0) or 0) / 100000.0 for k in "ltrb")
            out.append({"data": data, "suffix": _SUFFIX.get(suffix, suffix), "anchor": anchor,
                        "crop": crop, "name": nv.get("name", "") if nv is not None else "",
                        "place": _in_group(_xfrm(child.find("xdr:spPr", _NS)), group)})


def _in_group(rect, groups):
    """Where a shape inside groups sits in the outermost group's box, as
    fractions (x, y, w, h); None outside any group."""
    if not groups or rect is None:
        return None
    x, y, w, h = rect
    for box in reversed(groups):
        if box is None or not box[6] or not box[7]:
            return None
        ox, oy, cx, cy, chx, chy, chw, chh = box
        x, y = ox + (x - chx) * cx / chw, oy + (y - chy) * cy / chh
        w, h = w * cx / chw, h * cy / chh
    ox, oy, cx, cy = groups[0][:4]
    if not cx or not cy:
        return None
    return ((x - ox) / cx, (y - oy) / cy, w / cx, h / cy)


def drawing_pictures(path: str) -> dict:
    """{sheet name: [picture, …]} for every worksheet of the workbook at *path*."""
    out: dict = {}
    try:
        z = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile):
        return out
    with z:
        try:
            book = ET.fromstring(z.read("xl/workbook.xml"))
        except (KeyError, ET.ParseError):
            return out
        book_rels = _rels(z, "xl/workbook.xml")
        for sheet in book.findall("main:sheets/main:sheet", _NS):
            part = book_rels.get(sheet.get(_R + "id"))
            if not part:
                continue
            try:
                ws = ET.fromstring(z.read(part))
            except (KeyError, ET.ParseError):
                continue
            sheet_rels = _rels(z, part)
            found = []
            for drawing in ws.findall("main:drawing", _NS):
                target = sheet_rels.get(drawing.get(_R + "id"))
                if not target:
                    continue
                try:
                    root = ET.fromstring(z.read(target))
                except (KeyError, ET.ParseError):
                    continue
                rels = _rels(z, target)
                for anchor in root:
                    tag = anchor.tag.rsplit("}", 1)[1]
                    if tag in ("twoCellAnchor", "oneCellAnchor", "absoluteAnchor"):
                        _pictures_in(anchor, rels, z, _anchor_of(anchor), found)
            if found:
                out[sheet.get("name")] = found
    return out


# -- as CalcForge shows them -------------------------------------------------------------------
def placed_pictures(title: str, drawn: list, data: dict, left_out: list) -> list:
    """[{"data", "suffix", "anchor": [row, col, dx, dy], "w", "h"}] for the
    pictures *drawn* on worksheet *title* (sizes in points), each at the
    cell Excel anchors it to, cropped as Excel shows it, a metafile drawn as
    a picture; those that can't be shown are counted in *left_out*."""
    from .xlsxcharts import EMU_PER_PT, _measures, _placed
    col_at, row_at = _measures(data)
    out, skipped = [], 0
    for found in drawn:
        anchor = found["anchor"]
        if anchor._from is None and anchor.pos is not None:
            anchor = _at_cell(anchor, col_at, row_at)
        ext = anchor.ext
        size = (ext.width / EMU_PER_PT, ext.height / EMU_PER_PT) if ext is not None \
            and ext.width and ext.height else (72.0, 72.0)
        placed = _placed(anchor, col_at, row_at, size)
        if placed is None:
            skipped += 1
            continue
        (row, col, dx, dy), w, h = placed
        if found.get("place"):
            # one picture of a group: its part of the group's box
            x, y, fw, fh = found["place"]
            dx, dy, w, h = dx + x * w, dy + y * h, fw * w, fh * h
        if w <= 0 or h <= 0:
            skipped += 1
            continue
        blob, suffix = _shown(found["data"], found["suffix"], found.get("crop"), w, h)
        if blob is None:
            skipped += 1
            continue
        out.append({"data": blob, "suffix": suffix, "anchor": [row, col, dx, dy],
                    "w": max(4.0, w), "h": max(4.0, h)})
    if skipped:
        left_out.append(f"{skipped} picture{'s' * (skipped > 1)} on \u201c{title}\u201d")
    return out


def _at_cell(anchor, col_at, row_at) -> SimpleNamespace:
    """A picture placed on the sheet (absoluteAnchor) as one held to the
    cell under its top left corner."""
    from .xlsxcharts import EMU_PER_PT
    x, y = anchor.pos[0] / EMU_PER_PT, anchor.pos[1] / EMU_PER_PT

    def cell(at, edge):
        k = 0
        while k < 16383 and at(k + 1) <= edge:
            k += 1
        return k
    col, row = cell(col_at, x), cell(row_at, y)
    start = SimpleNamespace(col=col, colOff=round((x - col_at(col)) * EMU_PER_PT),
                            row=row, rowOff=round((y - row_at(row)) * EMU_PER_PT))
    return SimpleNamespace(kind=anchor.kind, _from=start, to=None, ext=anchor.ext, pos=None)


def _shown(data: bytes, suffix: str, crop, w: float, h: float) -> tuple:
    """(bytes, suffix) of a picture as shown at *w* × *h* points: as it is
    when Qt reads it and it isn't cropped, else drawn (a metafile), cropped,
    as PNG; (None, None) when it can't be read."""
    from PySide6.QtGui import QImage

    from . import metafile
    left, top, right, bottom = crop or (0.0, 0.0, 0.0, 0.0)
    kept_w, kept_h = max(0.01, 1.0 - left - right), max(0.01, 1.0 - top - bottom)
    if metafile.kind_of(data) or suffix in ("wmf", "emf"):
        # drawn at the size it is shown (the whole of it, when cropped),
        # sharp when printed: up to four pixels a point
        full_w, full_h = w / kept_w, h / kept_h
        scale = max(1.0, min(4.0, 4000.0 / max(full_w, full_h, 1.0)))
        image = metafile.picture(data, full_w, full_h, scale)
    else:
        image = QImage.fromData(data)
        if not image.isNull() and crop is None:
            return data, suffix
    if image is None or image.isNull():
        return None, None
    if crop is not None:
        width, height = image.width(), image.height()
        x, y = round(left * width), round(top * height)
        image = image.copy(x, y, max(1, round(kept_w * width)), max(1, round(kept_h * height)))
    return metafile.encoded(image), "png"
