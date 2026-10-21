"""Every pointer the canvas draws itself reads on the white page and on dark.

The user, 2026-10-21, on Windows: "Cloud cursor is white and can't be seen on
the sheet in dark mode, check all cursors again." The tools' pointers were
drawn with the toolbar icons' inks, which the dark theme makes light — but a
pointer is seen over the page, which stays white in either theme, and over
drawings, which may be dark. So no pointer takes its colour from the theme:
each is dark ink with a white edge (or the system arrow's white with a black
outline), and the ones Windows draws itself — the crosshair, the size
arrows, the I-beam, the hands — are the system's own.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter

from calcforge.ui.tools import TOOLS

WHITE = QColor("#ffffff")        # the page, in either theme
DARK = QColor("#202020")         # a dark drawing, the dark desk, a dark panel

#: how many of a pointer's pixels must stand well off each background
FEWEST_CLEAR_PIXELS = 12


def _luminance(colour: QColor) -> float:
    def linear(c: float) -> float:
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (0.2126 * linear(colour.red()) + 0.7152 * linear(colour.green())
            + 0.0722 * linear(colour.blue()))


def _over(pixmap, background: QColor) -> QImage:
    image = QImage(pixmap.width(), pixmap.height(), QImage.Format_RGB32)
    image.fill(background)
    painter = QPainter(image)
    drawn = pixmap.toImage()
    drawn.setDevicePixelRatio(1.0)
    painter.drawImage(0, 0, drawn)
    painter.end()
    return image


def _clear_pixels(pixmap, background: QColor) -> int:
    """The pixels of *pixmap*, laid on *background*, whose luminance differs
    from it by more than a half."""
    image = _over(pixmap, background)
    base = _luminance(background)
    return sum(1 for y in range(image.height()) for x in range(image.width())
               if abs(_luminance(QColor(image.pixel(x, y))) - base) > 0.5)


def custom_cursors(window) -> dict:
    """Every pointer the application draws for the canvas, by name."""
    from calcforge.items.base import rotate_cursor
    from calcforge.ui import view as view_module
    from calcforge.ui.cursors import BADGES, revu_cursor

    found = {f"select arrow, {badge}": revu_cursor(badge) for badge in BADGES}
    found["rotate"] = rotate_cursor()
    for kind in ("cell", "col", "row"):
        found[f"Excel {kind}"] = view_module.excel_cursor(kind)
    found["format painter"] = view_module.format_painter_cursor()
    found["arrow leader"] = view_module.arrow_leader_cursor()
    found["cloud leader / Cloud+"] = view_module.cloud_callout_cursor()
    found["equation move (SMath)"] = window.view.calc.move_cursor()
    for tool in TOOLS:
        cursor = window.view._cursor_for_tool(tool)
        if cursor.shape() == Qt.BitmapCursor:
            found[f"tool: {tool.label}"] = cursor
    return found


def _forget_made_cursors() -> None:
    """Drop the pointers made so far, so they are made again."""
    from calcforge.ui import cursors, view as view_module

    view_module._DRAWING_CURSORS.clear()
    view_module._CLOUD_CURSOR = None
    view_module._ARROW_LEADER_CURSOR = None
    view_module._CLOUD_CALLOUT_CURSOR = None
    cursors._MADE.clear()


def test_every_drawn_pointer_reads_on_the_white_page_and_on_dark(window):
    wrong = []
    for name, cursor in custom_cursors(window).items():
        pixmap = cursor.pixmap()
        assert not pixmap.isNull(), name
        for background in (WHITE, DARK):
            clear = _clear_pixels(pixmap, background)
            if clear < FEWEST_CLEAR_PIXELS:
                wrong.append(f"{name} over {background.name()}: {clear} clear pixels")
    assert not wrong, "\n".join(wrong)


def test_the_cloud_tools_pointer_is_dark_on_the_page_in_the_dark_theme(window, qapp):
    """The user's case: Cloud in hand, dark theme, over the white sheet."""
    from calcforge.app import apply_theme, current_theme
    from calcforge.theme import DARK as DARK_THEME

    before = current_theme()
    try:
        apply_theme(qapp, DARK_THEME)
        _forget_made_cursors()
        cloud = next(t for t in TOOLS if t.key == "cloud")
        window.select_tool("cloud")
        pixmap = window.view._cursor_for_tool(cloud).pixmap()
        image = _over(pixmap, WHITE)
        darkest = min(_luminance(QColor(image.pixel(x, y)))
                      for y in range(image.height()) for x in range(image.width()))
        assert darkest < 0.1, "dark ink on the white page"
    finally:
        apply_theme(qapp, before)
        _forget_made_cursors()


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_no_pointer_takes_its_colour_from_the_theme(window, qapp, theme):
    from calcforge.app import apply_theme, current_theme

    before = current_theme()
    try:
        apply_theme(qapp, "light")
        _forget_made_cursors()
        light = {name: c.pixmap().toImage() for name, c in custom_cursors(window).items()}
        apply_theme(qapp, theme)
        _forget_made_cursors()
        now = {name: c.pixmap().toImage() for name, c in custom_cursors(window).items()}
        changed = [name for name in light if light[name] != now[name]]
        assert not changed, f"drawn differently in the {theme} theme: {changed}"
    finally:
        apply_theme(qapp, before)
        _forget_made_cursors()
