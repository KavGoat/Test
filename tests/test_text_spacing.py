"""Line spacing and margins for words in a box, as Revu's (the user,
2026-10-19: "Make sure that our text boxes and callouts have line space and
margins etc like Bluebeam … also add auto fit text size to all the relevant
markups").

Line Spacing is Single, 1.15, 1.5, Double or any multiple; Margins are the
room between the border and the words, one value or each side. Both are laid
out on screen, while typing, in Alt+Z's fit and in the drawn appearance; both
are kept in the PDF (/DS's ``line-height`` and ``margin``, /RC's style) and
read back from a file that has them; a file without them is as it was.
"""
from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QTextBlockFormat, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QDoubleSpinBox

from calcforge.items.text import CalloutItem, TextItem, TypewriterItem
from tests.test_propbar_gaps import pick, pump, save_and_reopen

LINES = "first line\nsecond line\nthird line"


def boxed(kind=TextItem, spacing=1.0, margins=(), text=LINES):
    item = kind(text, QRectF(0, 0, 200, 40))
    item.style.line_spacing = spacing
    item.style.text_margins = margins
    item.apply_style()
    return item


def tops(item) -> list:
    """Where each line starts, down the document."""
    out = []
    block = item.doc.firstBlock()
    while block.isValid():
        layout = block.layout()
        out.append(layout.position().y() + layout.lineAt(0).y())
        block = block.next()
    return out


def ink(item, zoom=4) -> QImage:
    """The words as they are drawn — the same painting the PDF's appearance
    is made with — on white."""
    rect = item.local_rect()
    image = QImage(int(rect.width() * zoom) + 8, int(rect.height() * zoom) + 8,
                   QImage.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.scale(zoom, zoom)
    item.paint_text(painter)
    painter.end()
    return image


def ink_bands(image) -> list:
    """The first row of each run of rows with dark pixels in them."""
    starts, inside = [], False
    for y in range(image.height()):
        dark = any(QColor(image.pixel(x, y)).lightness() < 128
                   for x in range(0, image.width(), 2))
        if dark and not inside:
            starts.append(y)
        inside = dark
    return starts


def ink_left(image) -> int:
    for x in range(image.width()):
        if any(QColor(image.pixel(x, y)).lightness() < 128 for y in range(image.height())):
            return x
    return -1


# ---------------------------------------------------------------------------
# the layout
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", [TextItem, CalloutItem, TypewriterItem])
def test_line_spacing_sets_the_drawn_line_pitch(qapp, kind):
    single = boxed(kind, 1.0)
    double = boxed(kind, 2.0)
    assert double.line_height_factor() == 2.0
    one, two = tops(single), tops(double)
    pitch = one[1] - one[0]
    assert pitch > 5
    assert two[1] - two[0] == pytest.approx(2 * pitch, abs=0.01)
    assert two[2] - two[1] == pytest.approx(2 * pitch, abs=0.01)
    # and as drawn: the second line's ink twice as far down
    drawn_one, drawn_two = ink_bands(ink(single)), ink_bands(ink(double))
    assert len(drawn_one) == len(drawn_two) == 3
    assert drawn_two[1] - drawn_two[0] == pytest.approx(2 * (drawn_one[1] - drawn_one[0]),
                                                        abs=2)


def test_any_multiple_is_taken_and_kept_in_range(qapp):
    item = boxed(TextItem, 1.15)
    assert item.line_height_factor() == pytest.approx(1.15)
    pitch = tops(item)[1] - tops(item)[0]
    assert pitch == pytest.approx(1.15 * (tops(boxed())[1] - tops(boxed())[0]), abs=0.05)
    item.style.line_spacing = 0
    assert item.line_height_factor() == 1.0
    item.style.line_spacing = 99
    assert item.line_height_factor() == 10.0


@pytest.mark.parametrize("kind", [TextItem, CalloutItem, TypewriterItem])
def test_alt_z_fits_the_spaced_lines(qapp, kind):
    single = boxed(kind, 1.0)
    single.size_to_text()
    double = boxed(kind, 2.0)
    double.size_to_text()
    left, top, right, bottom = single.margins()
    pitch = tops(single)[1] - tops(single)[0]
    assert single.local_rect().height() == pytest.approx(3 * pitch + top + bottom, abs=0.01)
    # two lines' worth of extra room between three lines, and no blank band
    # under the last one
    assert double.local_rect().height() == pytest.approx(5 * pitch + top + bottom, abs=0.01)
    assert double.local_rect().width() == pytest.approx(single.local_rect().width())


def test_margins_move_the_words_and_the_fit(qapp):
    plain = boxed(TextItem)
    plain.size_to_text()
    roomy = boxed(TextItem, margins=(20.0, 12.0, 6.0, 9.0))
    assert roomy.margins() == (20.0, 12.0, 6.0, 9.0)
    assert roomy.text_rect().topLeft() == QPointF(20.0, 12.0)
    roomy.size_to_text()
    words = plain.local_rect().width() - 8
    assert roomy.local_rect().width() == pytest.approx(words + 26, abs=0.01)
    assert roomy.local_rect().height() == pytest.approx(
        plain.local_rect().height() - 8 + 21, abs=0.01)
    # the words are drawn that much further in
    assert ink_left(ink(roomy)) - ink_left(ink(plain)) == pytest.approx(16 * 4, abs=3)
    assert ink_bands(ink(roomy))[0] - ink_bands(ink(plain))[0] == pytest.approx(8 * 4, abs=3)


def test_the_lines_typed_take_the_spacing(window):
    from tests.test_usability import double_click, press_key, type_text
    window.show()
    window.select_tool("select")
    frame = window.document.pages[0].frame
    item = boxed(TextItem, 2.0, text="one")
    frame.add_markup(item)
    item.setPos(100, 100)
    pump()
    middle = item.mapToScene(item.local_rect().center())
    double_click(window.view, middle.x(), middle.y())
    pump()
    assert item.editing
    editor = item._editor
    assert editor.document() is item.doc
    press_key(window.view, Qt.Key_Return, "\r")
    type_text(window.view, "two")
    pump()
    item.end_edit()
    assert item.text() == "one\ntwo"
    pitch = tops(item)
    assert pitch[1] - pitch[0] == pytest.approx(2 * (tops(boxed())[1] - tops(boxed())[0]),
                                                abs=0.01)
    second = item.doc.findBlockByNumber(1).blockFormat()
    assert second.lineHeight() == pytest.approx(200)


# ---------------------------------------------------------------------------
# Bluebeam's exact line heights: scaled by the spacing, never doubled
# ---------------------------------------------------------------------------

def _bluebeam_box(spacing=1.0):
    from calcforge.io.btx import _rich_text
    item = TextItem("", QRectF(0, 0, 200, 60))
    item.style.font_size = 12
    item.style.line_spacing = spacing
    html = _rich_text({"RC": '<body xmlns="http://www.w3.org/1999/xhtml" '
                             f'style="font:Helvetica 12pt;line-height:{13.8 * spacing:g}pt">'
                             '<p>one</p><p>two</p></body>'})
    item.set_html(html)
    item.apply_style()
    return item


def exact(item) -> list:
    out = []
    block = item.doc.firstBlock()
    while block.isValid():
        out.append(round(block.blockFormat().lineHeight(), 3))
        block = block.next()
    return out


def test_bluebeam_line_heights_scale_with_the_spacing(qapp):
    item = _bluebeam_box()
    assert exact(item) == [13.8, 13.8]
    item.style.line_spacing = 2.0
    item.apply_style()
    assert exact(item) == [27.6, 27.6]
    again = TextItem()
    again.deserialize(item.serialize())
    assert exact(again) == [27.6, 27.6], "laid out at its spacing once, not twice"
    item.style.line_spacing = 1.0
    item.apply_style()
    assert exact(item) == [13.8, 13.8]


def test_a_look_put_over_bluebeam_words_scales_them_from_theirs(qapp):
    from calcforge.ui import toolsets
    item = _bluebeam_box(1.5)
    assert exact(item) == [20.7, 20.7]
    toolsets.apply_properties(item, {"style": dict(item.style.to_dict(), line_spacing=1.0)})
    assert item.line_height_factor() == 1.0
    assert exact(item) == [13.8, 13.8]


# ---------------------------------------------------------------------------
# the PDF
# ---------------------------------------------------------------------------

def _annotations(path):
    with pymupdf.open(path) as document:
        page = document[0]
        out = []
        for annot in page.annots():
            if annot.type[1] != "FreeText":
                continue
            keys = {key: document.xref_get_key(annot.xref, key)[1]
                    for key in ("DS", "RC", "RD", "Rect")}
            out.append(keys)
        return out


def _text_box(window, spacing, margins):
    from tests.test_propbar_per_kind import drawn
    item = drawn(window, "text")
    item.set_text(LINES)
    item.style.line_spacing = spacing
    item.style.text_margins = margins
    item.apply_style()
    item.size_to_text()
    return item


def test_spacing_and_margins_are_saved_and_read_back(window, tmp_path):
    item = _text_box(window, 1.5, (10.0, 7.0, 5.0, 6.0))
    rect = QRectF(item.local_rect())
    pitch = tops(item)[1] - tops(item)[0]
    path = save_and_reopen(window, tmp_path)
    (back,) = [i for i in window.view.scene().ordered_markups() if isinstance(i, TextItem)]
    assert back.line_height_factor() == pytest.approx(1.5)
    assert tuple(back.margins()) == (10.0, 7.0, 5.0, 6.0)
    assert back.local_rect().height() == pytest.approx(rect.height(), abs=0.01)
    assert tops(back)[1] - tops(back)[0] == pytest.approx(pitch, abs=0.01)
    # as another reader finds it
    (said,) = _annotations(path)
    size = item.style.font_size
    assert f"line-height:{size * 1.15 * 1.5:.1f}pt" in said["DS"]
    assert f"line-height:{size * 1.15 * 1.5:.1f}pt" in said["RC"], "in /RC's style too"
    # Bluebeam's margin, a point in from where the words start, CSS's order
    assert "margin:6pt 5pt 5pt 9pt" in said["DS"]


def test_the_words_come_back_from_the_pdf_alone(qapp, tmp_path, window):
    """Without CalcForge's own record, as any reader has it: the spacing and
    margins out of /DS and /RC."""
    from calcforge.io import btx
    item = boxed(TextItem, 1.5, (10.0, 7.0, 5.0, 6.0))
    from calcforge.io.annotate import _rich_text_of
    settings, rich = _rich_text_of(item)
    look = btx._text_look({"Subtype": "FreeText", "DS": settings, "RC": rich,
                           "DA": f"0 0 0 rg /Helv {item.style.font_size} Tf"})
    assert look["line_spacing"] == pytest.approx(1.5)
    assert look["text_margins"] == (10.0, 7.0, 5.0, 6.0)


def test_circled_words_keep_their_square_in_rd(window, tmp_path):
    """Bluebeam's circled text: the circle round the whole of Rect, /RD the
    square the words are set in, /DS's margin inside that."""
    from calcforge.io.btx import free_text_colours
    item = _text_box(window, 1.0, (14.0, 14.0, 14.0, 14.0))
    item.style.text_shape = "circle"
    item.style.padding = 4.0
    item.apply_style()
    path = str(tmp_path / "circled.pdf")
    window.document.path = path
    assert window.save_document()
    (said,) = _annotations(path)
    numbers = [float(v) for v in said["RD"].strip("[]").split()]
    rect = [float(v) for v in said["Rect"].strip("[]").split()]
    box = item.mapRectToParent(item.local_rect()).normalized()
    # the margins, less the padding /DS's margin already gives
    assert numbers[0] == pytest.approx(box.left() + 10.0 - rect[0], abs=0.05)
    assert numbers[2] == pytest.approx(rect[2] - (box.right() - 10.0), abs=0.05)
    back = free_text_colours({"Shape": "Circle", "RD": numbers, "DS": said["DS"]})
    assert back["text_margins"][0] - (box.left() - rect[0]) == pytest.approx(14.0, abs=0.05)


def test_a_bluebeam_free_text_with_margins_and_line_height(window, tmp_path):
    path = str(tmp_path / "theirs.pdf")
    document = pymupdf.open()
    page = document.new_page(width=600, height=400)
    words = page.add_freetext_annot(pymupdf.Rect(100, 100, 300, 200), "one two",
                                    fontsize=12)
    words.update()
    document.xref_set_key(words.xref, "DS", pymupdf.get_pdf_str(
        "font: Helvetica 12pt; text-align:left; margin:5pt 6pt 7pt 8pt; "
        "line-height:20.7pt; color:#000000"))
    document.xref_set_key(words.xref, "RC", pymupdf.get_pdf_str(
        '<?xml version="1.0"?><body xmlns="http://www.w3.org/1999/xhtml" '
        'style="font:Helvetica 12pt;line-height:20.7pt"><p>one</p><p>two</p></body>'))
    document.save(path)
    document.close()
    window.open_path(path)
    window.rebuild_scenes()
    (item,) = [i for i in window.document.pages[0].frame.markups() if i.TYPE == "text"]
    assert item.line_height_factor() == pytest.approx(1.5)
    assert tuple(item.margins()) == (9.0, 6.0, 6.0, 8.0)
    assert exact(item) == [20.7, 20.7], "laid out at the file's own line height"


def test_a_file_without_them_looks_as_before(window, tmp_path):
    path = str(tmp_path / "plain.pdf")
    document = pymupdf.open()
    page = document.new_page(width=600, height=400)
    words = page.add_freetext_annot(pymupdf.Rect(100, 100, 300, 200), "one", fontsize=12)
    words.update()
    document.xref_set_key(words.xref, "DS", pymupdf.get_pdf_str(
        "font: Helvetica 12pt; margin:3pt; line-height:13.8pt"))
    document.save(path)
    document.close()
    window.open_path(path)
    window.rebuild_scenes()
    (item,) = [i for i in window.document.pages[0].frame.markups() if i.TYPE == "text"]
    assert item.line_height_factor() == 1.0
    assert tuple(item.margins()) == (4.0, 4.0, 3.0, 4.0), "as it was read before"
    single = int(getattr(QTextBlockFormat.SingleHeight, "value",
                         QTextBlockFormat.SingleHeight))
    assert int(item.doc.firstBlock().blockFormat().lineHeightType()) == single


def test_a_box_saved_before_reads_as_it_was(qapp):
    old = boxed(TextItem).serialize()
    old["style"].pop("line_spacing")
    assert "html_spacing" not in old
    item = TextItem()
    item.deserialize(old)
    assert item.line_height_factor() == 1.0
    assert tops(item) == tops(boxed(TextItem))
    from calcforge.io.annotate import _rich_text_of
    settings, _rich = _rich_text_of(item)
    size = item.style.font_size
    assert f"margin:{item.style.padding - 1:g}pt;" in settings
    assert f"line-height:{size * 1.15:.1f}pt" in settings


# ---------------------------------------------------------------------------
# the Properties panel and toolbar
# ---------------------------------------------------------------------------

def _panel(window, kind, name):
    found = window.properties_panel.findChild(kind, name)
    assert found is not None and found.isVisible(), name
    return found


@pytest.mark.parametrize("tool", ["text", "callout"])
def test_the_panels_line_spacing_is_one_undo_step(window, tool):
    from tests.test_propbar_per_kind import drawn
    item = drawn(window, tool)
    steps = window.undo_stack.count()
    combo = _panel(window, QComboBox, "lineSpacingPanel")
    pick(combo, 1.5)
    assert item.style.line_spacing == pytest.approx(1.5)
    assert window.undo_stack.count() == steps + 1
    window.refresh_selection()
    pump()
    assert window.line_spacing_combo.value() == pytest.approx(1.5), "the bar in step"
    window.undo_stack.undo()
    pump()
    item = [i for i in window.view.scene().ordered_markups()
            if i.TYPE == tool][0]
    assert item.line_height_factor() == 1.0


def test_the_panels_margins_one_value_or_each_side(window):
    from tests.test_exercise_round1_undo import type_into
    from tests.test_propbar_per_kind import drawn
    item = drawn(window, "text")
    steps = window.undo_stack.count()
    type_into(_panel(window, QDoubleSpinBox, "textMarginLeft"), "12")
    assert tuple(item.margins())[0] == pytest.approx(12.0)
    assert window.undo_stack.count() == steps + 1
    type_into(_panel(window, QDoubleSpinBox, "textMargin"), "6")
    assert tuple(item.margins()) == (6.0, 6.0, 6.0, 6.0)
    assert _panel(window, QDoubleSpinBox, "textMarginLeft").value() == pytest.approx(6.0)
    window.undo_stack.undo()
    pump()
    item = [i for i in window.view.scene().ordered_markups() if i.TYPE == "text"][0]
    assert tuple(item.margins())[0] == pytest.approx(12.0)


def test_the_toolbars_line_spacing(window):
    from tests.test_exercise_round1_undo import type_into
    from tests.test_propbar_per_kind import drawn
    item = drawn(window, "text")
    steps = window.undo_stack.count()
    combo = window.line_spacing_combo
    assert combo.isVisible()
    pick(combo, 2.0)
    assert item.style.line_spacing == pytest.approx(2.0)
    assert window.undo_stack.count() == steps + 1
    pump()
    panel = _panel(window, QComboBox, "lineSpacingPanel")
    assert panel.value() == pytest.approx(2.0), "the panel in step"
    # Other…: any multiple
    other = combo.findText(combo.OTHER)
    assert other == combo.count() - 1
    combo.showPopup()
    pump()
    view = combo.view()
    QTest.mouseClick(view.viewport(), Qt.LeftButton, Qt.NoModifier,
                     view.visualRect(view.model().index(other, 0)).center())
    pump()
    dialog = combo.dialog
    assert dialog is not None and dialog.isVisible()
    assert dialog.doubleValue() == pytest.approx(2.0)
    spin = dialog.findChild(QDoubleSpinBox)
    type_into(spin, "1.3", enter=False)
    dialog.accept()
    pump()
    assert item.style.line_spacing == pytest.approx(1.3)
    assert window.undo_stack.count() == steps + 2
    assert combo.value() == pytest.approx(1.3)
    assert combo.findText(combo.OTHER) == combo.count() - 1, "Other… stays last"
    assert combo.itemText(combo.currentIndex()) == "1.3"
    # and typed into the panel's
    type_into(_panel(window, QComboBox, "lineSpacingPanel").lineEdit(), "1.75")
    assert item.style.line_spacing == pytest.approx(1.75)
    assert window.undo_stack.count() == steps + 3
    window.undo_stack.undo()
    pump()
    window.undo_stack.undo()
    pump()
    item = [i for i in window.view.scene().ordered_markups() if i.TYPE == "text"][0]
    assert item.style.line_spacing == pytest.approx(2.0)


def test_the_bar_sets_the_next_boxes_spacing(window):
    from tests.test_propbar_per_kind import drawn
    window.select_tool("text")
    pump()
    window.view.scene().clearSelection()
    window.refresh_selection()
    window.line_spacing_combo.setValue(1.5)
    item = drawn(window, "text")
    assert item.style.line_spacing == pytest.approx(1.5)


def test_a_markup_style_keeps_them(window):
    from calcforge.ui import markupstyles, toolsets
    item = boxed(TextItem, 1.5, (9.0, 8.0, 7.0, 6.0))
    payload = markupstyles.payload_of(item)
    assert payload["style"]["line_spacing"] == pytest.approx(1.5)
    assert tuple(payload["style"]["text_margins"]) == (9.0, 8.0, 7.0, 6.0)
    assert "html_spacing" not in payload
    fresh = TextItem("new words")
    toolsets.apply_properties(fresh, payload)
    assert fresh.line_height_factor() == pytest.approx(1.5)
    assert tuple(fresh.margins()) == (9.0, 8.0, 7.0, 6.0)
    assert fresh.text() == "new words"


def test_alt_z_reaches_every_box_with_words(window):
    """Alt+Z on a text box, a typewriter, a callout and a Cloud+: each one
    brought in round its words, at its spacing and margins."""
    frame = window.document.pages[0].frame
    made = []
    for kind in (TextItem, TypewriterItem, CalloutItem):
        item = boxed(kind, 1.5, (6.0, 6.0, 6.0, 6.0))
        item.set_local_rect(QRectF(0, 0, 300, 200))
        frame.add_markup(item)
        made.append(item)
    cloud = boxed(CalloutItem, 1.5, (6.0, 6.0, 6.0, 6.0))
    cloud.set_local_rect(QRectF(0, 0, 300, 200))
    cloud.set_cloud_rect(QRectF(400, 400, 60, 40))
    frame.add_markup(cloud)
    assert cloud.display_name() == "Cloud+"
    made.append(cloud)
    window.view.scene().clearSelection()
    for item in made:
        item.setSelected(True)
    steps = window.undo_stack.count()
    window.act_autosize.trigger()
    assert window.undo_stack.count() == steps + 1
    for item in made:
        assert item.local_rect().height() < 100, item.TYPE
        pitch = tops(item)[1] - tops(item)[0]
        assert item.local_rect().height() == pytest.approx(
            2 * pitch + pitch / 1.5 + 12, abs=0.05), item.TYPE
