"""Revu dims on the page the markups the Markups List's filter leaves out.

Revu's manual (Markups list, Filtering): "Markups on the PDF that do not
match the selected filters are dimmed ... determined by the Filtered
Annotation Dim percentage setting in the Markups List Preferences"; of the
search box: "any markups that are filtered out will be dimmed on the PDF".

The search is typed with real keys and the canvas itself is looked at. The
dimming is the canvas's alone: the saved file, an export and a print are
untouched by it, but for Print's own Dim Filtered Markups.
"""
from __future__ import annotations

import time

import pymupdf
import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from calcforge.items.shapes import RectItem
from calcforge.ui import filterdim


def pump(seconds=0.0, times=3):
    end = time.monotonic() + seconds
    while True:
        for _ in range(times):
            QApplication.processEvents()
        if time.monotonic() >= end:
            break
        time.sleep(0.005)


@pytest.fixture
def win(window):
    window.show()
    window.activateWindow()
    window.show_markups_list(True)          # Alt+L, as in Revu
    pump()
    yield window


def a_rect(window, at, subject, page=0, size=(80, 40)):
    frame = window.document.pages[page].frame
    item = RectItem("rect", QRectF(0, 0, *size))
    item.style.fill = "#ff0000"
    item.style.fill_opacity = 1.0
    item.subject = subject
    frame.add_markup(item, QPointF(*at))
    return item


def settle(window, seconds=1.2):
    """Long enough for the dimming to follow the list and the page's
    squares to be drawn again."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        window.view.viewport().grab()
        pump()
        time.sleep(0.01)


def colour_at(window, page_point, page=0):
    """The canvas's colour at a point of a page, as the screen shows it."""
    frame = window.document.pages[page].frame
    window.view.centerOn(frame.mapToScene(QPointF(300, 300)))
    pump()
    image = window.view.viewport().grab().toImage()
    where = window.view.mapFromScene(frame.mapToScene(QPointF(*page_point)))
    return image.pixelColor(where)


def search(window, text):
    """Type into the Markups List's search box, key by key."""
    box = window.markups_panel.filter
    box.setFocus()
    QTest.keyClick(box, Qt.Key_A, Qt.ControlModifier)
    QTest.keyClick(box, Qt.Key_Backspace)
    QTest.keyClicks(box, text)
    pump()


def test_typing_in_the_search_dims_what_it_leaves_out(win):
    kept = a_rect(win, (100, 100), "Keep me")
    gone = a_rect(win, (300, 100), "Leave me out")
    settle(win)
    assert colour_at(win, (140, 120)).green() < 40
    assert colour_at(win, (340, 120)).green() < 40
    search(win, "keep")
    settle(win)
    assert filterdim.is_dimmed(gone) and not filterdim.is_dimmed(kept)
    assert colour_at(win, (140, 120)).green() < 40               # shown as it is
    level = filterdim.opacity()
    faded = colour_at(win, (340, 120))
    assert abs(faded.green() - 255 * (1 - level)) < 25, faded.name()   # toned down
    # cleared by the keyboard: everything as it was
    box = win.markups_panel.filter
    QTest.keyClick(box, Qt.Key_A, Qt.ControlModifier)
    QTest.keyClick(box, Qt.Key_Backspace)
    settle(win)
    assert not filterdim.is_dimmed(gone)
    assert colour_at(win, (340, 120)).green() < 40


def test_a_column_filter_dims_too(win):
    a_rect(win, (100, 100), "Alpha")
    beta = a_rect(win, (300, 100), "Beta")
    panel = win.markups_panel
    panel.rebuild(win.document)
    subject = panel.COLUMNS.index("Subject")
    panel.set_column_filter(subject, {"Alpha"})
    settle(win)
    assert filterdim.is_dimmed(beta)
    assert colour_at(win, (340, 120)).green() > 80
    panel._clear_column_filters()          # the list's All button
    settle(win)
    assert not filterdim.is_dimmed(beta)


def test_the_dim_percent_preference(win):
    from calcforge.ui import preferences
    gone = a_rect(win, (300, 100), "Leave me out")
    a_rect(win, (100, 100), "Keep me")
    search(win, "keep")
    settle(win)
    before = colour_at(win, (340, 120)).green()
    prefs = preferences.current()
    changed = preferences.Preferences(**{**prefs.__dict__, "filtered_dim_percent": 90})
    try:
        win.apply_preferences(changed)
        settle(win)
        assert gone.opacity() == pytest.approx(0.1)
        assert colour_at(win, (340, 120)).green() > before + 40
    finally:
        win.apply_preferences(prefs)


def test_dimming_is_not_saved_exported_or_printed(win, tmp_path):
    from calcforge.io import export as export_io
    from calcforge.io import printing
    gone = a_rect(win, (300, 100), "Leave me out")
    a_rect(win, (100, 100), "Keep me")
    search(win, "keep")
    settle(win)
    assert filterdim.is_dimmed(gone)
    # saved
    win.document.path = str(tmp_path / "saved.pdf")
    assert win.save_document()
    with pymupdf.open(str(tmp_path / "saved.pdf")) as pdf:
        opacities = sorted(round(a.opacity if a.opacity >= 0 else 1.0, 2)
                           for a in pdf[0].annots())
    assert opacities and all(value == 1.0 for value in opacities), opacities
    # exported as a picture
    image = win.document.pages[0].frame.render_image(dpi=72)
    assert image.pixelColor(340, 120).green() < 40
    assert filterdim.is_dimmed(gone) and gone.opacity() < 1      # and dimmed again after
    # printed without Dim Filtered Markups: as it is; with it: toned down
    from PySide6.QtPrintSupport import QPrinter

    def printed(dim_filtered):
        path = str(tmp_path / f"print_{dim_filtered}.pdf")
        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(path)
        printing.print_pages(printer, [win.document.pages[0]],
                             printing.PrintOptions(dim_filtered=dim_filtered, auto_size=True),
                             filtered=win.markups_panel.filtered_out(win.document))
        with pymupdf.open(path) as pdf:
            return pdf[0].get_pixmap(dpi=72).pixel(340, 120)

    assert printed(False)[1] < 40
    assert printed(True)[1] > 80


def _drawing(path, count):
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=595, height=842)
        for i in range(count):
            x, y = 30 + (i % 12) * 45, 300 + (i // 12) * 40
            annot = page.add_rect_annot(pymupdf.Rect(x, y, x + 30, y + 25))
            annot.set_colors(stroke=(1, 0, 0), fill=(1, 0, 0))
            annot.set_info(subject="Theirs" if i else "Odd one")
            annot.update()
        pdf.save(path)
    return str(path)


@pytest.mark.parametrize("count", [3, 130], ids=["a few", "a crowded page"])
def test_their_untouched_annotations_are_dimmed(win, tmp_path, count):
    """Drawn by their own file: one at a time, or — on a crowded page —
    with the page; either way dimmed when filtered out, and back as their
    file drew them when the filter is cleared."""
    win.open_from_command_line(_drawing(tmp_path / "theirs.pdf", count))
    pump(0.3)
    frame = win.document.pages[0].frame
    assert frame.file_draws == (count > frame.FILE_DRAWN_FROM)
    theirs = [m for m in frame.markups() if getattr(m, "still_theirs", False)]
    assert len(theirs) == count
    first = (45, 312)                         # inside the first square, "Odd one"
    settle(win, 2.0)
    assert colour_at(win, first).green() < 60
    search(win, "theirs")
    settle(win, 2.5)
    odd = next(m for m in theirs if m.subject == "Odd one")
    assert filterdim.is_dimmed(odd)
    assert all(m.still_theirs for m in theirs)          # nothing taken over
    assert colour_at(win, first).green() > 90           # toned down
    assert colour_at(win, (90, 312)).green() < 60       # the others as they were
    search(win, "")
    settle(win, 2.5)
    assert not filterdim.is_dimmed(odd)
    assert colour_at(win, first).green() < 60


def test_a_thousand_markups_dim_quickly(win):
    frame = win.document.pages[0].frame
    for i in range(1000):
        item = RectItem("rect", QRectF(0, 0, 12, 8))
        item.subject = "even" if i % 2 == 0 else "odd"
        frame.add_markup(item, QPointF(20 + (i % 40) * 13, 20 + (i // 40) * 11))
    panel = win.markups_panel
    panel.rebuild(win.document)
    settle(win, 2.0)
    box = panel.filter
    box.setFocus()
    worst = 0.0
    for key in "even":                          # each key's own work, list included
        started = time.perf_counter()
        QTest.keyClicks(box, key)
        QApplication.processEvents()
        worst = max(worst, time.perf_counter() - started)
    started = time.perf_counter()
    panel.rebuild(win.document)                 # what follows a pause in the typing
    listed = time.perf_counter() - started
    started = time.perf_counter()
    changed = panel.dim_filtered_now()
    win.view.viewport().repaint()
    dimming = time.perf_counter() - started
    assert changed == 500
    print(f"\nworst key {worst * 1000:.1f} ms, list {listed * 1000:.0f} ms, "
          f"dimming 500 of 1000 and repainting {dimming * 1000:.0f} ms")
    assert worst < 0.05, worst                  # a key never waits for the list or page
    assert listed < 0.25, listed
    assert dimming < 0.2, dimming
    started = time.perf_counter()
    QTest.keyClick(box, Qt.Key_A, Qt.ControlModifier)
    QTest.keyClick(box, Qt.Key_Backspace)
    panel.dim_filtered_now()
    win.view.viewport().repaint()
    assert time.perf_counter() - started < 0.3
    assert not any(filterdim.is_dimmed(m) for m in frame.markups())


def test_the_preference_is_in_preferences(win):
    """Revu keeps Filtered Annotation Dim Percent in its Markups List
    preferences; CalcForge's Preferences ▸ Markup has it, typed in."""
    from calcforge.ui import dialogs, preferences
    from PySide6.QtWidgets import QSpinBox
    dialog = dialogs.PreferencesDialog(preferences.current(), win)
    try:
        box = dialog.findChild(QSpinBox, "filteredDimPercent")
        assert box is not None and box.value() == 60
        box.setFocus()
        QTest.keyClick(box, Qt.Key_A, Qt.ControlModifier)
        QTest.keyClicks(box, "75")
        assert dialog.result_preferences().filtered_dim_percent == 75
    finally:
        dialog.deleteLater()


# ---------------------------------------------------------------------------
# Revu's Filter List toggle
# ---------------------------------------------------------------------------

def test_filter_list_toggles_the_column_filters_without_losing_them(win):
    from calcforge.ui.panels import FILTER_LIST_KEY
    from calcforge.settings import app_settings
    a_rect(win, (100, 100), "Alpha")
    beta = a_rect(win, (300, 100), "Beta")
    panel = win.markups_panel
    button = panel.filter_list
    assert button.text() == "Filter List" and button.isCheckable() and button.isChecked()
    assert "kept" in button.toolTip()
    # beside the search box, as in Revu
    assert abs(button.geometry().center().y() - panel.filter.geometry().center().y()) < 6
    assert button.x() > panel.filter.x()
    subject = panel.COLUMNS.index("Subject")
    panel.set_column_filter(subject, {"Alpha"})
    settle(win)
    assert filterdim.is_dimmed(beta)
    assert panel.tree.topLevelItem(0).childCount() == 1
    # off, by a click: everything listed and at full strength, the filter kept
    QTest.mouseClick(button, Qt.LeftButton)
    settle(win)
    assert not button.isChecked() and not panel.filter_list_on()
    assert panel.column_filters == {subject: {"Alpha"}}
    assert panel.tree.topLevelItem(0).childCount() == 2
    assert not filterdim.is_dimmed(beta)
    assert colour_at(win, (340, 120)).green() < 40
    # the headings' filters are not there to click
    header = panel.tree.header()
    seen = []
    header.filterClicked.connect(lambda *a: seen.append(a))
    QTest.mouseClick(header.viewport(), Qt.LeftButton, Qt.NoModifier,
                     header.filter_rect(subject).center())
    assert not seen
    assert str(app_settings().value(FILTER_LIST_KEY)).lower() in ("false", "0")
    # on again, by a key given to it in Keyboard Shortcuts
    win.shortcuts.set_sequence("markupslist.filter_list", "Ctrl+Shift+F7")
    win.commands.apply()
    win.activateWindow()
    win.view.setFocus()
    QTest.keyClick(win.view.viewport(), Qt.Key_F7, Qt.ControlModifier | Qt.ShiftModifier)
    settle(win)
    assert button.isChecked()
    assert panel.tree.topLevelItem(0).childCount() == 1
    assert filterdim.is_dimmed(beta)
    QTest.mouseClick(header.viewport(), Qt.LeftButton, Qt.NoModifier,
                     header.filter_rect(subject).center())
    pump()
    assert seen                                           # the funnel answers again
    for popup in QApplication.topLevelWidgets():
        if popup.isVisible() and popup.inherits("QMenu"):
            popup.close()


# ---------------------------------------------------------------------------
# an ink line in several strokes, on screen and on paper
# ---------------------------------------------------------------------------

def _ink_drawing(path):
    """A drawing with somebody's ink line of two curved strokes, and a
    square of theirs."""
    import math
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=595, height=842)
        strokes = []
        for row in (0, 1):
            strokes.append([(100 + t * 4, 400 + row * 120 + 40 * math.sin(t / 8.0))
                            for t in range(0, 80)])
        ink = page.add_ink_annot(strokes)
        ink.set_colors(stroke=(1, 0, 0))
        ink.set_border(width=6)
        ink.set_info(subject="Ink")
        ink.update()
        square = page.add_rect_annot(pymupdf.Rect(100, 150, 200, 220))
        square.set_colors(stroke=(1, 0, 0), fill=(1, 0, 0))
        square.set_info(subject="Keep")
        square.update()
        pdf.save(path)
    return str(path)


def _ink_point():
    import math
    t = 40
    return (100 + t * 4, 400 + 40 * math.sin(t / 8.0))


def test_an_ink_line_in_strokes_is_dimmed_with_its_real_curves(win, tmp_path):
    win.open_from_command_line(_ink_drawing(tmp_path / "ink.pdf"))
    pump(0.3)
    frame = win.document.pages[0].frame
    strokes = [m for m in frame.markups() if getattr(m, "split_theirs", False)]
    assert len(strokes) == 2, "the ink line came in as two strokes"
    settle(win, 2.0)
    assert colour_at(win, _ink_point()).green() < 60
    search(win, "keep")
    settle(win, 2.5)
    assert all(filterdim.is_dimmed(m) for m in strokes)
    assert all(m.split_theirs for m in strokes)                  # nothing taken over
    number = strokes[0].split_from
    assert number in frame.markups_drawn_alone()                 # the page leaves it out
    look = strokes[0]._whole_look
    assert look is not None and look.isVisible()                 # drawn whole, by its file
    faded = colour_at(win, _ink_point())
    assert faded.red() > 200 and 90 < faded.green() < 220, faded.name()
    assert colour_at(win, (150, 185)).green() < 60               # the square, kept
    search(win, "")
    settle(win, 2.5)
    assert not look.isVisible() and number not in frame.markups_drawn_alone()
    assert colour_at(win, _ink_point()).green() < 60


def test_print_dims_their_untouched_annotations_too(win, tmp_path):
    from tests.test_print_dialog import click, ctrl_p, print_to
    win.open_from_command_line(_ink_drawing(tmp_path / "ink.pdf"))
    pump(0.3)
    search(win, "ink")                       # the square is left out
    settle(win, 2.0)
    frame = win.document.pages[0].frame
    square = next(m for m in frame.markups() if getattr(m, "still_theirs", False))
    assert filterdim.is_dimmed(square)

    def green(path, point):
        with pymupdf.open(path) as pdf:
            return pdf[0].get_pixmap(dpi=72).pixel(int(point[0]), int(point[1]))[1]

    dialog = ctrl_p(win)
    assert dialog.dim_filtered.isChecked()
    dimmed = print_to(dialog, tmp_path / "dimmed.pdf")
    assert 90 < green(dimmed, (150, 185)) < 220         # their square, toned down
    assert green(dimmed, _ink_point()) < 60             # the ink line, as it is
    dialog = ctrl_p(win)
    click(dialog.dim_filtered)
    plain = print_to(dialog, tmp_path / "plain.pdf")
    assert green(plain, (150, 185)) < 60
    # and the ink line, in strokes, toned down when it is the one left out
    search(win, "keep")
    settle(win, 2.0)
    dialog = ctrl_p(win)
    click(dialog.dim_filtered)
    assert dialog.dim_filtered.isChecked()
    inked = print_to(dialog, tmp_path / "ink_dimmed.pdf")
    assert 90 < green(inked, _ink_point()) < 220
    assert green(inked, (150, 185)) < 60
