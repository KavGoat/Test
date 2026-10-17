"""Revu's Print dialog, its preview folded in (docs/qa/revu_audit.md F1; the
user's decision, docs/qa/findings.md Round 3: "Build Revu's Print dialog, with
the preview folded in. Print Pages… opens it with Selected chosen. The
per-page and per-markup print ticks stay").

Driven the way a person drives it: Ctrl+P and File ▸ Print Preview… on the
real window, a thumbnail's own right-click, the mouse on the dialog's combos,
ticks and buttons, keys typed into its fields. The job goes to CalcForge's
Print to PDF printer (QPrinter, PdfFormat) — a real printer cannot run
headless — and the PDF is rendered back to check pages, paper sizes, scaling
and what printed in each stream.
"""
from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGroupBox, QMenu, QWidget

from calcforge.core.document import LANDSCAPE, MM_TO_PT
from calcforge.io import printing
from calcforge.io.printing import PrintOptions
from calcforge.items.shapes import RectItem
from calcforge.ui.printdialog import PDF_PRINTER, PrintDialog
from calcforge.ui.widgets import PagesRange
from tests.test_usability import drag, on_page

A4 = (595.0, 842.0)
A3_LANDSCAPE = (1191.0, 842.0)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def pump(times: int = 3) -> None:
    for _ in range(times):
        QApplication.processEvents()


@pytest.fixture
def win(window):
    window.show()
    window.activateWindow()
    window.view.setFocus()
    pump()
    yield window
    dialog = getattr(window, "print_dialog", None)
    if dialog is not None:
        try:
            dialog.done(0)
        except RuntimeError:
            pass


def a_rect(window, page=0, at=(300, 400), size=(200, 120)):
    frame = window.document.pages[page].frame
    item = RectItem("rect", QRectF(0, 0, *size))
    frame.add_markup(item, QPointF(*at))
    return item


def pages(window, count):
    asking, window.interactive_prompts = window.interactive_prompts, False
    while len(window.document.pages) < count:
        window.add_page()
    window.interactive_prompts = asking
    window.pages_panel.rebuild(window.document, window.current_index)
    window.go_to_page(0)
    pump()


def ctrl_p(window) -> PrintDialog:
    # back in the window, as when a dialog closes on a desktop (the offscreen
    # platform gives the window nothing back by itself)
    window.activateWindow()
    window.view.viewport().setFocus()
    pump(1)
    QTest.keyClick(window.view.viewport(), Qt.Key_P, Qt.ControlModifier)
    pump()
    dialog = QApplication.activeModalWidget()
    assert isinstance(dialog, PrintDialog), dialog
    return dialog


def ready(dialog) -> None:
    """Wait for the preview: the render processes' picture of a PDF page can
    take a moment, and after a second and a half it is drawn here."""
    import time
    give_up = time.monotonic() + 10
    while not dialog.preview_ready() and time.monotonic() < give_up:
        pump(1)
        time.sleep(0.005)
    pump()
    assert dialog.preview_ready()


def preview_picture(dialog):
    ready(dialog)
    return dialog.preview.grab().toImage()


def pick(combo, text) -> None:
    """Open the combo with the mouse and click the entry."""
    QTest.mouseClick(combo, Qt.LeftButton)
    pump()
    view = combo.view()
    row = combo.findText(text)
    assert row >= 0, text
    rect = view.visualRect(combo.model().index(row, 0))
    QTest.mouseClick(view.viewport(), Qt.LeftButton, Qt.NoModifier, rect.center())
    pump()
    if combo.currentText() != text:            # some styles want the release only
        combo.hidePopup()
        combo.setCurrentIndex(row)
    assert combo.currentText() == text


def click(widget) -> None:
    QTest.mouseClick(widget, Qt.LeftButton, Qt.NoModifier,
                     QPoint(min(8, widget.width() // 2), widget.height() // 2))
    pump()


def type_into(spin, text) -> None:
    spin.setFocus()
    QTest.keyClick(spin, Qt.Key_A, Qt.ControlModifier)
    QTest.keyClicks(spin, text)
    pump()


def print_to(dialog, path) -> str:
    """Print with the mouse to CalcForge's PDF printer, into *path*."""
    if dialog.printer.currentText() != PDF_PRINTER:
        pick(dialog.printer, PDF_PRINTER)
    dialog.file_path = str(path)
    QTest.mouseClick(dialog.go_button, Qt.LeftButton)
    pump()
    return str(path)


def sheets(path) -> list:
    with pymupdf.open(path) as pdf:
        return [(round(p.rect.width), round(p.rect.height)) for p in pdf]


def red_box(path, index=0, dpi=72):
    """The red ink's extent on a printed sheet, in points (or None)."""
    with pymupdf.open(path) as pdf:
        pix = pdf[index].get_pixmap(dpi=dpi)
    xs, ys = [], []
    n, samples, width = pix.n, pix.samples, pix.width
    for i in range(0, len(samples) - 2, n):
        r, g, b = samples[i], samples[i + 1], samples[i + 2]
        if r > 170 and g < 110 and b < 110:
            p = i // n
            xs.append(p % width)
            ys.append(p // width)
    if not xs:
        return None
    k = 72.0 / dpi
    return (min(xs) * k, min(ys) * k, (max(xs) + 1) * k, (max(ys) + 1) * k)


def darkest(path, box, index=0, dpi=72):
    """The darkest grey inside *box* (points) of a printed sheet."""
    with pymupdf.open(path) as pdf:
        pix = pdf[index].get_pixmap(dpi=dpi, clip=pymupdf.Rect(*box))
    samples, n = pix.samples, pix.n
    return min(min(samples[i], samples[i + 1], samples[i + 2])
               for i in range(0, len(samples) - 2, n))


def a_drawing(path):
    """A PDF page with page content (a black block) and a square annotation
    of somebody else's (red), as a drawing set arrives."""
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=A4[0], height=A4[1])
        page.draw_rect(pymupdf.Rect(60, 600, 240, 700), color=(0, 0, 0), fill=(0, 0, 0))
        annot = page.add_rect_annot(pymupdf.Rect(340, 600, 520, 700))
        annot.set_colors(stroke=(1, 0, 0))
        annot.set_border(width=4)
        annot.update()
        pdf.save(path)
    return str(path)


# ---------------------------------------------------------------------------
# opening it
# ---------------------------------------------------------------------------

def test_ctrl_p_opens_revus_print_dialog_with_its_sections(win):
    dialog = ctrl_p(win)
    assert dialog.windowTitle() == "Print"
    titles = [box.title() for box in dialog.findChildren(QGroupBox)]
    assert titles == ["Preview", "Printer", "Page Range", "Options"]
    assert isinstance(dialog.pages, PagesRange)
    assert dialog.pages.which() == PagesRange.ALL
    assert [dialog.stream.itemText(i) for i in range(dialog.stream.count())] == [
        "Document & Markups", "Document Only", "Markups Only"]
    assert [dialog.scaling.itemText(i) for i in range(dialog.scaling.count())] == [
        "None", "Fit to Paper", "Reduce to Paper", "Custom Scale", "Fit to Margins",
        "Reduce to Margins"]
    assert dialog.rotation.itemText(0) == "Auto"
    for name in ("printerProperties", "printToFile", "printGetWindow", "printAuto",
                 "printCopies", "printCollate", "printReverse", "printCentre", "printDim",
                 "printDefaults", "printGo", "printCancel"):
        assert dialog.findChild(QWidget, name) is not None, name
    assert dialog.centre.text() == "Centre"               # UK spelling
    assert PDF_PRINTER in [dialog.printer.itemText(i) for i in range(dialog.printer.count())]
    ready(dialog)
    assert dialog.page_of.text() == "1 of 1"
    # Esc is Cancel
    QTest.keyClick(dialog, Qt.Key_Escape)
    pump()
    assert not dialog.isVisible()


def test_print_preview_opens_the_same_dialog(win):
    file_menu = next(a.menu() for a in win.menuBar().actions() if a.text().replace("&", "") == "File")
    entry = next(a for a in file_menu.actions() if a.text() == "Print Preview…")
    entry.trigger()
    pump()
    dialog = QApplication.activeModalWidget()
    assert isinstance(dialog, PrintDialog)
    assert dialog.preview.isVisible()
    dialog.reject()
    printing_entry = next(a for a in file_menu.actions() if a.text() == "Print…")
    assert printing_entry.shortcut().toString() == "Ctrl+P"


def test_thumbnail_right_click_print_pages_opens_with_selected(win, tmp_path):
    pages(win, 4)
    for index in range(4):
        a_rect(win, index)
    win.show_panel("dock_pages", True)
    pump()
    strip = win.pages_panel.list
    # pick pages 2 and 3 with the mouse: click, then Shift+click
    QTest.mouseClick(strip.viewport(), Qt.LeftButton, Qt.NoModifier,
                     strip.visualItemRect(strip.item(1)).center())
    QTest.mouseClick(strip.viewport(), Qt.LeftButton, Qt.ShiftModifier,
                     strip.visualItemRect(strip.item(2)).center())
    pump()
    assert win.selected_pages() == [1, 2]
    clicked = []

    def choose():
        menu = QApplication.activePopupWidget()
        if not isinstance(menu, QMenu) or clicked:
            return
        timer.stop()
        entry = next(a for a in menu.actions() if a.text() == "Print Pages…")
        clicked.append(entry)
        QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier,
                         menu.actionGeometry(entry).center())

    timer = QTimer()
    timer.setInterval(5)
    timer.timeout.connect(choose)
    timer.start()
    point = strip.visualItemRect(strip.item(2)).center()
    QApplication.sendEvent(strip.viewport(), QContextMenuEvent(
        QContextMenuEvent.Mouse, point, strip.viewport().mapToGlobal(point)))
    timer.stop()
    pump()
    assert clicked
    dialog = QApplication.activeModalWidget()
    assert isinstance(dialog, PrintDialog)
    assert dialog.pages.which() == PagesRange.SELECTED
    assert dialog.pages.pages() == [1, 2]
    ready(dialog)
    assert dialog.page_of.text() == "1 of 2"
    out = print_to(dialog, tmp_path / "selected.pdf")
    assert sheets(out) == [(595, 842), (595, 842)]


def test_print_pages_on_one_page_offers_selected_for_it(win):
    pages(win, 3)
    dialog = win.print_pages(2)
    assert dialog.pages.which() == PagesRange.SELECTED and dialog.pages.pages() == [2]


# ---------------------------------------------------------------------------
# the options, by mouse and keyboard, and the preview following them
# ---------------------------------------------------------------------------

def test_options_by_mouse_and_keyboard_change_the_preview(win):
    a_rect(win)
    dialog = ctrl_p(win)
    first = preview_picture(dialog)
    # Page Scaling by the mouse: Custom Scale, then 50 typed into it
    pick(dialog.scaling, "Custom Scale")
    assert dialog.custom_scale.isEnabled()
    type_into(dialog.custom_scale, "50")
    assert dialog.custom_scale.value() == 50
    halved = preview_picture(dialog)
    assert halved != first
    # Centre off by the mouse: X and Y come alive and move the page
    click(dialog.centre)
    assert not dialog.centre.isChecked() and dialog.x.isEnabled()
    type_into(dialog.x, "40")
    moved = preview_picture(dialog)
    assert moved != halved
    # Print by the keyboard: Down from Document & Markups to Document Only
    dialog.stream.setFocus()
    QTest.keyClick(dialog.stream, Qt.Key_Down)
    pump()
    assert dialog.stream.currentData() == printing.DOCUMENT
    without = preview_picture(dialog)
    assert without != moved
    QTest.keyClick(dialog.stream, Qt.Key_Up)
    pump()
    assert dialog.stream.currentData() == printing.BOTH
    # Copies typed: Collate comes alive
    assert not dialog.collate.isEnabled()
    type_into(dialog.copies, "3")
    assert dialog.copies.value() == 3 and dialog.collate.isEnabled()
    # Auto off by the mouse: Size and Portrait / Landscape come alive
    click(dialog.auto)
    assert dialog.size.isEnabled() and dialog.landscape.isEnabled()
    click(dialog.landscape)
    assert dialog.options().landscape
    turned = preview_picture(dialog)
    assert turned != moved and turned != without


def test_the_preview_shows_the_stream_chosen(win):
    a_rect(win)
    dialog = ctrl_p(win)
    ready(dialog)
    shown = dialog.preview_image(win.document.pages[0])
    red = _reds(shown)
    assert red > 0
    pick(dialog.stream, "Document Only")
    ready(dialog)
    assert _reds(dialog.preview_image(win.document.pages[0])) == 0
    pick(dialog.stream, "Markups Only")
    ready(dialog)
    assert _reds(dialog.preview_image(win.document.pages[0])) == red


def _reds(image) -> int:
    count = 0
    for y in range(0, image.height(), 2):
        for x in range(0, image.width(), 2):
            c = image.pixelColor(x, y)
            if c.red() > 170 and c.green() < 110 and c.blue() < 110:
                count += 1
    return count


def test_preview_steps_through_the_pages_by_mouse_and_page_down(win):
    pages(win, 3)
    dialog = ctrl_p(win)
    ready(dialog)
    assert dialog.page_of.text() == "1 of 3" and not dialog.prev_button.isEnabled()
    QTest.mouseClick(dialog.next_button, Qt.LeftButton)
    assert dialog.page_of.text() == "2 of 3"
    QTest.keyClick(dialog, Qt.Key_PageDown)
    assert dialog.page_of.text() == "3 of 3" and not dialog.next_button.isEnabled()
    QTest.mouseClick(dialog.first_button, Qt.LeftButton)
    assert dialog.page_of.text() == "1 of 3"
    QTest.mouseClick(dialog.last_button, Qt.LeftButton)
    assert dialog.page_of.text() == "3 of 3"
    QTest.keyClick(dialog, Qt.Key_PageUp)
    assert dialog.page_of.text() == "2 of 3"
    # a Custom range typed into the Pages box: the preview follows it
    dialog.pages.range.setFocus()
    QTest.keyClick(dialog.pages.range, Qt.Key_A, Qt.ControlModifier)
    QTest.keyClicks(dialog.pages.range, "1, 3")
    pump()
    assert dialog.pages.which() == PagesRange.CUSTOM
    assert dialog.page_of.text() == "1 of 2"


def test_the_preview_is_quick(win):
    """Low resolution and kept: a change of scaling only re-lays it."""
    import time
    a_rect(win)
    dialog = ctrl_p(win)
    started = time.perf_counter()
    ready(dialog)
    assert time.perf_counter() - started < 1.5
    drawn = dict(dialog._images)
    pick(dialog.scaling, "Fit to Margins")
    assert dialog.preview_ready()               # nothing to draw again
    assert dialog._images.keys() == drawn.keys()
    longest = max(img.width() for img in drawn.values())
    assert longest <= 800                       # a preview, not a print


# ---------------------------------------------------------------------------
# what prints
# ---------------------------------------------------------------------------

def test_prints_every_page_on_its_own_paper_with_auto(win, tmp_path):
    win.add_page()
    win.document.pages[1].setup.apply_size("A3")
    win.document.pages[1].setup.orientation = LANDSCAPE
    dialog = ctrl_p(win)
    out = print_to(dialog, tmp_path / "auto.pdf")
    assert sheets(out) == [(595, 842), (round(A3_LANDSCAPE[0]), 842)]


def test_the_three_streams(win, tmp_path):
    rect = a_rect(win, at=(300, 400))
    from tests.test_calc_panels import an_equation
    an_equation(win, "12345+67890=", 80, 100)
    equation_box = (60, 80, 260, 140)
    printed = {}
    for words in ("Document & Markups", "Document Only", "Markups Only"):
        dialog = ctrl_p(win)
        pick(dialog.stream, words)
        printed[words] = print_to(dialog, tmp_path / f"{dialog.stream.currentData()}.pdf")
    both, document, markups = (printed[k] for k in ("Document & Markups", "Document Only",
                                                    "Markups Only"))
    # Document & Markups: the markup and the equation
    box = red_box(both)
    assert box is not None and abs(box[0] - 300) < 3 and abs(box[2] - 500) < 3
    assert darkest(both, equation_box) < 100
    # Document Only: the equation (page content), no markup
    assert red_box(document) is None
    assert darkest(document, equation_box) < 100
    # Markups Only: the markup on blank paper, no equation
    assert red_box(markups) is not None
    assert darkest(markups, equation_box) > 240
    assert rect.printable


def test_streams_with_a_drawings_own_annotations(win, tmp_path):
    win.open_from_command_line(a_drawing(tmp_path / "drawing.pdf"))
    pump()
    page = win.document.pages[0]
    assert page.markup_annotations, "the square came in as a markup"
    content, theirs = (70, 610, 230, 690), (330, 590, 530, 710)
    printed = {}
    for words in ("Document & Markups", "Document Only", "Markups Only"):
        dialog = ctrl_p(win)
        pick(dialog.stream, words)
        printed[words] = print_to(dialog, tmp_path / f"d_{dialog.stream.currentData()}.pdf")
    both = printed["Document & Markups"]
    assert darkest(both, content) < 60 and red_box(both) is not None
    document = printed["Document Only"]
    assert darkest(document, content) < 60 and red_box(document) is None
    markups = printed["Markups Only"]
    assert darkest(markups, content) > 240
    box = red_box(markups)
    assert box is not None and box[0] > theirs[0] - 5 and box[2] < theirs[2] + 5


def test_dim_page_content_tones_the_page_down_not_the_markups(win, tmp_path):
    win.open_from_command_line(a_drawing(tmp_path / "drawing.pdf"))
    pump()
    a_rect(win, at=(300, 200))
    dialog = ctrl_p(win)
    plain = print_to(dialog, tmp_path / "plain.pdf")
    dialog = ctrl_p(win)
    click(dialog.dim)
    assert dialog.dim.isChecked()
    dimmed = print_to(dialog, tmp_path / "dimmed.pdf")
    content = (70, 610, 230, 690)
    assert darkest(plain, content) < 60
    assert 110 < darkest(dimmed, content) < 220          # washed out, still there
    assert red_box(dimmed) is not None                   # the markups are not


def test_page_scaling_really_scales(win, tmp_path):
    a_rect(win, at=(300, 400), size=(200, 120))
    cases = {}
    for words, value in (("Custom Scale", "50"), ("Fit to Margins", None), ("None", None)):
        dialog = ctrl_p(win)
        click(dialog.auto)                      # onto A4 paper, chosen
        assert dialog.size.currentText() == "A4"
        pick(dialog.scaling, words)
        if value:
            type_into(dialog.custom_scale, value)
        cases[words] = print_to(dialog, tmp_path / f"{dialog.scaling.currentData()}.pdf")
    half = red_box(cases["Custom Scale"])
    width = half[2] - half[0]
    assert abs(width - 100) < 3                          # 200 pt at 50%
    left = (A4[0] - A4[0] / 2) / 2 + 300 / 2              # centred, then scaled
    assert abs(half[0] - left) < 3
    margins = red_box(cases["Fit to Margins"])
    scale = min((A4[0] - 36) / A4[0], (A4[1] - 36) / A4[1])
    assert abs((margins[2] - margins[0]) - 200 * scale) < 3
    full = red_box(cases["None"])
    assert abs((full[2] - full[0]) - 200) < 3


def test_rotation_auto_turns_a_landscape_page_onto_portrait_paper(win, tmp_path):
    win.document.pages[0].setup.apply_size("A3")
    win.document.pages[0].setup.orientation = LANDSCAPE
    win.go_to_page(0)
    pump()
    a_rect(win, at=(50, 50), size=(200, 100))
    dialog = ctrl_p(win)
    click(dialog.auto)
    out = print_to(dialog, tmp_path / "turned.pdf")
    assert sheets(out) == [(595, 842)]
    box = red_box(out)
    scale = min(A4[0] / 842, A4[1] / 1191)
    # turned a quarter clockwise: the page's top-left corner is at the
    # paper's top right
    assert abs(box[0] - (842 - 150) * scale) < 4 and abs(box[2] - (842 - 50) * scale) < 4
    assert abs(box[1] - 50 * scale) < 4 and abs(box[3] - 250 * scale) < 4
    # and 0° leaves it as it lies (cropped by Fit to Paper's scale only)
    dialog = ctrl_p(win)
    click(dialog.auto)
    pick(dialog.rotation, "0°")
    flat = red_box(print_to(dialog, tmp_path / "flat.pdf"))
    assert flat[2] - flat[0] > flat[3] - flat[1]


def test_copies_collate_and_reverse(win, tmp_path):
    win.add_page()
    win.document.pages[1].setup.apply_size("A3")
    pump()
    dialog = ctrl_p(win)
    type_into(dialog.copies, "2")
    assert dialog.collate.isChecked()
    collated = print_to(dialog, tmp_path / "collated.pdf")
    a4, a3 = (595, 842), (842, 1191)
    assert sheets(collated) == [a4, a3, a4, a3]
    dialog = ctrl_p(win)
    assert dialog.copies.value() == 2                    # remembered
    click(dialog.collate)
    apart = print_to(dialog, tmp_path / "apart.pdf")
    assert sheets(apart) == [a4, a4, a3, a3]
    dialog = ctrl_p(win)
    type_into(dialog.copies, "1")
    click(dialog.reverse)
    backwards = print_to(dialog, tmp_path / "reverse.pdf")
    assert sheets(backwards) == [a3, a4]


def test_the_per_page_and_per_markup_print_ticks_are_honoured(win, tmp_path):
    pages(win, 3)
    win.set_pages_printable([1], False)       # the thumbnail menu's tick, off
    pump()
    rect = a_rect(win, 0)
    a_rect(win, 2)
    rect.printable = False                    # Properties ▸ General ▸ Print, off
    dialog = ctrl_p(win)
    ready(dialog)
    assert dialog.page_of.text() == "1 of 2"             # page 2 is left out
    out = print_to(dialog, tmp_path / "ticks.pdf")
    assert len(sheets(out)) == 2
    assert red_box(out, 0) is None                       # its markup is left out
    assert red_box(out, 1) is not None


def test_get_window_prints_the_part_dragged(win, tmp_path):
    a_rect(win, at=(300, 400), size=(200, 120))
    dialog = ctrl_p(win)
    click(dialog.get_window_button)
    assert not dialog.isVisible()                        # stepped aside
    x0, y0 = on_page(win, 0, 280, 380)
    x1, y1 = on_page(win, 0, 520, 540)
    drag(win.view, x0, y0, x1, y1)
    pump()
    assert dialog.isVisible() and dialog.window_region is not None
    assert dialog.window_note.isVisible() and "page 1" in dialog.window_note.text()
    out = print_to(dialog, tmp_path / "window.pdf")
    box = red_box(out)
    assert box[2] - box[0] > 400                         # blown up to fill the paper


def test_get_window_esc_goes_back_unchanged(win):
    dialog = ctrl_p(win)
    click(dialog.get_window_button)
    QTest.keyClick(win.view.viewport(), Qt.Key_Escape)
    pump()
    assert dialog.isVisible() and dialog.window_region is None


def test_defaults_and_the_last_options_remembered(win, tmp_path):
    a_rect(win)
    dialog = ctrl_p(win)
    assert dialog.options() == PrintOptions()            # first time: the defaults
    pick(dialog.stream, "Markups Only")
    pick(dialog.scaling, "Reduce to Paper")
    click(dialog.dim)
    type_into(dialog.copies, "2")
    click(dialog.reverse)
    print_to(dialog, tmp_path / "remember.pdf")
    again = ctrl_p(win)
    chosen = again.options()
    assert (chosen.stream, chosen.scaling, chosen.dim, chosen.copies, chosen.reverse) == (
        printing.MARKUPS, printing.REDUCE_PAPER, True, 2, True)
    assert again.printer.currentText() == PDF_PRINTER
    # Defaults, by the mouse
    QTest.mouseClick(again.defaults, Qt.LeftButton)
    pump()
    assert again.options() == PrintOptions()
    assert again.stream.currentText() == "Document & Markups"
    assert again.scaling.currentText() == "Fit to Paper"
    # cancelled: what was printed last is what comes back
    QTest.mouseClick(again.findChild(QWidget, "printCancel"), Qt.LeftButton)
    third = ctrl_p(win)
    assert third.options().stream == printing.MARKUPS


def test_nothing_to_print_says_so(win, monkeypatch):
    win.document.pages[0].printable = False
    dialog = ctrl_p(win)
    ready(dialog)
    assert not dialog.go_button.isEnabled()
    assert "No pages" in dialog.preview_message()


def test_placement_rules():
    """The arithmetic, page by page (Revu's manual, Page Scaling)."""
    page, paper = QRectF(0, 0, 842, 1191).size(), QRectF(0, 0, 595, 842).size()
    fit = printing.place(page, paper, PrintOptions(scaling=printing.FIT_PAPER))
    assert fit.scale == pytest.approx(595 / 842)
    reduce = printing.place(QRectF(0, 0, 300, 400).size(), paper,
                            PrintOptions(scaling=printing.REDUCE_PAPER))
    assert reduce.scale == 1.0                            # never enlarged
    grow = printing.place(QRectF(0, 0, 300, 400).size(), paper,
                          PrintOptions(scaling=printing.FIT_PAPER))
    assert grow.scale > 1.0
    placed = printing.place(page, paper, PrintOptions(scaling=printing.NONE, centre=False,
                                                      x_mm=10, y_mm=20))
    corner = placed.transform.map(QPointF(0, 0))
    assert corner.x() == pytest.approx(10 * MM_TO_PT) and corner.y() == pytest.approx(20 * MM_TO_PT)
    order = printing.sheet_order(["a", "b"], PrintOptions(copies=2, collate=False, reverse=True))
    assert order == ["b", "b", "a", "a"]


def grey_ink(path, index=0, dpi=50) -> int:
    """How many pixels of black or grey ink (not red) a printed sheet has."""
    with pymupdf.open(path) as pdf:
        pix = pdf[index].get_pixmap(dpi=dpi)
    samples, n, count = pix.samples, pix.n, 0
    for i in range(0, len(samples) - 2, n):
        r, g, b = samples[i], samples[i + 1], samples[i + 2]
        if max(r, g, b) < 200 and max(r, g, b) - min(r, g, b) < 40:
            count += 1
    return count


def test_streams_on_a_spreadsheet_page(win, tmp_path):
    """A spreadsheet page's grid is its content; a markup over it is a markup."""
    from tests.test_sheet_pages import put, sheet_page
    run = sheet_page(win, 0)
    put(win, run, 0, 0, "1234567")
    put(win, run, 1, 0, "7654321")
    frame = win.document.pages[1].frame
    box = RectItem("rect", QRectF(0, 0, 120, 60))
    frame.add_markup(box, QPointF(200, 300))
    pump()
    printed = {}
    for words in ("Document & Markups", "Document Only", "Markups Only"):
        dialog = ctrl_p(win)
        dialog.pages.set_custom("2")
        pick(dialog.stream, words)
        printed[words] = print_to(dialog, tmp_path / f"s_{dialog.stream.currentData()}.pdf")
    both, document, markups = (printed[k] for k in ("Document & Markups", "Document Only",
                                                    "Markups Only"))
    assert grey_ink(both) > 0 and red_box(both) is not None
    assert grey_ink(document) > 0 and red_box(document) is None
    assert grey_ink(markups) == 0 and red_box(markups) is not None


def test_an_imported_drawing_prints_at_printer_resolution(win, tmp_path):
    """At 1200 dpi a whole A4 drawing rounded to 1,154 pixels over the
    render cap and printed blank, on every real printer (found building
    Print, 2026-10-17)."""
    from PySide6.QtPrintSupport import QPrinter
    from calcforge.io import export as export_io
    win.open_from_command_line(a_drawing(tmp_path / "drawing.pdf"))
    pump()
    content = (70, 610, 230, 690)
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(str(tmp_path / "old.pdf"))
    export_io.print_document(win.document, printer)
    assert darkest(str(tmp_path / "old.pdf"), content) < 60
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(str(tmp_path / "new.pdf"))
    assert printing.print_pages(printer, [win.document.pages[0]], PrintOptions()) == 1
    assert darkest(str(tmp_path / "new.pdf"), content) < 60


def _blacks(image) -> int:
    count = 0
    for y in range(0, image.height(), 2):
        for x in range(0, image.width(), 2):
            c = image.pixelColor(x, y)
            if max(c.red(), c.green(), c.blue()) < 60:
                count += 1
    return count


def test_the_preview_of_a_drawing_follows_the_stream(win, tmp_path):
    """The drawing's own picture comes from the render processes (or is
    drawn here if it is slow); either way each stream shows what prints."""
    win.open_from_command_line(a_drawing(tmp_path / "drawing.pdf"))
    pump()
    page = win.document.pages[0]
    dialog = ctrl_p(win)
    ready(dialog)
    both = dialog.preview_image(page)
    assert _blacks(both) > 0 and _reds(both) > 0
    pick(dialog.stream, "Document Only")
    ready(dialog)
    document = dialog.preview_image(page)
    assert _blacks(document) > 0 and _reds(document) == 0
    pick(dialog.stream, "Markups Only")
    ready(dialog)
    markups = dialog.preview_image(page)
    assert _blacks(markups) == 0 and _reds(markups) > 0
