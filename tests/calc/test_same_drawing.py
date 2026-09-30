"""Equations look exactly as WebSMath draws them (the user's instruction:
the visuals are WebSMath's code, one to one).

Three things together say so, now that WebSMath's own window is gone
(phase 6):

- the drawing code *is* WebSMath's: ``calc/ui/layout.py`` and
  ``calc/ui/region_item.py`` are byte for byte the files at WebSMath's commit
  8b340fa (their SHA-256 is below);
- the same keystrokes typed into CalcForge make the same equations, with the
  same results, as they did in WebSMath's window (recorded from it before it
  was removed);
- what a CalcForge page draws is WebSMath's drawing, pixel for pixel: the
  region drawn by that code directly, and through the page item that puts it
  on a page (at 4/3 zoom one SMath pixel is one pixel).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter

import tests.calc.test_calcforge_window as cw
from markforge.calc.engine.display import display_text

LINES = ["M:12.5'kN", "b:300'mm", "M/b=", "sqrt(M/(2'kN=", "x^2+1/3=", "if(1>0,2", "mat("]

# What WebSMath's own window made of LINES (text, shown result), recorded
# from it on 2026-09-30 before it was removed.
WEBSMATH_MADE = [
    ("M≔12.5'kN", None),
    ("b≔300'mm", None),
    ("(M)/(b)=", "41.6667 kN/m"),
    ("√((M)/((2'kN)))=", "2.5"),
    ("x^(2+(1)/(3))=", None),
    ("if{1>0;2;}", None),
    ("mat(,,,,2,2)", None),
]

# SHA-256 of WebSMath's drawing code at commit 8b340fa (websmath/ui/...).
WEBSMATH_CODE = {
    "layout.py": "ffd273dde2cf3330cca11f409e4e887bc66e5663e02f2b450983900a00e18e73",
    "region_item.py": "8dad912a72a928ffb607253f468722d0672c9fc67f31d2c02a5be7de65024a8f",
}


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


def test_the_drawing_code_is_websmaths_byte_for_byte():
    folder = Path(__file__).resolve().parents[2] / "markforge" / "calc" / "ui"
    for name, digest in WEBSMATH_CODE.items():
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest, \
            f"calc/ui/{name} is no longer WebSMath's drawing code, one to one"


def test_equations_are_drawn_pixel_for_pixel_as_websmath_draws_them(window):
    ours = cw.Sheet(window)
    y = 18
    for keys in LINES:
        ours.type_at(18, y, keys)
        ours.press(Qt.Key_Return)
        y += 54
    ours.calc.leave()
    assert len(ours.items) == len(LINES)
    made = sorted(ours.items.values(), key=lambda item: item.region.y)
    for item, (text, shown) in zip(made, WEBSMATH_MADE):
        assert item.text() == text
        assert (display_text(item.region.display) if item.region.display is not None
                else None) == shown, text
        # WebSMath's drawing of the region, and the same through the page item
        reference = _render(lambda p: item._view.paint(p, None), item._view.frame_rect(), 1.0)
        rect = item.local_rect()
        on_page = _render(item.paint_visible, rect, 4.0 / 3.0)
        on_page = on_page.copy(0, 0, reference.width(), reference.height())
        assert _difference(reference, on_page) == 0, item.text()
