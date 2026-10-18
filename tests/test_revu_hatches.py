"""Revu 21's hatch list (the user's screenshot, docs/qa/revu_shots/propbar/
15.png, 2026-10-18): Manage…, (None), Brick, Diagonal Brick, Horizontal,
Vertical, Diagonal Down, Diagonal Up, Grid, Weave, 10% Dots, 20% Dots,
30% Dots — then CalcForge's own patterns and materials, all kept.

Each is drawn inside its shape and nowhere else, picked from the bar with the
mouse in one undo step, saved, opened again under the same key, and drawn by
MuPDF from the saved file. The keys files already hold ("up", "cross",
"dots"…) open looking the same, and a Bluebeam tool set's names for Revu's
hatches come in as these.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath
from PySide6.QtWidgets import QComboBox

from calcforge.items import hatches
from calcforge.items.shapes import RectItem
from tests.test_propbar_gaps import (drag, markups, mupdf_page, one_undo_step, page, pick,
                                     pump, save_and_reopen, select, w)  # noqa: F401

REVU_ORDER = ["(None)", "Brick", "Diagonal Brick", "Horizontal", "Vertical", "Diagonal Down",
              "Diagonal Up", "Grid", "Weave", "10% Dots", "20% Dots", "30% Dots"]
NEW = ["diagonal brick", "weave", "10% dots", "20% dots", "30% dots"]
OLD_KEYS = ["horizontal", "vertical", "cross", "up", "down", "diagonal cross", "dots", "dense",
            "steel", "masonry", "aluminium", "bronze", "lead", "plastic", "rubber", "glass",
            "brick", "block", "stone", "tiles", "earth", "hardcore", "honeycomb", "grating",
            "chequer plate", "concrete", "gravel", "sand", "batt insulation",
            "rigid insulation", "timber", "timber end"]


def _names(combo: QComboBox) -> list[str]:
    return [combo.itemText(i) for i in range(combo.count())
            if combo.itemData(i, Qt.AccessibleDescriptionRole) != "separator"]


def test_the_bars_list_is_revus_order_then_ours(w):
    names = _names(w.hatch_combo)
    assert names[0] == "Manage…"
    assert names[1:1 + len(REVU_ORDER)] == REVU_ORDER
    keys = [w.hatch_combo.itemData(i) for i in range(w.hatch_combo.count())]
    for key in OLD_KEYS + NEW:
        assert key in keys, key
    # CalcForge's own come after Revu's
    assert keys.index("steel") > keys.index("30% dots")
    assert keys.index("diagonal cross") > keys.index("30% dots")


def test_the_properties_panel_hatch_row_is_the_same_list(w):
    w.select_tool("rect")
    drag(w, page(w, 100, 100), page(w, 260, 200))
    (rect,) = markups(w, RectItem)
    select(w, rect)
    pump()
    combo = w.properties_panel.findChild(QComboBox, "hatchPattern")
    assert combo is not None
    assert _names(combo)[1:1 + len(REVU_ORDER)] == REVU_ORDER


def _hatched(name: str, size: int = 120, scale: float = 1.0, pad: int = 20) -> QImage:
    image = QImage(size + 2 * pad, size + 2 * pad, QImage.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    region = QPainterPath()
    region.addRect(QRectF(pad, pad, size, size))
    hatches.paint(painter, region, name, scale, QColor("black"))
    painter.end()
    return image


def _dark(image: QImage, x: int, y: int) -> bool:
    return QColor(image.pixel(x, y)).lightness() < 160


@pytest.mark.parametrize("key", [hatches.named_key(n) or n for n in
                                 ("Brick",) + tuple(NEW)])
def test_each_new_hatch_is_drawn_inside_its_shape_only(qapp, key):
    image = _hatched(key)
    inside = sum(_dark(image, x, y) for y in range(20, 140) for x in range(20, 140))
    outside = sum(_dark(image, x, y) for y in range(image.height()) for x in range(image.width())
                  if not (19 <= x <= 140 and 19 <= y <= 140))
    assert inside > 200, "drawn"
    assert outside == 0, "nothing past the shape"


def test_diagonal_down_and_up_lean_as_revus(qapp):
    """Revu's Diagonal Down runs top-left to bottom-right (\\), Up the other way."""
    def lean(key):
        image = _hatched(key, scale=2.0)
        down = up = 0
        for y in range(30, 130):
            for x in range(30, 130):
                if _dark(image, x, y):
                    down += _dark(image, x + 3, y + 3)
                    up += _dark(image, x + 3, y - 3)
        return down, up
    down, up = lean("down")
    assert down > 3 * up
    down, up = lean("up")
    assert up > 3 * down


def test_the_dots_grow_denser_as_named(qapp):
    def cover(key):
        image = _hatched(key, size=200, scale=3.0)
        total = 0.0
        for y in range(30, 210):
            for x in range(30, 210):
                total += 1 - QColor(image.pixel(x, y)).lightnessF()
        return total / (180 * 180)
    tens, twenties, thirties = cover("10% dots"), cover("20% dots"), cover("30% dots")
    assert 0.06 < tens < 0.14
    assert 0.15 < twenties < 0.25
    assert 0.24 < thirties < 0.36


def test_old_keys_open_looking_the_same(qapp):
    # the keys files and tool sets already hold are still in the library,
    # drawn by the same patterns as before
    for key in OLD_KEYS:
        assert key in hatches.LIBRARY and hatches.key_for(key) == key
    assert hatches.LIBRARY["up"][0][0][0] == 45 and hatches.LIBRARY["down"][0][0][0] == 135
    assert hatches.LIBRARY["cross"][0] == (hatches._family(0), hatches._family(90))
    assert hatches.LIBRARY["dots"][1] == "dots" and hatches.LIBRARY["dense"][1] == "dense dots"


def test_revus_names_in_a_tool_set_come_in_as_these(qapp):
    from calcforge.io.btx import _hatch_of
    names = {"Diagonal Up": "up", "Diagonal Down": "down", "Grid": "cross",
             "Hatch-DiagonalBrick": "diagonal brick", "Weave": "weave", "10% Dots": "10% dots",
             "20% Dots": "20% dots", "30% Dots": "30% dots", "Brick": "brick",
             "Horizontal": "horizontal", "Vertical": "vertical"}
    for name, key in names.items():
        assert hatches.key_for(name) == key, name
        payload = {"style": {"stroke": "#000000"}}
        _hatch_of({"PatternName": name}, {}, payload)
        assert payload["style"]["hatch"] == key
    # a pattern of somebody's own keeps its name
    payload = {"style": {}}
    _hatch_of({"PatternName": "WSP AUS STR_A_ConfinementHatch"}, {}, payload)
    assert payload["style"]["hatch"] == "WSP AUS STR_A_ConfinementHatch"


def test_picked_from_the_bar_saved_reopened_and_drawn_by_mupdf(w, tmp_path):
    keys = ["brick", "diagonal brick", "down", "weave", "10% dots", "30% dots"]
    places = {}
    for index, key in enumerate(keys):
        x, y = 40 + (index % 3) * 180, 60 + (index // 3) * 150
        w.select_tool("rect")
        drag(w, page(w, x, y), page(w, x + 140, y + 100))
        places[key] = QRectF(x, y, 140, 100)
    assert len(markups(w, RectItem)) == len(keys)
    w.select_tool("select")
    for key in keys:
        box = places[key]

        def the_rect(box=box):
            corner = page(w, box.x(), box.y())
            return next(r for r in markups(w, RectItem)
                        if (r.mapToScene(r.local_rect().topLeft()) - corner).manhattanLength() < 3)
        select(w, the_rect())
        one_undo_step(w, lambda key=key: pick(w.hatch_combo, key),
                      lambda key=key, the_rect=the_rect: the_rect().style.hatch == key)
        assert w.hatch_combo.currentData() == key

    path = save_and_reopen(w, tmp_path)
    assert {r.style.hatch for r in markups(w, RectItem)} == set(keys)
    image = mupdf_page(path, zoom=2.0)
    for key in keys:
        box = places[key]
        inside = QRectF(box.x() * 2 + 16, box.y() * 2 + 16, box.width() * 2 - 32,
                        box.height() * 2 - 32)
        inked = sum(1 for y in range(int(inside.top()), int(inside.bottom()), 2)
                    for x in range(int(inside.left()), int(inside.right()), 2)
                    if QColor(image.pixel(x, y)).lightness() < 235)
        total = (inside.width() / 2) * (inside.height() / 2)
        assert inked / total > 0.03, f"{key} is drawn by another reader"
