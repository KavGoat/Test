"""Every picture of an Excel workbook comes across (the user, 2026-10-24:
"i imported that one but photos etc did not work", 200PFC_WP30NC.xlsx).

openpyxl keeps only the pictures Pillow opens and drops the rest without a
word: that workbook's logos are Windows metafiles. Its pictures are read
here from the drawing parts themselves (sheet/xlsxpictures.py) — anchored
at two cells, at one cell with a size, or at a place on the sheet; inside a
group; cropped — and a metafile (WMF or EMF) is drawn as a picture
(sheet/metafile.py). The workbooks here are made in the test, with a
metafile of known shapes, so each can be checked by its pixels."""
from __future__ import annotations

import struct
import zipfile

import pytest
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QColor, QImage

openpyxl = pytest.importorskip("openpyxl")

from calcforge.sheet import metafile  # noqa: E402
from calcforge.sheet.xlsx import read_workbook  # noqa: E402
from calcforge.sheet.xlsxpictures import drawing_pictures  # noqa: E402

RED, BLUE = 0x000000FF, 0x00FF0000          # COLORREF is 0x00BBGGRR


def wmf(fill=RED, placeable=True) -> bytes:
    """A metafile 1440 units an inch, 1 in × 0.5 in: a rectangle filled
    *fill* over its left half, its window set (extent before origin, as
    Office writes them)."""
    records = []

    def record(function, *words):
        body = b"".join(struct.pack("<h", w) if isinstance(w, int) and -32768 <= w < 32768
                        else w for w in words)
        records.append(struct.pack("<IH", 3 + len(body) // 2, function) + body)
    record(0x020C, 720, 1440)                              # SetWindowExt: h, w
    record(0x020B, 0, 0)                                   # SetWindowOrg: y, x
    records.append(struct.pack("<IHHIH", 7, 0x02FC, 0, fill, 0))   # CreateBrushIndirect
    record(0x012D, 0)                                      # SelectObject(brush)
    records.append(struct.pack("<IHHhhI", 8, 0x02FA, 5, 0, 0, 0))  # CreatePenIndirect(PS_NULL)
    record(0x012D, 1)                                      # SelectObject(pen)
    record(0x041B, 720, 720, 0, 0)                         # Rectangle: bottom, right, top, left
    records.append(struct.pack("<IH", 3, 0))               # EOF
    body = b"".join(records)
    header = struct.pack("<HHHIHIH", 1, 9, 0x0300, (18 + len(body)) // 2, 1, 7, 0)
    out = header + body
    if placeable:
        head = struct.pack("<IHhhhhHI", metafile.WMF_PLACEABLE, 0, 0, 0, 1440, 720, 1440, 0)
        checksum = 0
        for (word,) in struct.iter_unpack("<H", head):
            checksum ^= word
        out = head + struct.pack("<H", checksum) + out
    return out


def emf(fill=BLUE) -> bytes:
    """An EMF of a 100 × 50 device unit frame (26.46 × 13.23 mm at 96 dpi)
    filled *fill* over its right half."""
    recs = []
    recs.append(struct.pack("<IIIII", 39, 24, 1, 0, fill) + struct.pack("<I", 0))  # CreateBrush
    recs.append(struct.pack("<III", 37, 12, 1))                       # SelectObject(1)
    recs.append(struct.pack("<III", 37, 12, 0x80000008))               # NULL_PEN
    recs.append(struct.pack("<IIiiii", 43, 24, 50, 0, 100, 50))        # Rectangle
    recs.append(struct.pack("<IIIII", 14, 20, 0, 0, 20))               # EOF
    body = b"".join(recs)
    size = 88 + len(body)
    header = struct.pack("<II", 1, 88)
    header += struct.pack("<iiii", 0, 0, 100, 50)                      # bounds
    header += struct.pack("<iiii", 0, 0, 2646, 1323)                  # frame, 0.01 mm
    header += struct.pack("<IIIIHH", metafile.EMF_SIGNATURE, 0x10000, size, 6, 2, 0)
    header += struct.pack("<III", 0, 0, 0)                             # description, palette
    header += struct.pack("<iiii", 96 * 10, 96 * 10, 254, 254)         # device px, mm
    assert len(header) == 88
    return header + body


def png(colour="#20a020", w=40, h=20) -> bytes:
    image = QImage(w, h, QImage.Format_ARGB32)
    image.fill(QColor(colour))
    for x in range(w // 2):
        for y in range(h):
            image.setPixelColor(x, y, QColor("#ffff00"))    # yellow left half
    held = QByteArray()
    buffer = QBuffer(held)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(held)


_DRAWING = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
 xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
 <xdr:twoCellAnchor>
  <xdr:from><xdr:col>1</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>1</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>
  <xdr:to><xdr:col>3</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>3</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to>
  <xdr:pic><xdr:nvPicPr><xdr:cNvPr id="2" name="Logo"/><xdr:cNvPicPr/></xdr:nvPicPr>
   <xdr:blipFill><a:blip r:embed="rId1"/></xdr:blipFill>
   <xdr:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="1" cy="1"/></a:xfrm></xdr:spPr></xdr:pic>
  <xdr:clientData/>
 </xdr:twoCellAnchor>
 <xdr:oneCellAnchor>
  <xdr:from><xdr:col>5</xdr:col><xdr:colOff>12700</xdr:colOff><xdr:row>0</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>
  <xdr:ext cx="1270000" cy="635000"/>
  <xdr:grpSp><xdr:nvGrpSpPr><xdr:cNvPr id="3" name="Group"/><xdr:cNvGrpSpPr/></xdr:nvGrpSpPr>
   <xdr:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="1270000" cy="635000"/>
    <a:chOff x="0" y="0"/><a:chExt cx="200" cy="100"/></a:xfrm></xdr:grpSpPr>
   <xdr:pic><xdr:nvPicPr><xdr:cNvPr id="4" name="Mark"/><xdr:cNvPicPr/></xdr:nvPicPr>
    <xdr:blipFill><a:blip r:embed="rId2"/></xdr:blipFill>
    <xdr:spPr><a:xfrm><a:off x="100" y="0"/><a:ext cx="100" cy="100"/></a:xfrm></xdr:spPr></xdr:pic>
  </xdr:grpSp>
  <xdr:clientData/>
 </xdr:oneCellAnchor>
 <xdr:absoluteAnchor>
  <xdr:pos x="0" y="1905000"/><xdr:ext cx="508000" cy="254000"/>
  <xdr:pic><xdr:nvPicPr><xdr:cNvPr id="5" name="Photo"/><xdr:cNvPicPr/></xdr:nvPicPr>
   <xdr:blipFill><a:blip r:embed="rId3"/><a:srcRect l="50000"/></xdr:blipFill>
   <xdr:spPr/></xdr:pic>
  <xdr:clientData/>
 </xdr:absoluteAnchor>
</xdr:wsDr>"""

_DRAWING_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image1.wmf"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image2.emf"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image3.png"/>
</Relationships>"""


def with_pictures(path) -> str:
    """A workbook of one sheet whose drawing holds a WMF logo at B2:D4, an
    EMF in a group at F1 (its right half), and a PNG placed on the sheet,
    cropped to its right half."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cover"
    ws["A1"] = "Job"
    wb.save(path)
    with zipfile.ZipFile(path) as z:
        parts = {name: z.read(name) for name in z.namelist()}
    sheet = parts["xl/worksheets/sheet1.xml"].decode()
    sheet = sheet.replace("</worksheet>", '<drawing r:id="rIdD"/></worksheet>')
    if 'xmlns:r=' not in sheet.split(">", 2)[1]:
        sheet = sheet.replace("<worksheet ", '<worksheet xmlns:r="http://schemas.openxmlformats.org/'
                              'officeDocument/2006/relationships" ', 1)
    parts["xl/worksheets/sheet1.xml"] = sheet.encode()
    parts["xl/worksheets/_rels/sheet1.xml.rels"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rIdD" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships/drawing" Target="../drawings/drawing1.xml"/></Relationships>').encode()
    parts["xl/drawings/drawing1.xml"] = _DRAWING.encode()
    parts["xl/drawings/_rels/drawing1.xml.rels"] = _DRAWING_RELS.encode()
    parts["xl/media/image1.wmf"] = wmf()
    parts["xl/media/image2.emf"] = emf()
    parts["xl/media/image3.png"] = png()
    types = parts["[Content_Types].xml"].decode().replace(
        "</Types>",
        '<Default Extension="wmf" ContentType="image/x-wmf"/>'
        '<Default Extension="emf" ContentType="image/x-emf"/>'
        '<Default Extension="png" ContentType="image/png"/>'
        '<Override PartName="/xl/drawings/drawing1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/></Types>')
    parts["[Content_Types].xml"] = types.encode()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(name, data)
    return path


def image_of(found) -> QImage:
    image = QImage.fromData(found["data"])
    assert not image.isNull()
    return image


def colour_at(image, fx, fy) -> QColor:
    return image.pixelColor(int(fx * (image.width() - 1)), int(fy * (image.height() - 1)))


def test_every_picture_of_the_drawing_is_found(tmp_path, qapp):
    path = with_pictures(str(tmp_path / "pictures.xlsx"))
    found = drawing_pictures(path)["Cover"]
    assert [p["name"] for p in found] == ["Logo", "Mark", "Photo"]
    assert [p["suffix"] for p in found] == ["wmf", "emf", "png"]
    assert found[1]["place"] == pytest.approx((0.5, 0.0, 0.5, 1.0)), "its half of the group"
    assert found[2]["anchor"].pos == (0, 1905000) and found[2]["crop"] == (0.5, 0, 0, 0)


def test_they_come_in_placed_drawn_and_cropped(tmp_path, qapp):
    imported = read_workbook(with_pictures(str(tmp_path / "pictures.xlsx")))
    (sheet,) = imported.sheets
    assert not [t for t in imported.left_out if "picture" in t], imported.left_out
    logo, mark, photo = sheet.pictures
    # the WMF logo at B2, two columns and two rows: drawn, its left half red
    assert logo["anchor"][:2] == [1, 1] and logo["suffix"] == "png"
    assert logo["w"] == pytest.approx(96.0) and logo["h"] == pytest.approx(30.0)
    image = image_of(logo)
    assert colour_at(image, 0.25, 0.5).red() > 200 and colour_at(image, 0.25, 0.5).blue() < 60
    assert colour_at(image, 0.75, 0.5).alpha() == 0, "nothing drawn on its right half"
    # the EMF: the right half of its group, 1 pt in from F1; blue on its right
    assert mark["anchor"][:2] == [0, 5]
    assert mark["anchor"][2] == pytest.approx(1.0 + 50.0) and mark["w"] == pytest.approx(50.0)
    image = image_of(mark)
    assert colour_at(image, 0.75, 0.5).blue() > 200 and colour_at(image, 0.25, 0.5).alpha() == 0
    # the photo placed 150 pt down the sheet: row 11 (15 pt rows), cropped to green
    assert photo["anchor"][:2] == [10, 0] and photo["anchor"][3] == pytest.approx(0.0)
    image = image_of(photo)
    assert colour_at(image, 0.1, 0.5).green() > 120 and colour_at(image, 0.1, 0.5).red() < 80


def test_a_metafile_is_drawn_whichever_way_its_window_is_set():
    for data in (wmf(), wmf(placeable=False)):
        image = metafile.picture(data, 72, 36, 2)
        assert image is not None and (image.width(), image.height()) == (144, 72)
        assert colour_at(image, 0.2, 0.5).red() > 200
        assert colour_at(image, 0.8, 0.5).alpha() == 0
    assert metafile.kind_of(emf()) == "emf" and metafile.kind_of(png()) == ""
    assert metafile.picture(b"not a picture") is None


def test_a_picture_that_cant_be_read_is_said(tmp_path, qapp):
    path = with_pictures(str(tmp_path / "pictures.xlsx"))
    with zipfile.ZipFile(path) as z:
        parts = {name: z.read(name) for name in z.namelist()}
    parts["xl/media/image3.png"] = b"\x89PNG broken"
    with zipfile.ZipFile(path, "w") as z:
        for name, data in parts.items():
            z.writestr(name, data)
    imported = read_workbook(path)
    assert len(imported.sheets[0].pictures) == 2
    assert "1 picture on “Cover”" in imported.left_out
