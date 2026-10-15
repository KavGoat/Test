"""Errors in the equations (the user, 2026-10-15): t:=fc with fc not defined
says so as soon as it is left — not only once t= is asked for — and every
error is written in red under its equation, selected or not, on screen, in
print and in the saved PDF."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from tests.test_calc_panels import an_equation


@pytest.fixture
def win(window):
    window.show()
    window.activateWindow()
    window.view.setFocus()
    return window


def _red_below(window, item) -> int:
    box = item.mapRectToScene(item.local_rect())
    area = QRectF(box.left(), box.bottom(), max(box.width(), 120), 14)
    image = QImage(int(area.width() * 4), int(area.height() * 4), QImage.Format_RGB32)
    image.fill(Qt.white)
    painter = QPainter(image)
    window.scene.render(painter, QRectF(image.rect()), area)
    painter.end()
    return sum(1 for x in range(image.width()) for y in range(image.height())
               if QColor(image.pixel(x, y)).red() > 150 and QColor(image.pixel(x, y)).green() < 90)


def test_a_definition_with_a_name_not_defined_says_so_in_red(win):
    item = an_equation(win, "t:fc")
    assert item.region.error is not None
    assert item.region.error.message == "fc - not defined."
    win.view.calc.leave()
    win.scene.clearSelection()
    assert not item.focused
    assert item._error_message() == "fc - not defined."
    assert item.boundingRect().bottom() > item.local_rect().bottom() + 4, "room for the note"
    assert _red_below(win, item) > 20


def test_an_evaluation_error_shows_without_being_selected_and_prints(win, tmp_path):
    """The user (2026-10-15): the red note prints and goes into the PDF too."""
    import pymupdf
    item = an_equation(win, "q*2=", 100, 220)
    win.view.calc.leave()
    win.scene.clearSelection()
    assert item._error_message() == "q - not defined."
    assert _red_below(win, item) > 20
    frame = item.parentItem()
    frame.print_mode = True
    try:
        assert _red_below(win, item) > 20, "printed as well"
    finally:
        frame.print_mode = False
    path = str(tmp_path / "errors.pdf")
    win.document.path = path
    assert win.save_document()
    with pymupdf.open(path) as saved:
        assert "q - not defined." in saved[0].get_text()


def test_a_good_equation_has_no_note(win):
    item = an_equation(win, "w:3", 100, 320)
    win.view.calc.leave()
    assert item._error_message() == "" and item._error_note_rect() is None
