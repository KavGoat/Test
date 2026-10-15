"""Revu's Change Multiple Colors (the user's choice, 2026-10-15)."""
from __future__ import annotations

from PySide6.QtCore import QRectF

from calcforge.items.shapes import RectItem
from calcforge.ui import changecolors, colorpicker


def _two(window):
    frame = window.scene.frames[0]
    a = RectItem("rect", QRectF(0, 0, 60, 40))
    a.style.stroke, a.style.fill = "#ff0000", "#0000ff"
    b = RectItem("rect", QRectF(0, 0, 60, 40))
    b.style.stroke, b.style.fill = "#000000", "#ff0000"
    for item, x in ((a, 50), (b, 150)):
        item.setParentItem(frame)
        item.setPos(x, 50)
        item.setSelected(True)
    return a, b


def test_the_source_list_is_the_colours_the_selection_uses(window):
    a, b = _two(window)
    found = changecolors.colours_in([a, b])
    assert found[:3] == ["#ff0000", "#0000ff", "#000000"]
    assert len(found) == len(set(found)), "each colour once"


def test_one_colour_becomes_another_wherever_it_is_used_in_one_undo(window, monkeypatch):
    a, b = _two(window)
    dialog = changecolors.ChangeColorsDialog(window, [a, b])
    assert dialog.found[0] == "#ff0000" and dialog.source == "#ff0000"
    assert not dialog.ok.isEnabled(), "a destination is still to be chosen"
    colorpicker.ANSWERS[:] = ["#00aa00"]
    dialog._pick_destination()
    assert dialog.destination == "#00aa00" and dialog.ok.isEnabled()
    assert a.style.stroke == "#ff0000", "the After picture leaves the markups as they were"
    before = window.undo_stack.count()
    assert dialog.apply() == 2
    assert a.style.stroke == "#00aa00" and b.style.fill == "#00aa00"
    assert a.style.fill == "#0000ff" and b.style.stroke == "#000000"
    assert window.undo_stack.count() == before + 1
    window.undo_stack.undo()
    rects = [m for m in window.scene.frames[0].markups() if isinstance(m, RectItem)]
    strokes = sorted(m.style.stroke.lower() for m in rects)
    fills = sorted(m.style.fill.lower() for m in rects)
    assert strokes == ["#000000", "#ff0000"] and fills == ["#0000ff", "#ff0000"]


def test_the_right_click_menu_and_the_properties_panel_offer_it(window, monkeypatch):
    a, b = _two(window)
    window.refresh_selection()
    from PySide6.QtWidgets import QPushButton
    panel_button = window.findChild(QPushButton, "changeMultipleColors")
    assert panel_button is not None
    seen = []
    monkeypatch.setattr(changecolors, "change_multiple_colors",
                        lambda w, items: seen.append(list(items)) or 0)
    panel_button.click()
    assert seen and set(seen[0]) == {a, b}
