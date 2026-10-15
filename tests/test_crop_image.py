"""Revu's Crop Image (the user's choice, 2026-10-15): select an image markup,
drag the part of it to keep."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QRectF
from PySide6.QtGui import QColor, QImage, QPainter

from calcforge.items.media import ImageItem


def _image(window):
    picture = QImage(100, 100, QImage.Format_RGB32)
    picture.fill(QColor("#ffffff"))
    painter = QPainter(picture)
    painter.fillRect(0, 0, 50, 50, QColor("#ff0000"))       # red top-left quarter
    painter.fillRect(50, 50, 50, 50, QColor("#0000ff"))     # blue bottom-right
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    picture.save(buffer, "PNG")
    key = window.document.add_asset(bytes(data), ".png")
    item = ImageItem(key, QRectF(0, 0, 200, 200))
    item.setParentItem(window.scene.frames[0])
    item.setPos(100, 100)
    item.load_from_document(window.document)
    return item


def test_crop_image_keeps_the_dragged_part_and_undo_brings_back_the_rest(window):
    item = _image(window)
    frame = window.scene.frames[0]
    item.setSelected(True)
    # drag over the image's top-left quarter: page (100,100)-(200,200)
    assert window.crop_image_region(frame, QRectF(90, 90, 110, 110))
    image = next(i for i in frame.markups() if isinstance(i, ImageItem))
    assert image.local_rect() == QRectF(0, 0, 100, 100)
    assert image.crop == QRectF(0, 0, 0.5, 0.5)
    assert image.source_rect() == QRectF(0, 0, 50, 50)
    # what is left is the red quarter, filling the box
    shown = QImage(100, 100, QImage.Format_RGB32)
    painter = QPainter(shown)
    window.scene.render(painter, QRectF(0, 0, 100, 100),
                        image.mapRectToScene(QRectF(0, 0, 100, 100)))
    painter.end()
    assert QColor(shown.pixel(50, 50)).name() == "#ff0000"
    # kept in the file
    data = image.serialize()
    again = ImageItem()
    again.deserialize(data)
    assert again.crop == image.crop and again.local_rect() == image.local_rect()
    window.undo_stack.undo()
    back = next(i for i in frame.markups() if isinstance(i, ImageItem))
    assert back.local_rect() == QRectF(0, 0, 200, 200) and not back.is_cropped()


def test_a_second_crop_is_of_what_is_shown(window):
    item = _image(window)
    assert item.crop_to(QRectF(100, 100, 100, 100))            # bottom-right quarter
    assert item.crop_to(QRectF(100, 100, 50, 50))              # its top-left quarter
    assert item.crop == QRectF(0.5, 0.5, 0.25, 0.25)


def test_crop_image_is_a_tool_and_on_the_image_menu(window):
    from calcforge.ui.tools import TOOL_MAP
    assert TOOL_MAP["crop_image"].label == "Crop Image"
    item = _image(window)
    assert not window.crop_image_region(window.scene.frames[0], QRectF(400, 400, 20, 20))
    assert "Crop Image" in window.status_hint.text()
