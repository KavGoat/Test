"""The user's bug list of 2026-09-30 (after phase 8): the autocomplete list's
place, one insertion marker, panels that use their width, a properties bar
that stays put, fill and hatch opacity kept apart, and the page number
centred on the page view. Driven through the real window."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication

from tests.calc.test_calcforge_window import v  # noqa: F401
from tests.test_calc_modes import at, into_calc_mode
from tests.test_usability import click


# -- the autocomplete list sits under what is being typed ------------------------------

@pytest.mark.parametrize("x_px, y_px", [(36, 36), (400, 700)])
def test_the_autocomplete_list_opens_under_the_cursor(v, x_px, y_px):
    v.type_at(x_px, y_px, "")
    v.keys("si")
    s = v.suggestions
    assert s.isVisible()
    item = v.focused_item
    # where the caret is on the screen: just after the typed word, under it
    box = item.sceneBoundingRect()
    right_under = v.view.viewport().mapToGlobal(
        v.view.mapFromScene(QPointF(box.right(), box.bottom())))
    top_left = s.pos()
    assert abs(top_left.x() - right_under.x()) < 25, (top_left, right_under)
    assert -5 < top_left.y() - right_under.y() < 25, (top_left, right_under)


# -- one insertion marker ------------------------------------------------------------------

def test_calc_mode_shows_only_the_red_cross(window):
    from calcforge.ui import preferences

    window.show()
    prefs = preferences.current()
    was = prefs.insertion_point
    try:
        prefs.insertion_point = True             # MarkForge's blue insertion point on
        preferences.apply(prefs)
        into_calc_mode(window, 150, 200)
        assert window.view.calc.cross is not None, "the red cross is where typing starts"
        assert window.view._insertion_point is None, "and no blue one beside it"

        window.toggle_calc_mode(False)          # Markup mode: MarkForge's own marker
        p = at(window, 300, 400)
        click(window.view, p.x(), p.y())
        assert window.view._insertion_point is not None
        window.toggle_calc_mode(True)           # back in Calc mode it isn't drawn
        drawn = []
        window.view._draw_insertion_point = lambda painter, point: drawn.append(point)
        window.view.viewport().repaint()
        QApplication.instance().processEvents()
        assert drawn == []
    finally:
        prefs.insertion_point = was
        preferences.apply(prefs)


# -- panels use their width -------------------------------------------------------------

def _dock_at(window, name, width):
    from PySide6.QtCore import Qt as _Qt
    dock = getattr(window, name)
    for other in window.panels:
        other.hide()
    window.show_panel(name, True)
    window.resizeDocks([dock], [width], _Qt.Horizontal)
    for _ in range(4):
        QApplication.instance().processEvents()
    return dock


def test_the_maths_panel_flexes_with_its_width(window):
    """Every section reflows: more buttons to a row when wide, fewer when
    narrow, each row filled edge to edge (the user: "just make the whole
    thing flex")."""
    window.show()
    window.resize(1600, 900)
    panel = window.maths_panel
    seen = {}
    for width in (620, 230, 420):
        _dock_at(window, "dock_maths", width)
        for title in ("Arithmetic", "Functions"):
            section = panel.section(title)
            first_row = [b for b in section.buttons if b.y() == section.buttons[0].y()]
            span = first_row[-1].geometry().right() - first_row[0].geometry().left()
            assert span > panel.viewport().width() * 0.85, (title, width, span)
            seen[(title, width)] = len(first_row)
        assert panel.widget().width() <= panel.viewport().width(), "never wider than the panel"
    assert seen[("Arithmetic", 620)] > seen[("Arithmetic", 420)] > seen[("Arithmetic", 230)]
    assert seen[("Functions", 620)] > seen[("Functions", 230)]


def test_no_panel_scrolls_sideways_when_narrow(window):
    from PySide6.QtWidgets import QAbstractScrollArea
    window.show()
    window.resize(1600, 900)
    for name in window.PANEL_ICONS:
        dock = _dock_at(window, name, 230)
        sideways = [w for w in dock.widget().findChildren(QAbstractScrollArea)
                    if w.isVisible() and w.horizontalScrollBar().isVisible()]
        assert not sideways, name
        assert dock.widget().minimumSizeHint().width() <= 230, name


# -- the style bar and the three opacities ----------------------------------------------

def test_hatch_opacity_is_its_own_and_leaves_the_fill_alone(window):
    from PySide6.QtCore import QRectF
    from calcforge.items.shapes import RectItem
    window.show()
    frame = window.document.pages[0].frame
    box = RectItem("rect", QRectF(0, 0, 120, 80))
    frame.add_markup(box, QPointF(100, 100))
    box.style.fill, box.style.hatch = "#ffec99", "up"
    window.select_tool("select")
    box.setSelected(True)
    window.refresh_selection()
    fill, overall = box.style.fill_opacity, box.style.opacity
    window.hatch_opacity_spin.setValue(40)
    assert box.style.hatch_opacity == pytest.approx(0.4)
    assert box.style.fill_opacity == fill and box.style.opacity == overall, \
        "the hatch's opacity changes the hatch only"
    window.undo_stack.undo()
    (box,) = [i for i in frame.markups() if isinstance(i, RectItem)]   # undo rebuilds it
    assert box.style.hatch_opacity == pytest.approx(1.0)
    box.setSelected(True)
    window.refresh_selection()
    # each sits beside what it fades, and says what it is
    actions = [a for a in window.style_bar.actions() if a.isVisible()]
    widgets = [window.style_bar.widgetForAction(a) for a in actions]
    order = [w for w in widgets if w in (window.fill_button, window.fill_opacity_spin,
                                         window.hatch_combo, window.hatch_opacity_spin,
                                         window.opacity_spin)]
    assert order == [window.fill_button, window.fill_opacity_spin, window.hatch_combo,
                     window.hatch_opacity_spin, window.opacity_spin]
    for spin, word in ((window.fill_opacity_spin, "Fill"), (window.hatch_opacity_spin, "Hatch"),
                       (window.opacity_spin, "Overall")):
        assert spin.toolTip().startswith(word)


def test_a_hatch_is_drawn_at_its_own_opacity():
    from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath
    from calcforge.items.base import Style, paint_hatch

    def ink(style) -> int:
        image = QImage(60, 60, QImage.Format_ARGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        region = QPainterPath()
        region.addRect(0, 0, 60, 60)
        paint_hatch(painter, region, style)
        painter.end()
        return min(QColor(image.pixel(x, y)).lightness() for x in range(60) for y in range(60))

    solid = Style(hatch="up", hatch_color="#000000", hatch_scale=2.0)
    faint = Style(hatch="up", hatch_color="#000000", hatch_scale=2.0, hatch_opacity=0.3)
    assert ink(faint) > ink(solid) + 60, (ink(solid), ink(faint))


# -- the page number under the middle of the page view ------------------------------------

def test_the_page_number_is_centred_on_the_page_view(window):
    from PySide6.QtCore import QPoint
    window.show()
    window.resize(1900, 1000)

    def centres():
        for _ in range(6):
            QApplication.instance().processEvents()
        viewport, nav = window.view.viewport(), window.page_navigation
        return (viewport.mapToGlobal(QPoint(viewport.width() // 2, 0)).x(),
                nav.mapToGlobal(QPoint(nav.width() // 2, 0)).x())

    view, nav = centres()
    assert abs(view - nav) <= 2
    _dock_at(window, "dock_maths", 450)                  # a wide panel on the right
    view, nav = centres()
    assert abs(view - nav) <= 2


# -- "=" always types ------------------------------------------------------------------------

def test_a_definition_can_show_its_value(v):
    """t:=test+1= — SMath Studio desktop defines and shows the value."""
    from calcforge.calc.engine.display import display_text
    for y, keys in ((18, "test:2"), (60, "t:test+1="), (110, "x:2'm+3'm=")):
        v.type_at(36, y, "")
        v.keys(keys)
        item = v.focused_item
        v.press(Qt.Key_Return)
        assert item.text().endswith("=") == keys.endswith("="), keys
    made = sorted(v.items.values(), key=lambda i: i.region.y)
    assert display_text(made[1].region.display) == "3"
    assert display_text(made[2].region.display) == "5 m"


@pytest.mark.parametrize("name", ["t", "m", "s", "g", "A", "h", "L"])
def test_equals_and_define_type_after_any_name(v, name):
    """Names that are also units (t tonne, m metre, s second...) used to
    block = and : until a choice was made from the list."""
    v.type_at(36, 18, "")
    v.keys(f"{name}:4")
    v.press(Qt.Key_Return)
    v.type_at(36, 72, "")
    v.keys(f"{name}*2=")
    item = v.focused_item
    v.press(Qt.Key_Return)
    from calcforge.calc.engine.display import display_text
    assert item.text() == f"{name}·2=" or item.text().endswith("="), item.text()
    assert display_text(item.region.display) == "8"


# -- the caret while typing a unit --------------------------------------------------------

def _caret_pixels(item, colour):
    from PySide6.QtGui import QColor, QImage, QPainter
    rect = item.boundingRect()
    image = QImage(int(rect.width() * 6) + 8, int(rect.height() * 6) + 8, QImage.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.scale(6, 6)
    painter.translate(-rect.topLeft())
    item.paint_visible(painter)
    painter.end()
    want = QColor(colour)
    return sum(1 for x in range(image.width()) for y in range(image.height())
               if QColor(image.pixel(x, y)).blue() > 200 and QColor(image.pixel(x, y)).red() < 60
               and QColor(image.pixel(x, y)).green() < 60) if colour == "blue" else None


def test_the_caret_turns_blue_in_a_unit(v):
    v.type_at(36, 36, "")
    v.keys("x:2")
    item = v.focused_item
    plain = _caret_pixels(item, "blue")
    v.keys("'")
    after_apostrophe = _caret_pixels(item, "blue")
    assert after_apostrophe > plain, "from the ' on, the caret says a unit is being typed"


def test_the_caret_stands_clear_of_the_last_letter(v):
    v.type_at(36, 36, "")
    v.keys("x")
    item = v.focused_item
    view = item._view
    info = view._row_info(item.editor.row)
    end_of_text = info.slots[-1]
    drawn = []

    class Spy:
        def __init__(self, painter):
            self.p = painter

        def __getattr__(self, name):
            return getattr(self.p, name)

        def drawLine(self, a, b):
            drawn.append((a, b))
            return self.p.drawLine(a, b)

    from PySide6.QtGui import QImage, QPainter
    image = QImage(200, 100, QImage.Format_ARGB32)
    painter = QPainter(image)
    view._paint_cursor(Spy(painter))
    painter.end()
    bar = [a for a, b in drawn if a.x() == b.x()][0]
    assert bar.x() >= end_of_text + 1


# -- the properties toolbar, per markup type (as Bluebeam's) -------------------------------

def _bar_fields(window):
    return {field for field, actions in window._style_widgets.items()
            if any(a.isVisible() for a in actions)}


def _select(window, item):
    window.select_tool("select")
    window.view.scene().clearSelection()
    item.setSelected(True)
    window.refresh_selection()


def test_the_toolbar_shows_each_types_own_controls(window):
    from PySide6.QtCore import QRectF
    from calcforge.items.measure import CountItem, MeasureItem
    from calcforge.items.shapes import PolyItem, RectItem
    from calcforge.items.text import TextItem
    from calcforge.ui.stylecaps import (ARROW_SIZE, CLOUD, CORNER, DASH, FILL, FONT,
                                        HATCH, OPACITY, STROKE, SYMBOL)
    window.show()
    frame = window.document.pages[0].frame
    cloud = RectItem("cloud", QRectF(0, 0, 120, 60))
    box = RectItem("rect", QRectF(0, 0, 120, 60))
    highlight = RectItem("highlight", QRectF(0, 0, 120, 20))
    text = TextItem("Words", QRectF(0, 0, 120, 30))
    count = CountItem()
    area = MeasureItem("area", [QPointF(0, 0), QPointF(80, 0), QPointF(80, 50)])
    for y, item in enumerate((cloud, box, highlight, text, count, area)):
        frame.add_markup(item, QPointF(80, 60 + 80 * y))
    _select(window, cloud)
    assert CLOUD in _bar_fields(window) and CORNER not in _bar_fields(window)
    assert window.style_kind_label.text().strip() == "Cloud"
    _select(window, box)
    assert CORNER in _bar_fields(window) and CLOUD not in _bar_fields(window)
    _select(window, highlight)
    assert _bar_fields(window) == {FILL, "fill_opacity", OPACITY}
    _select(window, count)
    assert SYMBOL in _bar_fields(window) and DASH not in _bar_fields(window)
    assert HATCH not in _bar_fields(window)
    _select(window, area)
    assert ARROW_SIZE not in _bar_fields(window)
    _select(window, text)
    bar = window.style_bar
    visible = [a for a in bar.actions() if a.isVisible()]
    first_font = min(visible.index(a) for a in window._style_widgets[FONT] if a.isVisible())
    first_line = min(visible.index(a) for a in window._style_widgets[STROKE] if a.isVisible())
    assert first_font < first_line, "words first for anything with words in it, as Bluebeam"


def test_the_cloud_arc_is_set_from_the_toolbar_and_for_new_clouds(window):
    from PySide6.QtCore import QRectF
    from calcforge.items.shapes import RectItem
    window.show()
    frame = window.document.pages[0].frame
    cloud = RectItem("cloud", QRectF(0, 0, 120, 60))
    frame.add_markup(cloud, QPointF(100, 100))
    _select(window, cloud)
    window.cloud_spin.setValue(18.0)
    assert cloud.cloud_radius == pytest.approx(18.0)
    window.undo_stack.undo()
    (cloud,) = [i for i in frame.markups() if isinstance(i, RectItem)]
    assert cloud.cloud_radius == pytest.approx(9.0)
    # nothing selected, the cloud tool in hand: the next cloud's arcs
    window.view.scene().clearSelection()
    window.select_tool("cloud")
    window.refresh_selection()
    assert window.style_kind_label.text().strip() == "New cloud"
    window.cloud_spin.setValue(24.0)
    made = RectItem("cloud", QRectF(0, 0, 50, 50))
    window.apply_default_style(made)
    assert made.cloud_radius == pytest.approx(24.0)


def test_count_symbol_and_corner_radius_from_the_toolbar(window):
    from PySide6.QtCore import QRectF
    from calcforge.items.measure import CountItem
    from calcforge.items.shapes import RectItem
    window.show()
    frame = window.document.pages[0].frame
    count = CountItem()
    box = RectItem("rect", QRectF(0, 0, 120, 60))
    frame.add_markup(count, QPointF(100, 100))
    frame.add_markup(box, QPointF(300, 100))
    _select(window, count)
    window.symbol_combo.setCurrentText("star")
    assert count.symbol == "star"
    _select(window, box)
    window.corner_spin.setValue(6.0)
    assert box.style.corner_radius == pytest.approx(6.0)
