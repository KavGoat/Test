"""The Variable boxes type and look as SMath writes a name (the user,
2026-10-16): the measurement's and the cell's, at the top of their
right-click menus, and the measurement's in the Properties panel.

Typed with real keys into the real menu: L . b e a m and Enter names the
measurement L.beam — drawn L with "beam" as its subscript, in the
equation's own maths — and an equation reads L.beam. No units, operators
or spaces go in; Greek comes from the Greek-letter keys, as in an equation.
"""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calcforge.calc.engine.display import display_text  # noqa: E402
from calcforge.items.measure import LENGTH, MeasureItem  # noqa: E402
from calcforge.ui.namebox import SMathNameEdit  # noqa: E402
from tests.test_tables import cell_scene, make_table, pump, w  # noqa: E402,F401


def right_click(view, point):
    local = view.mapFromScene(point)
    QApplication.sendEvent(view.viewport(), QContextMenuEvent(
        QContextMenuEvent.Mouse, local, view.viewport().mapToGlobal(local)))


def a_length(w):
    frame = w.document.pages[0].frame
    item = MeasureItem(LENGTH, [QPointF(0, 0), QPointF(200, 0)])
    w.view.begin_snapshot([frame])
    frame.add_markup(item, QPointF(150, 300))
    w.view.commit_snapshot("Measure")
    return item


def type_into_the_menu(name, keys, seen):
    """When the menu is up: its Variable box, typed into key by key."""
    def step():
        popup = QApplication.activePopupWidget()
        if popup is None:
            QTimer.singleShot(40, step)
            return
        field = popup.findChild(QLineEdit, name)
        seen["field_class"] = type(field).__name__
        for key in keys:
            if isinstance(key, str):
                QTest.keyClicks(field, key)
            else:
                QTest.keyClick(field, *key) if isinstance(key, tuple) else QTest.keyClick(field, key)
        seen["text"] = field.text()
        seen["picture"] = field.grab()
        QTest.keyClick(field, Qt.Key_Return)
    QTimer.singleShot(60, step)


def test_a_measurements_variable_is_typed_as_smath_does(w):
    from tests.test_calc_panels import an_equation
    measure = a_length(w)
    seen = {}
    type_into_the_menu("measureVariable", ["L", ".", "b", "e", "a", "m"], seen)
    right_click(w.view, measure.sceneBoundingRect().center())
    pump()
    assert seen["field_class"] == "SMathNameEdit"
    assert seen["text"] == "L.beam"
    assert measure.variable == "L.beam", "the name the calcs read"
    use = an_equation(w, "L.beam=", y=500)
    assert "not defined" not in display_text(use.region.display or "") and \
        use.region.error is None


def test_the_box_draws_the_name_with_its_subscript():
    box = SMathNameEdit("L.beam")
    box.resize(160, 30)
    lay = box._item._layout
    texts = []

    def walk(node):
        if getattr(node, "text", None):
            texts.append((node.text, node.font.pointSizeF(), node.font.italic()))
        for child in getattr(node, "children", None) or []:
            walk(child)
    walk(lay)
    joined = "".join(t for t, _s, _i in texts)
    assert joined.replace(" ", "") == "Lbeam"
    sizes = {t: size for t, size, _ in texts}
    assert any(size < sizes.get("L", 99) for t, size in sizes.items() if t != "L"), \
        "beam is drawn smaller, as a subscript"
    assert all(italic for _t, _s, italic in texts), "an equation's name: italic maths"


def test_only_a_name_goes_in():
    box = SMathNameEdit("")
    box.show()
    box.setFocus()
    for key in ("2", "x", "'", "+", " ", "m", ".", "1", ".", "2"):
        QTest.keyClicks(box, key)
    assert box.text() == "xm.12", "no leading digit, no unit, operator, space or second ."
    QTest.keyClick(box, Qt.Key_Backspace)
    assert box.text() == "xm.1"
    box.close()


def test_greek_comes_from_the_greek_keys(w):
    measure = a_length(w)
    seen = {}
    type_into_the_menu("measureVariable",
                       [(Qt.Key_F, Qt.ControlModifier | Qt.AltModifier), ".", "R", "d"], seen)
    right_click(w.view, measure.sceneBoundingRect().center())
    pump()
    assert seen["text"] == "φ.Rd"
    assert measure.variable == "φ.Rd"


def test_a_cells_variable_is_typed_as_smath_does(w):
    table = make_table(w)
    tables = w.view.tables
    tables.open(table, (1, 1))
    seen = {}
    type_into_the_menu("cellVariable", ["W", ".", "t", "o", "t"], seen)
    right_click(w.view, cell_scene(table, "B2"))
    pump()
    assert seen["field_class"] == "SMathNameEdit"
    workbook = table.sheet.workbook
    name = workbook.find_name("W.tot", None)
    assert name is not None and name.refers_to.replace("$", "").endswith("!B2")


def test_the_properties_panel_box_is_the_same(w):
    measure = a_length(w)
    w.view.scene().clearSelection()
    measure.setSelected(True)
    w.refresh_selection()
    field = w.properties_panel.findChild(QLineEdit, "measureVariable")
    assert isinstance(field, SMathNameEdit)
    QTest.mouseClick(field, Qt.LeftButton)
    QTest.keyClicks(field, "L.b")
    QTest.keyClick(field, Qt.Key_Return)
    pump()
    assert measure.variable == "L.b"


# -- the user's review, 2026-10-16: the name sits in the middle, full size ----------------------
def _ink_columns(image, top, bottom, left, right):
    """Runs of columns holding dark ink, each with its first and last row."""
    def dark(x, y):
        colour = image.pixelColor(x, y)
        return colour.lightness() < 120
    runs, start = [], None
    for x in range(left, right):
        inked = any(dark(x, y) for y in range(top, bottom))
        if inked and start is None:
            start = x
        if not inked and start is not None:
            runs.append((start, x))
            start = None
    out = []
    for a, b in runs:
        rows = [y for y in range(top, bottom) if any(dark(x, y) for x in range(a, b))]
        out.append((a, b, min(rows), max(rows)))
    return out


def test_the_name_is_centred_full_size_and_never_clipped(w):
    from PySide6.QtGui import QFontMetricsF
    measure = a_length(w)
    w.set_measure_variable(measure, "L.beam")
    menu = w.build_context_menu(measure, measure.sceneBoundingRect().center())
    field = menu.findChild(QLineEdit, "measureVariable")
    menu.popup(w.mapToGlobal(w.rect().center()))
    pump()
    field.clearFocus()
    pump()
    image = field.grab().toImage()
    height = image.height()
    glyphs = _ink_columns(image, 2, height - 2, 3, image.width() - 3)
    assert glyphs, "the name is drawn"
    base, subscript = glyphs[0], glyphs[1:]
    ink_top = min(g[2] for g in glyphs)
    ink_bottom = max(g[3] for g in glyphs)
    assert ink_top >= 4 and ink_bottom <= height - 5, "clear of the box's top and bottom"
    above, below = ink_top, height - 1 - ink_bottom
    assert abs(above - below) <= 3, "in the middle of the box"
    l_height = base[3] - base[2] + 1
    assert all(l_height >= g[3] - g[2] + 1 for g in subscript), "L is at least as tall as beam"
    assert all(g[3] > base[3] for g in subscript), "the subscript drops below the base line"
    words = QFontMetricsF(field.font()).capHeight()
    assert abs(l_height - words) <= 1.5, "L is the size of the menu's own capitals"
    menu.hide()
