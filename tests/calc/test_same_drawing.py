"""Equations look exactly as WebSMath draws them (the user's instruction:
the visuals are WebSMath's code, one to one).

The same keystrokes typed into WebSMath's own window and into CalcForge give
pixel-identical drawings — of the region itself, and through the page item
that puts it on a CalcForge page (at 4/3 zoom one SMath pixel is one pixel).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter

import tests.calc.test_calcforge_window as cw
from tests.calc.legacy_ui.worksheet_view import WorksheetView
from tests.calc.test_ui import press, type_at

LINES = ["M:12.5'kN", "b:300'mm", "M/b=", "sqrt(M/(2'kN=", "x^2+1/3=", "if(1>0,2", "mat("]


def _render(paint, rect, scale):
    image = QImage(int(rect.width() * scale) + 4, int(rect.height() * scale) + 4, QImage.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.scale(scale, scale)
    painter.translate(-rect.topLeft())
    paint(painter)
    painter.end()
    return image


def _difference(a: QImage, b: QImage) -> int:
    assert a.size() == b.size(), (a.size(), b.size())
    return sum(abs(QColor(a.pixel(x, y)).lightness() - QColor(b.pixel(x, y)).lightness())
               for x in range(a.width()) for y in range(a.height()))


def test_equations_are_drawn_pixel_for_pixel_as_websmath_draws_them(window):
    ours = cw.Sheet(window)
    theirs = WorksheetView()
    y = 18
    for keys in LINES:
        type_at(theirs, 18, y, keys)
        press(theirs, Qt.Key_Return)
        ours.type_at(18, y, keys)
        ours.press(Qt.Key_Return)
        y += 54
    theirs.focus_item(None)
    ours.calc.leave()
    assert len(theirs.items) == len(ours.items) == len(LINES)
    for region_item in theirs.items.values():
        item = ours.at_y(region_item.region.y)
        assert item.text() == region_item.region.editor.root.text()
        reference = _render(lambda p: region_item.paint(p, None), region_item.frame_rect(), 1.0)
        drawn = _render(lambda p: item._view.paint(p, None), item._view.frame_rect(), 1.0)
        assert _difference(reference, drawn) == 0, item.text()
        # and through the page item, at the zoom where 1 SMath pixel = 1 pixel
        rect = item.local_rect()
        on_page = _render(item.paint_visible, rect, 4.0 / 3.0)
        on_page = on_page.copy(0, 0, reference.width(), reference.height())
        assert _difference(reference, on_page) == 0, item.text()
