"""A PDF opens exactly as it was written (the user, 2026-10-01): its markups
are drawn by the file itself and nothing is converted. A markup becomes
CalcForge's only when it is actually edited — moved, resized, retyped,
restyled — and undoing that edit gives the file's own drawing back.
Picking one out (a click, the properties showing) changes nothing."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from tests.test_format import _a_drawing_marked_up_elsewhere
from tests.test_usability import click, double_click, drag


@pytest.fixture
def sheet(window, tmp_path):
    path = str(tmp_path / "marked.pdf")
    _a_drawing_marked_up_elsewhere(path)
    window.show()
    window.open_path(path)
    window.rebuild_scenes()
    window.select_tool("select")
    if hasattr(window, "toggle_calc_mode"):
        window.toggle_calc_mode(False)
    QApplication.instance().processEvents()
    return window


def marks(window):
    page = window.document.pages[0]
    return [i for i in page.frame.ordered_markups() if not getattr(i, "from_drawing", False)]


def by_kind(window, kind):
    for item in marks(window):
        if kind == "cloud" and getattr(item, "kind", "") == "cloud":
            return item
        if kind == "typed" and item.TYPE == "text":
            return item
        if kind == "callout" and item.TYPE == "callout":
            return item
    raise AssertionError(kind)


def all_as_written(window):
    page = window.document.pages[0]
    return all(i.still_theirs for i in marks(window)) and page.frame.left_to_us() == ()


def centre(item):
    return item.mapToScene(item.local_rect().center())


def test_opening_converts_nothing(sheet):
    assert len(marks(sheet)) == 3
    assert all_as_written(sheet)
    assert sheet.undo_stack.count() == 0
    assert not sheet.document.modified


def test_picking_one_out_changes_nothing(sheet):
    cloud = by_kind(sheet, "cloud")
    edge = cloud.mapToScene(cloud.local_rect().topLeft() + QPointF(0, 30))
    click(sheet.view, edge.x(), edge.y())
    assert cloud.isSelected()
    sheet.refresh_selection()                       # properties and style bar fill in
    QApplication.instance().processEvents()
    assert all_as_written(sheet), "selected, still drawn by its own file"
    assert sheet.undo_stack.count() == 0
    click(sheet.view, 560, 800)                     # and let go of it
    assert all_as_written(sheet)


def test_a_click_with_a_tremble_is_not_a_move(sheet):
    cloud = by_kind(sheet, "cloud")
    was = QPointF(cloud.pos())
    edge = cloud.mapToScene(cloud.local_rect().topLeft() + QPointF(0, 30))
    drag(sheet.view, edge.x(), edge.y(), edge.x() + 1, edge.y() + 1)
    assert cloud.pos() == was and all_as_written(sheet)


def test_moving_one_makes_it_ours_and_undo_gives_the_original_back(sheet):
    cloud = by_kind(sheet, "cloud")
    was = QPointF(cloud.pos())
    edge = cloud.mapToScene(cloud.local_rect().topLeft() + QPointF(0, 30))
    drag(sheet.view, edge.x(), edge.y(), edge.x() + 80, edge.y() + 40)
    assert not cloud.still_theirs
    assert sheet.document.pages[0].frame.left_to_us() == (cloud.from_annotation,)
    sheet.undo_stack.undo()
    QApplication.instance().processEvents()
    cloud = by_kind(sheet, "cloud")
    assert cloud.pos() == was
    assert all_as_written(sheet), "back to however it was written"
    sheet.undo_stack.redo()
    assert not by_kind(sheet, "cloud").still_theirs


def test_restyling_one_makes_it_ours_and_undo_gives_it_back(sheet):
    cloud = by_kind(sheet, "cloud")
    sheet.view.scene().clearSelection()
    cloud.setSelected(True)
    sheet.refresh_selection()
    sheet.view.begin_snapshot()
    style = cloud.style.copy() if hasattr(cloud.style, "copy") else cloud.style
    style.stroke = "#0000ff"
    cloud.set_style(style) if hasattr(cloud, "set_style") else setattr(cloud, "style", style)
    cloud.touch()
    sheet.view.commit_snapshot("Style")
    assert not cloud.still_theirs
    sheet.undo_stack.undo()
    assert all_as_written(sheet)


def test_opening_a_text_box_and_leaving_it_unchanged_leaves_it_as_written(sheet):
    typed = by_kind(sheet, "typed")
    count = sheet.undo_stack.count()
    double_click(sheet.view, *_xy(centre(typed)))
    assert sheet.view.editing_item() is typed
    assert not typed.still_theirs, "being typed in, it is drawn here"
    sheet.view.setFocus()
    QTest.keyClick(sheet.view.viewport(), Qt.Key_Escape)
    typed = by_kind(sheet, "typed")
    assert sheet.view.editing_item() is None
    assert all_as_written(sheet), "nothing was changed, so nothing changed hands"
    assert sheet.undo_stack.count() == count


def test_retyping_a_text_box_makes_it_ours_and_undo_gives_it_back(sheet):
    typed = by_kind(sheet, "typed")
    double_click(sheet.view, *_xy(centre(typed)))
    editor = typed._editor
    cursor = editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    editor.textCursor().insertText(" (rev B)")
    sheet.view.end_item_edit()
    typed = by_kind(sheet, "typed")
    assert "rev B" in typed.text() and not typed.still_theirs
    sheet.undo_stack.undo()
    typed = by_kind(sheet, "typed")
    assert "rev B" not in typed.text()
    assert all_as_written(sheet)


def test_saving_untouched_keeps_their_annotations(sheet, tmp_path):
    import pymupdf
    cloud = by_kind(sheet, "cloud")
    cloud.setSelected(True)
    sheet.refresh_selection()
    path = str(tmp_path / "again.pdf")
    from tests.test_calc_saving import save_to
    save_to(sheet, path)
    with pymupdf.open(path) as saved:
        page = saved[0]
        annots = list(page.annots())
        kinds = sorted(a.type[1] for a in annots)
        info = {a.type[1]: a.info for a in annots}
    assert kinds == ["FreeText", "FreeText", "Square"]
    assert info["Square"]["title"] == "Sam" and info["Square"]["content"] == "check this dim"


def _xy(point):
    return point.x(), point.y()


@pytest.mark.skipif(not __import__("os").path.exists(
    __import__("tests.test_format", fromlist=["REFERENCE"]).REFERENCE),
    reason="the reference drawing is not here")
def test_a_real_bluebeam_drawing_opens_as_written_and_stays_so_when_picked(window):
    """Every markup on a drawing made in Bluebeam: opened, each clicked and
    shown in Properties — all still drawn by the file, nothing to save."""
    from tests.test_format import REFERENCE
    window.show()
    window.open_path(REFERENCE)
    window.rebuild_scenes()
    window.select_tool("select")
    QApplication.instance().processEvents()
    assert not window.document.modified
    found = 0
    for page in window.document.pages:
        theirs = [i for i in page.frame.markups() if i.from_annotation]
        assert all(i.still_theirs for i in theirs), page.uid
        for item in theirs:
            window.view.scene().clearSelection()
            item.setSelected(True)
            window.refresh_selection()
            found += 1
        QApplication.instance().processEvents()
        assert all(i.still_theirs for i in theirs) and page.frame.left_to_us() == ()
    assert found and window.undo_stack.count() == 0 and not window.document.modified


def test_the_screen_is_the_same_after_picking_one_out_and_letting_go(sheet):
    def shot():
        QApplication.instance().processEvents()
        sheet.view.viewport().repaint()
        return sheet.view.viewport().grab().toImage()

    before = shot()
    cloud = by_kind(sheet, "cloud")
    edge = cloud.mapToScene(cloud.local_rect().topLeft() + QPointF(0, 30))
    click(sheet.view, edge.x(), edge.y())
    assert shot() != before, "selected: its handles show"
    sheet.view.scene().clearSelection()
    assert shot() == before, "let go: the very same drawing, pixel for pixel"


# -- the page and its markups drawn apart (Calcs.pdf, 2026-10-01) --------------------

def test_a_page_a_hair_off_its_own_size_keeps_its_markups_as_written(calcs):
    """842 pt wide came back from millimetres as 0.9999999999999999 of itself,
    and every markup on the page was taken over as it opened."""
    window, path = calcs
    frame = window.document.pages[0].frame
    singles = [i for i in frame.markups() if i.TYPE != "poly" or i.style.width > 10]
    assert singles and all(i.still_theirs for i in singles)


def _a_sheet_like_calcs(path):
    """Words under a Bluebeam highlighter (an ink line that multiplies), a
    three-stroke ink note, a text box and a rectangle."""
    import pymupdf
    document = pymupdf.open()
    page = document.new_page(width=842, height=595)
    page.insert_text((72, 100), "STEEL FRAMES TO NZS 3404", fontsize=14)
    box = page.add_freetext_annot(pymupdf.Rect(300, 200, 520, 250), "BUS BAR 1",
                                  fontsize=12, text_color=(0, 0, 1), fill_color=(0.85, 0.85, 1))
    box.update()
    square = page.add_rect_annot(pymupdf.Rect(100, 300, 260, 420))
    square.set_colors(stroke=(1, 0, 0))
    square.update()
    marker = page.add_ink_annot([[(70, 96), (300, 96)]])
    marker.set_border(width=14)
    marker.set_colors(stroke=(1, 1, 0))
    marker.set_blendmode(pymupdf.PDF_BM_Multiply)
    marker.update()
    scrawl = page.add_ink_annot([[(400, 400), (450, 420)], [(400, 430), (450, 450)],
                                 [(400, 460), (450, 480)]])
    scrawl.update()
    document.save(path)
    document.close()


@pytest.fixture
def calcs(window, tmp_path):
    path = str(tmp_path / "calcs.pdf")
    _a_sheet_like_calcs(path)
    window.show()
    window.open_path(path)
    window.rebuild_scenes()
    window.select_tool("select")
    QApplication.instance().processEvents()
    return window, path


def _page_as_shown(window, settle=True):
    """The first page as the canvas draws it, once every tile has arrived."""
    import time
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QImage, QPainter
    from calcforge.io import pdftiles
    frame = window.document.pages[0].frame
    rect = frame.mapRectToScene(frame.page_rect())

    def shot():
        image = QImage(int(rect.width()), int(rect.height()), QImage.Format_RGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        window.view.scene().render(painter, QRectF(image.rect()), rect)
        painter.end()
        return image
    for _ in range(500):
        shot()
        QApplication.instance().processEvents()
        if not pdftiles.TILES._waiting:
            break
        time.sleep(0.01)
    return shot()


def _as_array(image):
    import numpy as np
    from PySide6.QtGui import QImage
    image = image.convertToFormat(QImage.Format_RGB888)
    raw = np.frombuffer(bytes(image.constBits()), np.uint8)
    return raw.reshape(image.height(), image.bytesPerLine())[:, :image.width() * 3] \
        .reshape(image.height(), image.width(), 3).astype(int)


def test_the_page_looks_as_its_file_draws_it(calcs):
    import numpy as np
    import pymupdf
    window, path = calcs
    ours = _as_array(_page_as_shown(window))
    with pymupdf.open(path) as document:
        pixmap = document[0].get_pixmap(annots=True, alpha=False)
        theirs = np.frombuffer(pixmap.samples, np.uint8).reshape(
            pixmap.height, pixmap.width, 3).astype(int)
    h, w = min(ours.shape[0], theirs.shape[0]), min(ours.shape[1], theirs.shape[1])
    # leaving out the canvas's own grey edge round the page
    apart = np.abs(ours[2:h - 2, 2:w - 2] - theirs[2:h - 2, 2:w - 2]).max(axis=2)
    assert (apart > 80).sum() < 0.004 * h * w, int((apart > 80).sum())
    # the words under the highlighter still show: it multiplies
    words = ours[90:100, 75:200]
    assert words.min() < 90, "dark text under the yellow"


def test_taking_a_markup_over_does_not_redraw_the_page(calcs):
    window, path = calcs
    frame = window.document.pages[0].frame
    before = frame.markups_drawn_alone()
    square = next(i for i in frame.markups() if i.TYPE == "rect")
    square.setPos(square.pos() + QPointF(30, 0))
    assert not square.still_theirs
    assert frame.markups_drawn_alone() == before, "the page's tiles are the same tiles"
    window.undo_stack.undo() if window.undo_stack.count() else None


def test_a_highlighter_multiplies_when_edited_too(calcs):
    window, path = calcs
    frame = window.document.pages[0].frame
    marker = next(i for i in frame.markups() if getattr(i, "kind", "") in ("ink", "highlighter")
                  and i.style.width > 10)
    assert marker.style.blend == "multiply"


def test_a_three_stroke_ink_note_is_drawn_once(calcs):
    window, path = calcs
    frame = window.document.pages[0].frame
    strokes = [i for i in frame.markups() if getattr(i, "kind", "") == "ink"
               and i.style.width < 10]
    assert len(strokes) == 3
    assert not any(i.still_theirs or i.from_annotation for i in strokes), "ours"
    import pymupdf
    with pymupdf.open(path) as document:
        three = [a.xref for a in document[0].annots()
                 if a.type[1] == "Ink" and len(a.vertices or []) == 3]
    assert three and three[0] in frame.markups_drawn_alone(), "the page leaves the original out"
    assert three[0] in frame.left_to_us(), "and so does a save"


def test_a_three_stroke_ink_note_survives_save_and_reopen(calcs, tmp_path):
    from tests.test_calc_saving import save_to
    window, path = calcs
    saved = str(tmp_path / "again.pdf")
    save_to(window, saved)
    window.open_path(saved)
    window.rebuild_scenes()
    frame = window.document.pages[0].frame
    strokes = [i for i in frame.markups() if getattr(i, "kind", "") == "ink"
               and i.style.width < 10]
    assert len(strokes) == 3, "every stroke, once"


# -- taken over, a Bluebeam markup still looks as it did (Calcs.pdf, 2026-10-01) -------

def _bluebeam_bits(path):
    """A Bluebeam picture (/IT /SquareImage), a call-out with no border and
    rich text whose lines are indented with spaces."""
    import pymupdf
    document = pymupdf.open()
    page = document.new_page(width=842, height=595)
    picture = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 30), False)
    picture.set_rect(picture.irect, (20, 120, 220))
    page.insert_image(pymupdf.Rect(0, 0, 1, 1), pixmap=picture)    # the image object
    image_xref = page.get_images()[0][0]
    square = page.add_rect_annot(pymupdf.Rect(100, 100, 300, 250))
    square.set_colors(stroke=(1, 0, 0))
    square.set_border(width=0)
    square.update()
    document.xref_set_key(square.xref, "IT", "/SquareImage")
    document.xref_set_key(square.xref, "Image", f"{image_xref} 0 R")
    callout = page.add_freetext_annot(pymupdf.Rect(400, 100, 560, 160), "SEE NOTE",
                                      fontsize=8, text_color=(0, 0, 1),
                                      fill_color=(0.9, 0.9, 1))
    callout.update()
    document.xref_set_key(callout.xref, "IT", "/FreeTextCallout")
    document.xref_set_key(callout.xref, "CL", "[380 300 390 140 400 140]")
    document.xref_set_key(callout.xref, "BS", "<</W 0/S/S/Type/Border>>")
    words = page.add_freetext_annot(pymupdf.Rect(100, 350, 500, 420), "1.1 first",
                                    fontsize=9)
    words.update()
    document.xref_set_key(words.xref, "RC", pymupdf.get_pdf_str(
        '<?xml version="1.0"?><body xmlns="http://www.w3.org/1999/xhtml" '
        'style="font:Helvetica 9pt"><p>1.1 a numbered line</p>'
        '<p>      its second line, indented</p></body>'))
    document.save(path)
    document.close()


@pytest.fixture
def bits(window, tmp_path):
    path = str(tmp_path / "bits.pdf")
    _bluebeam_bits(path)
    window.open_path(path)
    window.rebuild_scenes()
    return window.document.pages[0].frame


def test_a_bluebeam_picture_keeps_its_picture_when_taken_over(bits):
    picture = next(i for i in bits.markups() if i.TYPE == "rect")
    assert picture.picture_framed and picture._their_picture is not None
    assert picture._their_picture.width() == 40, "the picture at its own resolution"
    assert not picture.style.stroke, "no border: its border width is 0"
    picture.make_it_ours()
    from PySide6.QtGui import QColor, QImage, QPainter
    image = QImage(220, 170, QImage.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    picture.paint_visible(painter)
    painter.end()
    assert QColor(image.pixel(100, 75)) == QColor(20, 120, 220), "the picture fills the box"


def test_a_call_out_with_no_border_keeps_its_leader(bits):
    callout = next(i for i in bits.markups() if i.TYPE == "callout")
    assert callout.box_border is False
    assert callout.style.width == 1.0 and callout.style.stroke


def test_indented_lines_keep_their_indent(bits):
    words = next(i for i in bits.markups() if i.TYPE == "text" and "numbered" in i.text())
    assert "\xa0" * 6 + "its second line" in words.serialize()["html"]


# -- the file's drawing, all of it (the user's photo and video, 2026-10-01) ---------

def test_a_markups_file_drawing_reaches_as_far_as_its_file_says(window, tmp_path):
    """A Bluebeam dimension's words sit out at the end of a leader, beyond
    what the markup measures as its own box: drawn only inside that box the
    "1m" was cut away. The file's drawing is laid in the box the file gives
    the annotation (/Rect)."""
    import pymupdf
    path = str(tmp_path / "dim.pdf")
    document = pymupdf.open()
    page = document.new_page(width=842, height=595)
    line = page.add_line_annot((100, 300), (200, 300))
    line.set_colors(stroke=(1, 0, 0))
    line.update()
    # a label well outside the line, as Bluebeam writes a dimension's value
    document.xref_set_key(line.xref, "Rect", "[90 250 330 320]")
    document.save(path)
    document.close()
    window.open_path(path)
    window.rebuild_scenes()
    frame = window.document.pages[0].frame
    (item,) = [i for i in frame.markups() if i.from_annotation]
    assert item.still_theirs and item.their_box
    look = item._their_look
    assert look is not None and look.isVisible()
    shown = item.mapRectToParent(look.boundingRect())
    assert shown.left() <= 91 and shown.right() >= 329, shown
    item.setPos(item.pos() + QPointF(10, 0))              # taken over: the file's drawing goes
    assert not look.isVisible()


def test_an_untouched_highlighter_is_drawn_with_the_page(calcs):
    """It multiplies into what is under it, which only the page's own render
    does exactly — on the graphics card a multiply was a black block."""
    window, path = calcs
    frame = window.document.pages[0].frame
    marker = next(i for i in frame.markups() if i.style.blend == "multiply")
    assert marker.from_annotation not in frame.markups_drawn_alone()
    marker.setPos(marker.pos() + QPointF(0, 20))           # taken over
    assert marker.from_annotation in frame.markups_drawn_alone()


def test_hiding_an_annotation_never_rebuilds_its_appearance(tmp_path):
    """PyMuPDF's set_flags has MuPDF build a new appearance its own way — a
    Bluebeam call-out became a solid box. The hidden flag is written into
    the dictionary instead, and the appearance stream is untouched."""
    import pymupdf
    from calcforge.pdf import engine
    path = str(tmp_path / "box.pdf")
    _bluebeam_bits(path)
    with pymupdf.open(path) as document:
        page = document[0]
        callout = next(a for a in page.annots() if a.type[1] == "FreeText")
        number = callout.xref
        appearance = document.xref_get_key(number, "AP")
        stream = document.xref_stream(int(appearance[1].split()[1]))
        engine.leave_out(page, (number,))
        engine.display_list(document, 0, True)
        assert document.xref_get_key(number, "AP") == appearance
        assert document.xref_stream(int(appearance[1].split()[1])) == stream
        flags = int(document.xref_get_key(number, "F")[1])
        assert flags & pymupdf.PDF_ANNOT_IS_HIDDEN
