"""Revu 21's line-style list (the user's screenshot, docs/qa/revu_shots/propbar/
14.png, 2026-10-18): Manage…, Solid, Dashed 1–6, then its complex styles —
Fenceline Circle, Fenceline Square, Gas, Hot Water, Zig Zag, Insulation,
Double, Tracks, Road — each with its name and its sample, a tick on the one in
use, and CalcForge's own dash styles after them.

Each complex style is drawn along any markup's path (and kept inside the
markup's box at any zoom), picked from the bar with the mouse in one undo
step, saved, opened again as the same style, and drawn by MuPDF from the saved
file the way another reader sees it. Old files' styles still load, and a
Bluebeam tool set's line-style names come in as these.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QComboBox, QStyleOptionViewItem

from calcforge.items import complexlines, linestyles
from calcforge.items.base import DASH_ARRAYS, Style
from calcforge.items.measure import LENGTH, MeasureItem
from calcforge.items.shapes import PolyItem, RectItem
from calcforge.items.text import TextItem
from tests.test_propbar_gaps import (drag, markups, mupdf_page, one_undo_step, page, pick,
                                     pump, save_and_reopen, select, w)  # noqa: F401

REVU_ORDER = ["Solid", "Dashed 1", "Dashed 2", "Dashed 3", "Dashed 4", "Dashed 5",
              "Dashed 6", "Fenceline Circle", "Fenceline Square", "Gas", "Hot Water",
              "Zig Zag", "Insulation", "Double", "Tracks", "Road"]
OLD_KEYS = ["dash", "dot", "dashdot", "dashdotdot", "long dash", "centre", "phantom",
            "hidden", "short dash", "dense dot", "sparse dot", "long dash dot",
            "long dash dot dot", "border", "divide", "double dash", "dash long gap"]


# ---------------------------------------------------------------------------
# the list
# ---------------------------------------------------------------------------
def _names(combo: QComboBox) -> list[str]:
    return [combo.itemText(i) for i in range(combo.count())
            if combo.itemData(i, Qt.AccessibleDescriptionRole) != "separator"]


def test_the_bars_list_is_revus_order_then_ours(w):
    names = _names(w.dash_combo)
    assert names[0] == "Manage…"
    assert names[1:1 + len(REVU_ORDER)] == REVU_ORDER
    # CalcForge's own styles stay, after Revu's, under the keys files use
    keys = [w.dash_combo.itemData(i) for i in range(w.dash_combo.count())]
    for key in OLD_KEYS:
        assert key in keys, key
    assert keys.index("dash") > keys.index("road")


def test_no_name_is_cut_short_and_the_one_in_use_is_ticked(w):
    combo = w.dash_combo
    view = combo.view()
    delegate = view.itemDelegate()
    option = QStyleOptionViewItem()
    option.font = view.font()
    option.fontMetrics = view.fontMetrics()
    longest = max(view.fontMetrics().horizontalAdvance(combo.itemText(i))
                  for i in range(combo.count()))
    widest = max(delegate.sizeHint(option, combo.model().index(i, 0)).width()
                 for i in range(combo.count()))
    assert widest >= longest + delegate.SWATCH.width() + delegate.TICK
    assert view.minimumWidth() >= widest

    def row(index: int) -> QImage:
        image = QImage(widest, 40, QImage.Format_ARGB32)
        image.fill(QColor("#808080"))          # either theme's words show on it
        painter = QPainter(image)
        option.rect = image.rect()
        option.palette = view.palette()
        delegate.paint(painter, option, combo.model().index(index, 0))
        painter.end()
        return image.copy(0, 0, delegate.TICK - 4, 40)

    current = combo.findData("double")
    combo.setCurrentIndex(current)
    ticked, plain = row(current), row(combo.findData("road"))
    assert ticked != plain, "a tick at the left of the one in use, as Revu's"


def test_the_properties_panel_style_row_is_the_same_list(w):
    w.select_tool("rect")
    drag(w, page(w, 100, 100), page(w, 260, 200))
    (rect,) = markups(w, RectItem)
    select(w, rect)
    pump()
    combo = w.properties_panel.findChild(QComboBox, "lineStyle")
    assert combo is not None
    assert _names(combo)[1:1 + len(REVU_ORDER)] == REVU_ORDER


# ---------------------------------------------------------------------------
# drawn along every kind of path, inside the markup's box
# ---------------------------------------------------------------------------
def _kinds():
    return {
        "rect": lambda: RectItem("rect", QRectF(0, 0, 160, 90)),
        "ellipse": lambda: RectItem("ellipse", QRectF(0, 0, 160, 90)),
        "cloud": lambda: RectItem("cloud", QRectF(0, 0, 160, 90)),
        "line": lambda: PolyItem("line", [QPointF(0, 0), QPointF(170, 60)]),
        "polyline": lambda: PolyItem("polyline", [QPointF(0, 0), QPointF(80, 70),
                                                  QPointF(160, 10)]),
        "polygon": lambda: PolyItem("polygon", [QPointF(0, 0), QPointF(160, 20),
                                                QPointF(90, 100)]),
        "arc": lambda: PolyItem("arc", [QPointF(0, 60), QPointF(80, 0), QPointF(160, 60)]),
        "length": lambda: MeasureItem(LENGTH, [QPointF(0, 0), QPointF(170, 0)]),
        "text box": lambda: TextItem(),
    }


def _drawn(item, zoom: float = 1.0):
    """The markup painted on white, *zoom* times, and its box in the picture."""
    box = item.boundingRect()
    margin = 30
    image = QImage(int((box.width() + 2 * margin) * zoom),
                   int((box.height() + 2 * margin) * zoom), QImage.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.scale(zoom, zoom)
    painter.translate(margin - box.left(), margin - box.top())
    item.paint_visible(painter)
    painter.end()
    inside = QRectF(margin * zoom, margin * zoom, box.width() * zoom, box.height() * zoom)
    return image, inside


def _inked(image: QImage, step: int = 1) -> list:
    return [(x, y) for y in range(0, image.height(), step) for x in range(0, image.width(), step)
            if QColor(image.pixel(x, y)).lightness() < 235]


@pytest.mark.parametrize("name", complexlines.COMPLEX)
@pytest.mark.parametrize("kind", list(_kinds()))
def test_each_complex_style_is_drawn_and_stays_inside_the_box(qapp, name, kind):
    def made(style_name: str):
        item = _kinds()[kind]()
        item.style.stroke = "#000000"
        item.style.width = 2.0
        linestyles.apply(item.style, style_name)
        return item
    styled, solid = made(name), made("solid")
    image, inside = _drawn(styled)
    plain, _ = _drawn(solid)
    ink = _inked(image)
    assert ink, "something is drawn"
    outside = [p for p in ink if not inside.adjusted(-1, -1, 1, 1).contains(QPointF(*p))]
    assert not outside, f"{len(outside)} pixels outside the box"
    differ = sum(1 for y in range(0, min(image.height(), plain.height()), 2)
                 for x in range(0, min(image.width(), plain.width()), 2)
                 if (QColor(image.pixel(x, y)).lightness() < 200)
                 != (QColor(plain.pixel(x, y)).lightness() < 200))
    assert differ > 20, "not drawn as a plain solid line"
    # the hit-test reaches the widened line too
    assert styled.shape().boundingRect().width() > solid.shape().boundingRect().width()


@pytest.mark.parametrize("name", ["double", "tracks", "gas", "insulation"])
def test_drawn_inside_its_box_when_zoomed_in(qapp, name):
    item = RectItem("ellipse", QRectF(0, 0, 60, 40))
    item.style.stroke, item.style.width = "#000000", 3.0
    linestyles.apply(item.style, name)
    image, inside = _drawn(item, zoom=6.0)
    ink = _inked(image, 3)
    assert ink
    assert all(inside.adjusted(-6, -6, 6, 6).contains(QPointF(*p)) for p in ink)


def test_a_complex_line_grows_with_its_width(qapp):
    thin, thick = Style(line_style="double", width=1.0), Style(line_style="double", width=4.0)
    assert complexlines.reach(thick) > 3 * complexlines.reach(thin)
    assert complexlines.reach(Style(line_style="dash", width=4.0)) == 0.0
    # and its border in the PDF stays solid: it has no dashes of its own
    assert thick.dashes() == []


# ---------------------------------------------------------------------------
# picked from the bar, saved, opened again, and seen by another reader
# ---------------------------------------------------------------------------
def test_picked_from_the_bar_saved_reopened_and_drawn_by_mupdf(w, tmp_path):
    places = {}
    styles = list(complexlines.COMPLEX) + ["dashed 4", "long dash dot dot"]
    for index, name in enumerate(styles):
        x, y = 40 + (index % 3) * 180, 60 + (index // 3) * 130
        w.select_tool("rect")
        drag(w, page(w, x, y), page(w, x + 140, y + 80))
        places[name] = QRectF(x, y, 140, 80)
    rects = markups(w, RectItem)
    assert len(rects) == len(styles)
    w.select_tool("select")
    for name in styles:
        box = places[name]

        def the_rect(box=box):
            return next(r for r in markups(w, RectItem)
                        if abs(r.mapToScene(r.local_rect().topLeft()).x()
                               - page(w, box.x(), box.y()).x()) < 2
                        and abs(r.mapToScene(r.local_rect().topLeft()).y()
                                - page(w, box.x(), box.y()).y()) < 2)
        select(w, the_rect())
        one_undo_step(w, lambda name=name: pick(w.dash_combo, name),
                      lambda name=name, the_rect=the_rect: the_rect().style.line_style == name)
        rect = the_rect()
        rect.style.width = 2.0
        rect.update()
    # an older file's style is drawn as it was
    old = next(r for r in markups(w, RectItem) if r.style.line_style == "long dash dot dot")
    old_dashes = old.style.dashes()

    path = save_and_reopen(w, tmp_path)
    found = {r.style.line_style for r in markups(w, RectItem)}
    assert found == set(styles), "each one opens again as the same style"
    again = next(r for r in markups(w, RectItem) if r.style.line_style == "long dash dot dot")
    assert again.style.dashes() == old_dashes

    image = mupdf_page(path, zoom=2.0)
    image.save(str(tmp_path / "mupdf.png"))
    for name in complexlines.COMPLEX:
        box = places[name]
        # along the top side, clear of the corners: ink off the line's own
        # row (two rails, symbols, labels, loops), which a solid line has none of
        top = box.y() * 2
        rows = [int(top + d) for d in list(range(-16, -2)) + list(range(3, 17))]
        hits = sum(1 for y in rows for x in range(int(box.x() * 2 + 40),
                                                 int(box.right() * 2 - 40), 2)
                   if QColor(image.pixel(x, y)).lightness() < 200)
        assert hits > 6, f"{name} is drawn by another reader ({hits})"


# ---------------------------------------------------------------------------
# keys kept, and Bluebeam's names
# ---------------------------------------------------------------------------
def test_old_keys_still_load_as_they_were(qapp):
    expected = {"dash": [4.0, 2.0], "dashdot": [4.0, 2.0, 1.0, 2.0], "centre": [10.0, 2.5, 2.0, 2.5]}
    for key, dashes in expected.items():
        assert Style.from_dict({"line_style": key}).dashes() == dashes
    for key in OLD_KEYS:
        assert key in DASH_ARRAYS


def test_revus_names_in_a_tool_set_come_in_as_these_styles(qapp):
    from calcforge.io.btx import _style
    assert linestyles.named("Fenceline Circle") == "fenceline circle"
    assert linestyles.named("HotWater") == "hot water"
    assert linestyles.named("Zig Zag") == "zig zag"
    assert linestyles.named("WSP AUS - 140BW") == ""
    double = _style({"BS": {"W": 1.0, "S": "D", "D": [3, 3]}, "LineStyleName": "Double"})
    assert double["line_style"] == "double" and "dash_array" not in double
    dashed = _style({"BS": {"W": 1.0}, "LineStyleName": "Dashed 3",
                     "LineStyle": [False, [0, 5.5, -5.25]]})
    assert dashed["line_style"] == "dashed 3" and dashed["dash_array"] == (5.5, 5.25)
    theirs = _style({"BS": {"W": 1.0}, "LineStyleName": "WSP AUS - 140BW",
                     "LineStyle": [False, [0, 6, -2]]})
    assert theirs["line_style"] == "dash" and theirs["dash_array"] == (6.0, 2.0)
