"""Bluebeam's Color Processing (io/colorproc.py): the colours a PDF page sets
are changed where it sets them, so the page stays vector line work; images
change with Process Images; Mask Images makes a colour transparent."""
from __future__ import annotations

import pymupdf

from calcforge.io import colorproc
from calcforge.io.colorproc import Process


def a_page() -> bytes:
    pdf = pymupdf.open()
    page = pdf.new_page(width=200, height=100)
    # black line (the default colour, never set), a red box, a CMYK blue box
    content = (b"2 w 10 10 m 190 10 l S\n"
               b"1 0 0 rg 20 30 40 40 re f\n"
               b"1 1 0 0 k 80 30 40 40 re f\n"
               b"BT /Helv 10 Tf 140 50 Td (Hi) Tj ET\n")
    xref = pdf.get_new_xref()
    pdf.update_object(xref, "<<>>")
    pdf.update_stream(xref, content)
    page.set_contents(xref)
    page.insert_font(fontname="helv", fontbuffer=None) if False else None
    # an image: a 20×20 white square with a green middle
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), False)
    pix.clear_with(255)
    pix.set_rect(pymupdf.IRect(5, 5, 15, 15), (0, 200, 0))
    page.insert_image(pymupdf.Rect(150, 75, 170, 95), pixmap=pix)
    data = pdf.tobytes()
    pdf.close()
    return data


def colour_at(data: bytes, x: float, y: float):
    doc = pymupdf.open(stream=data, filetype="pdf")
    pix = doc[0].get_pixmap(dpi=144, alpha=False)
    s = pix.pixel(int(x * 2), int(y * 2))
    doc.close()
    return s


LINE, RED, BLUE, PICTURE = (100, 90), (40, 50), (100, 50), (160, 85)   # raster: y down


def test_modify_colors_changes_vectors_only_and_keeps_them_vectors():
    data = a_page()
    assert colour_at(data, *RED)[0] > 200
    out = colorproc.process_pdf(data, [0], Process(colorproc.MODIFY,
                                                    pairs=[("#ff0000", "#00ff00"),
                                                           ("#000000", "#0000ff")]))
    assert colour_at(out, *RED) == (0, 255, 0)
    assert colour_at(out, *LINE)[2] > 200 and colour_at(out, *LINE)[0] < 60, "black, never set, too"
    assert colour_at(out, *PICTURE)[1] > 150, "pictures are left alone by Modify Colors"
    doc = pymupdf.open(stream=out, filetype="pdf")
    assert doc[0].get_drawings(), "still vector line work"
    doc.close()


def test_modify_to_no_color_leaves_the_shape_unpainted():
    out = colorproc.process_pdf(a_page(), [0], Process(pairs=[("#ff0000", None)]))
    assert colour_at(out, *RED) == (255, 255, 255)
    assert colour_at(out, *BLUE)[2] > 200, "the others painted as before"


def test_grayscale_black_and_white_and_colorize():
    data = a_page()
    grey = colorproc.process_pdf(data, [0], Process(colorproc.GRAYSCALE))
    r, g, b = colour_at(grey, *RED)
    assert r == g == b and 60 < r < 100                    # red's luminance
    assert colour_at(grey, *PICTURE)[1] > 150, "images only with Process Images"
    grey_too = colorproc.process_pdf(data, [0], Process(colorproc.GRAYSCALE, images=True))
    r, g, b = colour_at(grey_too, *PICTURE)
    assert r == g == b
    bw = colorproc.process_pdf(data, [0], Process(colorproc.BLACK_WHITE))
    assert colour_at(bw, *RED) == (0, 0, 0) and colour_at(bw, *BLUE) == (0, 0, 0)
    single = colorproc.process_pdf(data, [0], Process(colorproc.COLORIZE, select="#2f9e44",
                                                      scale=False))
    for spot in (RED, BLUE):
        got = colour_at(single, *spot)
        assert all(abs(a - b) <= 2 for a, b in zip(got, (0x2f, 0x9e, 0x44)))


def test_luminosity_saturation_hue_and_mask_images():
    data = a_page()
    hue = colorproc.process_pdf(data, [0], Process(colorproc.LSH, hue=120))
    r, g, b = colour_at(hue, *RED)
    assert g > 200 and r < 60, "red turned a third of the way round: green"
    masked = colorproc.process_pdf(data, [0], Process(colorproc.MASK, mask="#ffffff", tolerance=5))
    # the image's white is gone (the page shows through), its green stays
    doc = pymupdf.open(stream=masked, filetype="pdf")
    assert any(info[1] for info in doc[0].get_images(full=True)), "a soft mask now"
    doc.close()
    assert colour_at(masked, *RED)[0] > 200, "vectors untouched by Mask Images"


def test_the_colours_a_page_sets_are_listed():
    found = colorproc.colours_in_pdf(a_page(), 0)
    assert {"#000000", "#ff0000", "#0000ff"} <= set(found)


def test_photos_colorize_and_mask():
    from PySide6.QtGui import QColor, QImage
    image = QImage(4, 1, QImage.Format_RGB32)
    for x, c in enumerate(("#ffffff", "#000000", "#ff0000", "#808080")):
        image.setPixelColor(x, 0, QColor(c))
    out = colorproc.process_qimage(image, Process(colorproc.COLORIZE, select="#000080",
                                                  to="#ffffff"))
    assert out.pixelColor(0, 0).name() == "#ffffff" and out.pixelColor(1, 0).name() == "#000080"
    masked = colorproc.process_qimage(image, Process(colorproc.MASK, mask="#ffffff"))
    assert masked.pixelColor(0, 0).alpha() == 0 and masked.pixelColor(1, 0).alpha() == 255


def test_color_processing_in_the_window_changes_the_pages_pdf_and_undoes(window, tmp_path):
    """Page ▸ Color Processing: the page's own PDF, processed (still vectors,
    still exported as itself); Modify Colors lists the page's colours and is
    for the current page only; one undo step puts it back."""
    from calcforge.io import pdfio
    from calcforge.io.colorproc import GRAYSCALE, MODIFY
    from calcforge.ui import colorprocess
    path = tmp_path / "set.pdf"
    path.write_bytes(a_page())
    pdfio.import_pages(window.document, str(path), [0], at=0)
    window.rebuild_scenes()
    window.interactive_prompts = False
    page = window.document.pages[0]
    before = page.pdf_key
    window.color_processing(0)
    dialog = window._last_color_dialog
    assert {"#000000", "#ff0000"} <= set(dialog.colours)
    assert dialog.kind.currentData() == MODIFY and not dialog.all_pages.isEnabled()
    dialog.pairs[0][1].setCurrentIndex(dialog.pairs[0][1].findData("#ff0000"))
    dialog.pairs[0][2].set("#00ff00")
    assert colorprocess.finish_pages(window, dialog) == 1
    assert page.pdf_key != before
    assert colour_at(window.document.asset(page.pdf_key), *RED) == (0, 255, 0)
    window.undo_stack.undo()
    assert window.document.pages[0].pdf_key == before
    # Custom pages, Grayscale
    window.color_processing(0)
    dialog = window._last_color_dialog
    dialog.kind.setCurrentIndex(dialog.kind.findData(GRAYSCALE))
    dialog.custom_pages.setChecked(True)
    dialog.custom_text.setText("1")
    assert dialog.page_indexes(1) == [0]
    assert colorprocess.finish_pages(window, dialog) == 1
    r, g, b = colour_at(window.document.asset(window.document.pages[0].pdf_key), *RED)
    assert r == g == b


def test_bluebeams_page_ranges():
    from calcforge.ui.colorprocess import parse_pages
    assert parse_pages("1-3, 5, 9", 10) == [0, 1, 2, 4, 8]
    assert parse_pages("2-1", 10) is None and parse_pages("12", 10) is None
    assert parse_pages("x", 10) is None


def test_a_photo_has_colorize_and_mask_only(window, tmp_path):
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QColor, QImage
    from calcforge.io.colorproc import MASK
    from calcforge.items.media import ImageItem
    from calcforge.ui import colorprocess
    image = QImage(10, 10, QImage.Format_RGB32)
    image.fill(QColor("#ffffff"))
    path = tmp_path / "photo.png"
    image.save(str(path))
    key = window.document.add_asset(path.read_bytes(), "png")
    photo = ImageItem(key, QRectF(0, 0, 50, 50))
    window.document.pages[0].frame.add_markup(photo, QPointF(40, 40))
    photo.load_from_document(window.document)
    window.interactive_prompts = False
    window.change_colors(photo)
    dialog = window._last_color_dialog
    assert [dialog.kind.itemData(i) for i in range(dialog.kind.count())] == ["colorize", "mask"]
    dialog.kind.setCurrentIndex(1)
    assert dialog.process().kind == MASK
    assert colorprocess.finish_item(window, photo, dialog.process())
    done = QImage()
    done.loadFromData(window.document.asset(photo.asset_key))
    assert done.pixelColor(5, 5).alpha() == 0, "its white masked"


def test_a_snapshots_colours_are_its_drawings_and_modify_changes_them(window, tmp_path):
    """The user, 2026-10-14: a snapshot's Change Colors listed the wrong
    colours (its markup style's, not its drawing's), so changing them did
    nothing. It lists what the drawing sets and the change shows."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter
    from calcforge.io import pdfio
    from calcforge.items.snapshot import SnapshotItem
    from calcforge.ui import colorprocess
    path = tmp_path / "set.pdf"
    path.write_bytes(a_page())
    pdfio.import_pages(window.document, str(path), [0], at=0)
    window.rebuild_scenes()
    window.interactive_prompts = False
    frame = window.document.pages[0].frame
    window.take_snapshot(frame, QRectF(10, 20, 120, 60))
    window.paste_items()
    (snap,) = [i for i in window.view.scene().items() if isinstance(i, SnapshotItem)]

    def red_and_green():
        image = QImage(240, 120, QImage.Format_RGB32)
        image.fill(0xFFFFFFFF)
        painter = QPainter(image)
        painter.scale(2, 2)
        snap.paint_visible(painter) if hasattr(snap, "paint_visible") else snap.paint(painter, None)
        painter.end()
        colours = {image.pixelColor(x, y).name() for x in range(0, 240, 3) for y in range(0, 120, 3)}
        return "#ff0000" in colours, "#00ff00" in colours

    assert red_and_green() == (True, False)
    dialog = window.change_colors(snap) or window._last_color_dialog
    assert {"#000000", "#ff0000"} <= set(dialog.colours), "the drawing's own colours"
    dialog.pairs[0][1].setCurrentIndex(dialog.pairs[0][1].findData("#ff0000"))
    dialog.pairs[0][2].set("#00ff00")
    assert colorprocess.finish_item(window, snap, dialog.process())
    (snap,) = [i for i in window.view.scene().items() if isinstance(i, SnapshotItem)]
    assert red_and_green() == (False, True)
    window.undo_stack.undo()
    (snap,) = [i for i in window.view.scene().items() if isinstance(i, SnapshotItem)]
    assert red_and_green() == (True, False)
