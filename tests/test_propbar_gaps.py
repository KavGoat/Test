"""The Properties toolbar's gaps against Revu 21 (docs/qa/findings.md, round 6),
closed and driven the way a person drives them: markups drawn with the mouse,
the toolbar's own controls clicked or keyed, the Properties panel's buttons
pressed — then one undo step, saved and opened again, and the saved PDF drawn
by MuPDF, which is how another reader sees it.

- 6.1 an area's and a rectangle's Line colour: Revu's framed swatch
- 6.2 an area measurement's hatch
- 6.3 a callout's "A": Revu's Auto font size
- 6.4 a cloud's scallops in the line-style box, and its intensity ▾
- 6.5 Units ▾ for the measurement itself; Caption ▾'s values
- 6.6 strikethrough, superscript, subscript; line-style Manage…; a size for
  each line end
"""
from __future__ import annotations

import pymupdf
import pytest
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QDoubleSpinBox, QToolButton

from calcforge.items.measure import AREA, LENGTH, MeasureItem
from calcforge.items.shapes import PolyItem, RectItem
from calcforge.items.text import CalloutItem, TextItem


# ---------------------------------------------------------------------------
# a person's hands
# ---------------------------------------------------------------------------
@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    pump()
    return window


def pump(times: int = 3) -> None:
    for _ in range(times):
        QApplication.instance().processEvents()


def page(w, x, y) -> QPointF:
    return w.document.pages[0].frame.mapToScene(QPointF(x, y))


def at(w, point: QPointF) -> QPoint:
    return w.view.mapFromScene(point)


def click(w, point: QPointF) -> None:
    QTest.mouseClick(w.view.viewport(), Qt.LeftButton, Qt.NoModifier, at(w, point))
    pump()


def drag(w, start: QPointF, end: QPointF) -> None:
    viewport = w.view.viewport()
    QTest.mousePress(viewport, Qt.LeftButton, Qt.NoModifier, at(w, start))
    for step in (0.3, 0.6, 1.0):
        QTest.mouseMove(viewport, at(w, start + (end - start) * step))
    QTest.mouseRelease(viewport, Qt.LeftButton, Qt.NoModifier, at(w, end))
    pump()


def key(w, which, modifiers=Qt.NoModifier, widget=None) -> None:
    QTest.keyClick(widget or w.view, which, modifiers)
    pump()


def press(widget) -> None:
    """A click in the middle of a toolbar or panel button."""
    assert widget.isVisible(), widget.objectName()
    QTest.mouseClick(widget, Qt.LeftButton)
    pump()


def pick(combo: QComboBox, data, stays: bool = True) -> None:
    """Open the list and click the entry, as a person picks from a list."""
    assert combo.isVisible(), combo.objectName()
    index = combo.findData(data)
    assert index >= 0, (combo.objectName(), data)
    combo.showPopup()
    pump()
    view = combo.view()
    view.scrollTo(view.model().index(index, 0))
    pump()
    rect = view.visualRect(view.model().index(index, 0))
    QTest.mouseClick(view.viewport(), Qt.LeftButton, Qt.NoModifier, rect.center())
    pump()
    if view.isVisible():                      # some styles need the release too
        combo.hidePopup()
    if stays:
        assert combo.currentIndex() == index, (combo.objectName(), data)


def menu_click(menu, action) -> None:
    """Click an entry of an open menu where it is drawn."""
    assert menu.isVisible() and action.isVisible() and action.isEnabled(), action.text()
    QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier, menu.actionGeometry(action).center())
    pump()


def shown_on_bar(w, widget) -> bool:
    bar = w.style_bar
    return any(a.isVisible() and bar.widgetForAction(a) is widget for a in bar.actions())


def markups(w, kind):
    return [i for i in w.view.scene().ordered_markups() if isinstance(i, kind)]


def select(w, item) -> None:
    """Click the markup, with the Select tool, where it is drawn."""
    w.select_tool("select")
    w.view.scene().clearSelection()
    box = item.mapRectToScene(item.local_rect())
    target = box.center()
    if isinstance(item, (PolyItem,)) or (isinstance(item, MeasureItem) and not item.closed):
        target = item.mapToScene((item.points[0] + item.points[1]) / 2)
    elif isinstance(item, MeasureItem):
        target = item.mapToScene(item.points[0]) + QPointF(12, 12)
    click(w, target)
    if not item.isSelected():
        item.setSelected(True)
        w.refresh_selection()
        pump()
    assert w.selected_items() == [item]


def one_undo_step(w, change, check):
    before = w.undo_stack.index()
    change()
    assert w.undo_stack.index() == before + 1, "one undo step"
    assert check()
    w.undo_stack.undo()
    pump()
    assert not check(), "undone in one step"
    w.undo_stack.redo()
    pump()
    assert check()


def save_and_reopen(w, tmp_path, name="out.pdf") -> str:
    path = str(tmp_path / name)
    w.document.path = path
    assert w.save_document()
    w.open_from_command_line(path)
    w.view.set_zoom(1.0)
    pump()
    return path


def mupdf_page(path, zoom=2.0) -> QImage:
    """The saved file's first page as MuPDF draws it: what another reader sees."""
    with pymupdf.open(path) as document:
        picture = document[0].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), annots=True)
        return QImage(picture.samples, picture.width, picture.height, picture.stride,
                      QImage.Format_RGB888).copy()


def ink_in(image: QImage, rect: QRectF, test) -> float:
    """The share of the pixels inside *rect* that pass *test*."""
    hits = total = 0
    for y in range(int(rect.top()), int(rect.bottom())):
        for x in range(int(rect.left()), int(rect.right()), 2):
            total += 1
            hits += bool(test(QColor(image.pixel(x, y))))
    return hits / max(total, 1)


def scaled(w, ratio=100):
    from calcforge.core.document import PageScale
    w.current_page().scale = PageScale.from_ratio(ratio)
    return w.current_page()


def draw_area(w, corners=((150, 300), (400, 300), (400, 480), (150, 480))):
    w.select_tool("measure_area")
    for x, y in corners:
        click(w, page(w, x, y))
    key(w, Qt.Key_Return)
    w.select_tool("select")
    pump()
    (area,) = markups(w, MeasureItem)
    return area


# ---------------------------------------------------------------------------
# 6.1 — Line: a framed colour swatch, as Revu's
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("kind", ["area", "sketch_rect"])
def test_line_colour_is_a_framed_swatch_that_sets_the_line(w, kind):
    from calcforge.ui import colorpicker
    scaled(w)
    if kind == "area":
        item = draw_area(w)
    else:
        w.select_tool("sketch_rect")
        drag(w, page(w, 150, 300), page(w, 400, 480))
        w.select_tool("select")
        (item,) = markups(w, RectItem)
    select(w, item)
    button = w.stroke_button
    assert shown_on_bar(w, button)
    assert button.property("revuSwatch") is True
    # it sits straight after "Line:"
    bar = w.style_bar
    visible = [bar.widgetForAction(a) for a in bar.actions() if a.isVisible()]
    index = visible.index(button)
    assert getattr(visible[index - 1], "text", lambda: "")() == "Line:"

    def change():
        colorpicker.ANSWERS.append("#ff8800")
        press(button)

    def found():
        return markups(w, type(item))[0]
    one_undo_step(w, change, lambda: found().style.stroke == "#ff8800")


# ---------------------------------------------------------------------------
# 6.2 — an area measurement takes a hatch
# ---------------------------------------------------------------------------
def test_an_area_is_hatched_from_the_bar_saved_and_seen_by_other_readers(w, tmp_path):
    scaled(w)
    area = draw_area(w)
    select(w, area)
    assert shown_on_bar(w, w.hatch_combo), "Revu's area has a Hatch ▾"

    def the_area():
        return markups(w, MeasureItem)[0]
    one_undo_step(w, lambda: pick(w.hatch_combo, "horizontal"),
                  lambda: the_area().style.hatch == "horizontal")
    area = the_area()
    region = area.hatch_region()
    assert region is not None and not region.isEmpty()
    # the Properties panel offers it too
    w.view.scene().clearSelection()
    select(w, area)
    assert w.properties_panel.findChild(QComboBox, "hatchPattern") is not None

    # drawn on the page: dark hatch lines inside the area, none before
    def hatch_share(item) -> float:
        box = item.local_rect()
        image = QImage(int(box.width()) + 20, int(box.height()) + 20, QImage.Format_ARGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        painter.translate(10 - box.left(), 10 - box.top())
        item.paint_visible(painter)
        painter.end()
        inside = QRectF(30, 30, box.width() - 40, box.height() * 0.3)   # clear of the words
        return ink_in(image, inside, lambda c: c.lightness() < 200)
    assert hatch_share(area) > 0.03
    plain = MeasureItem(AREA, list(area.points))
    assert hatch_share(plain) < 0.01

    path = save_and_reopen(w, tmp_path)
    (again,) = markups(w, MeasureItem)
    assert again.style.hatch == "horizontal"
    assert again.hatch_region() is not None
    # MuPDF draws the hatch from the saved file
    image = mupdf_page(path)
    inside = QRectF(170 * 2, 320 * 2, 210 * 2, 140 * 2)
    assert ink_in(image, inside, lambda c: c.lightness() < 200) > 0.03
    with pymupdf.open(path) as document:
        annotation = next(document[0].annots())
        assert "/Pattern" in document.xref_object(annotation.xref)


# ---------------------------------------------------------------------------
# 6.3 — a callout's "A": Revu's Auto font size
# ---------------------------------------------------------------------------
def test_a_callouts_auto_font_size_fills_its_box(w, tmp_path):
    frame = w.document.pages[0].frame
    callout = CalloutItem("Fix here", QRectF(0, 0, 160, 60), [QPointF(-60, 90)])
    w.view.begin_snapshot([frame])
    frame.add_markup(callout, QPointF(250, 300))
    w.view.commit_snapshot("Callout")
    select(w, callout)
    assert shown_on_bar(w, w.font_auto_button)
    # straight after the font size, as Revu's
    bar = w.style_bar
    visible = [bar.widgetForAction(a) for a in bar.actions() if a.isVisible()]
    assert visible.index(w.font_auto_button) == visible.index(w.font_spin) + 1
    before = callout.style.font_size

    def the_callout():
        return markups(w, CalloutItem)[0]
    one_undo_step(w, lambda: press(w.font_auto_button),
                  lambda: the_callout().style.font_auto)
    callout = the_callout()
    assert callout.style.font_size > before + 4, "the words grow to fill the box"
    assert callout.doc.size().height() <= callout.text_rect().height() + 0.5
    assert w.font_spin.value() == pytest.approx(callout.style.font_size)
    assert w.font_auto_button.isChecked()
    # more words: the size comes down to keep them in the box
    big = callout.style.font_size
    callout.set_text("Fix here, and here, and over there by the door")
    assert callout.style.font_size < big
    assert callout.doc.size().height() <= callout.text_rect().height() + 0.5
    # a bigger box: bigger words
    small = callout.style.font_size
    callout.set_local_rect(QRectF(0, 0, 320, 120))
    assert callout.style.font_size > small
    # saved and opened: still Auto, at the size it came to
    size = callout.style.font_size
    path = save_and_reopen(w, tmp_path)
    (again,) = markups(w, CalloutItem)
    assert again.style.font_auto and again.style.font_size == pytest.approx(size, abs=0.11)
    with pymupdf.open(path) as document:
        annotation = next(document[0].annots())
        said = document.xref_object(annotation.xref)
        assert f"{size:g}pt" in said, "the size it came to is the size other readers use"
        text = document[0].get_text()
    # a size picked from the list turns Auto off, as Revu's does
    select(w, again)
    w.font_spin.setFocus()
    key(w, Qt.Key_Down, widget=w.font_spin)
    (again,) = markups(w, CalloutItem)
    assert not again.style.font_auto
    assert not w.font_auto_button.isChecked()
    assert text is not None


def test_the_properties_panel_has_revus_auto_beside_the_size(w):
    from PySide6.QtWidgets import QCheckBox
    frame = w.document.pages[0].frame
    box = TextItem("Words", QRectF(0, 0, 200, 80))
    frame.add_markup(box, QPointF(200, 300))
    select(w, box)
    auto = w.properties_panel.findChild(QCheckBox, "fontAutoPanel")
    assert auto is not None and not auto.isChecked()
    press(auto)
    (box,) = markups(w, TextItem)
    assert box.style.font_auto and box.style.font_size > 20


# ---------------------------------------------------------------------------
# 6.4 — a cloud: scallops in the line-style box, and Revu's intensity ▾
# ---------------------------------------------------------------------------
def _rows_inked(icon) -> int:
    image = icon.pixmap(150, 34).toImage()
    return sum(1 for y in range(image.height())
               if any(QColor.fromRgba(image.pixel(x, y)).alpha() > 60
                      for x in range(image.width())))


def test_a_clouds_line_style_shows_scallops_and_its_intensity_is_a_list(w, tmp_path):
    from calcforge.ui.propbar import CLOUD_SIZES, CloudSizeCombo
    w.select_tool("cloud")
    drag(w, page(w, 150, 300), page(w, 400, 450))
    w.select_tool("select")
    (cloud,) = [i for i in markups(w, (RectItem, PolyItem)) if i.kind == "cloud"]
    select(w, cloud)
    combo = w.dash_combo
    assert combo.property("cloudStyles") is True
    scallops = _rows_inked(combo.itemIcon(combo.currentIndex()))
    # a plain line is a few rows of ink; the scallops stand much taller
    box = RectItem("rect", QRectF(0, 0, 50, 50))
    w.document.pages[0].frame.add_markup(box, QPointF(500, 600))
    select(w, box)
    assert combo.property("cloudStyles") is False
    plain = _rows_inked(combo.itemIcon(combo.currentIndex()))
    assert scallops > plain * 2
    select(w, cloud)
    intensity = w.cloud_spin
    assert isinstance(intensity, CloudSizeCombo) and shown_on_bar(w, intensity)
    assert intensity.isEditable() is False
    assert [intensity.itemData(i) for i in range(len(CLOUD_SIZES))] == list(CLOUD_SIZES)
    # the intensity is straight after the line style, as Revu's ≋ ▾
    bar = w.style_bar
    visible = [bar.widgetForAction(a) for a in bar.actions() if a.isVisible()]
    assert visible.index(intensity) == visible.index(combo) + 1

    def the_cloud():
        return [i for i in markups(w, (RectItem, PolyItem)) if i.kind == "cloud"][0]
    one_undo_step(w, lambda: pick(intensity, 3.0),
                  lambda: the_cloud().cloud_size == pytest.approx(3.0))
    # a size set in the Properties panel shows on the list too
    panel_size = w.properties_panel.findChild(QDoubleSpinBox, "cloudSize")
    assert panel_size is not None
    panel_size.setValue(3.3)
    pump()
    w.refresh_selection()
    assert intensity.value() == pytest.approx(3.3)
    assert intensity.currentText() == "Size 3.3"
    path = save_and_reopen(w, tmp_path)
    again = [i for i in markups(w, (RectItem, PolyItem)) if i.kind == "cloud"][0]
    assert again.cloud_size == pytest.approx(3.3)
    with pymupdf.open(path) as document:
        clouds = [a for a in document[0].annots()
                  if "/BE" in document.xref_object(a.xref)]
        assert clouds and "/I 3.3" in document.xref_object(clouds[0].xref)


# ---------------------------------------------------------------------------
# 6.5 — Units ▾ for this measurement; Caption ▾'s values
# ---------------------------------------------------------------------------
def test_units_are_the_measurements_own_saved_and_shown(w, tmp_path):
    scaled(w, 100)
    w.select_tool("measure_length")
    drag(w, page(w, 150, 300), page(w, 350, 300))
    w.select_tool("select")
    (length,) = markups(w, MeasureItem)
    metres = length.value.to("m").magnitude
    assert length.value_text.endswith(" m")
    select(w, length)
    assert shown_on_bar(w, w.units_button)
    press(w.units_button)
    assert w.units_popup.isVisible()
    assert w.units_length_combo.isVisible() and not w.units_area_combo.isVisible()
    assert w.units_length_combo.itemText(0) == "Page (m)"

    def the_length():
        return markups(w, MeasureItem)[0]

    def to_mm():
        w.units_length_combo.setCurrentIndex(w.units_length_combo.findData("mm"))
        w.units_length_combo.activated.emit(w.units_length_combo.currentIndex())
        pump()
    one_undo_step(w, to_mm, lambda: the_length().value_text.endswith(" mm"))
    w.units_popup.hide()
    length = the_length()
    assert w.current_page().scale.display_unit == "m", "the page keeps its own units"
    # (the same length: undo and redo keep its points to a thousandth)
    assert length.value.to("m").magnitude == pytest.approx(metres, rel=1e-4)
    assert float(length.measured_text.split()[0]) == pytest.approx(metres * 1000, rel=1e-4)
    # "Page" puts it back on the page's units
    select(w, length)
    press(w.units_button)
    w.units_length_combo.setCurrentIndex(0)
    w.units_length_combo.activated.emit(0)
    pump()
    w.units_popup.hide()
    assert the_length().value_text.endswith(" m") and not the_length().units
    w.undo_stack.undo()
    pump()
    text = the_length().value_text
    assert text.endswith(" mm")
    path = save_and_reopen(w, tmp_path)
    (again,) = markups(w, MeasureItem)
    assert again.units == {"length": "mm"} and again.value_text == text
    # another reader is shown it in millimetres: the words are in the drawing
    with pymupdf.open(path) as document:
        annotation = next(document[0].annots())
        assert "mm" in (annotation.info.get("content", "") + document[0].get_text())


def test_a_measurement_variable_keeps_its_value_whatever_it_is_shown_in(qapp):
    """tests/test_measure_variables: the variable is the quantity, so an
    equation's answer is the same length whether it is shown in m or mm."""
    from calcforge.core.units import parse_unit
    from tests.test_calc_blocks import settle, shown
    from tests.test_measure_variables import a_length, type_line
    from calcforge.ui.mainwindow import MainWindow
    import tests.calc.test_calcforge_window as cw
    window = MainWindow()
    window.confirm_discard = lambda: True
    window.interactive_prompts = False
    window.resize(1280, 860)
    window.show()
    v = cw.Sheet(window)
    try:
        measure = a_length(v)
        assert v.window.set_measure_variable(measure, "L.b")
        use = type_line(v, 400, "L.b*2=")
        first = parse_unit(shown(use).replace(" ", ""))
        measure.set_unit("length", "mm")
        measure.refresh()
        settle(v.window)
        then = parse_unit(shown(use).replace(" ", ""))
        assert then.to("m").magnitude == pytest.approx(first.to("m").magnitude, rel=1e-3)
        assert measure.value_text.startswith("L.b = ") and measure.value_text.endswith("mm")
    finally:
        window.document.modified = False
        window.close()
        window.deleteLater()


def test_caption_offers_revus_values_for_an_area(w, tmp_path):
    scaled(w, 100)
    area = draw_area(w)
    select(w, area)
    press(w.caption_button)
    menu = w.caption_button.popup_menu
    assert menu.isVisible()
    actions = w.caption_part_actions
    assert [p for p, a in actions.items() if a.isVisible()] == [
        "label", "area", "perimeter", "volume", "wall_area"]
    assert actions["area"].isChecked() and not actions["perimeter"].isChecked()
    assert not actions["volume"].isEnabled(), "a volume needs a depth"

    def the_area():
        return markups(w, MeasureItem)[0]
    one_undo_step(w, lambda: menu_click(menu, actions["perimeter"]),
                  lambda: "P = " in the_area().value_text)
    menu.hide()
    area = the_area()
    lines = area.value_text.split("\n")
    assert lines[0].startswith("A = ") and lines[1].startswith("P = ")
    # its perimeter, worked out from its corners at 1:100
    import math
    points = area.points
    around = sum(math.dist((a.x(), a.y()), (b.x(), b.y()))
                 for a, b in zip(points, points[1:] + points[:1]))
    metres = around * 100 * 25.4 / 72 / 1000
    assert float(lines[1].split()[2]) == pytest.approx(metres, abs=0.01)
    assert 29 < metres < 31
    # with a depth, volume and wall area come in
    area.depth_text = "2.5 m"
    area.refresh()
    select(w, area)
    press(w.caption_button)
    assert actions["volume"].isEnabled() and actions["wall_area"].isEnabled()
    menu_click(menu, actions["wall_area"])
    menu.hide()
    area = the_area()
    assert "WA = " in area.value_text
    assert area.value.to("m**2").magnitude == pytest.approx(55, rel=0.05), \
        "the measurement's own value is still its area"
    # its label on the caption, as Revu shows it
    area.label = "Slab 1"
    select(w, area)
    press(w.caption_button)
    menu_click(menu, actions["label"])
    menu.hide()
    assert the_area().value_text.split("\n")[0] == "Slab 1"
    text = the_area().value_text
    path = save_and_reopen(w, tmp_path)
    (again,) = markups(w, MeasureItem)
    assert again.caption_parts == ["label", "area", "perimeter", "wall_area"]
    assert again.value_text == text
    image = mupdf_page(path)
    assert not image.isNull()


# ---------------------------------------------------------------------------
# 6.6 — strikethrough, superscript, subscript
# ---------------------------------------------------------------------------
def test_strikethrough_superscript_and_subscript(w, tmp_path):
    frame = w.document.pages[0].frame
    box = TextItem("Remove this", QRectF(0, 0, 200, 40))
    frame.add_markup(box, QPointF(200, 300))
    select(w, box)
    # Revu's Style ▾: Font Style B I U S
    press(w.font_style_button)
    assert w.font_style_popup.isVisible()
    strike = w.font_buttons["strikethrough"]

    def the_box():
        return markups(w, TextItem)[0]
    one_undo_step(w, lambda: press(strike), lambda: the_box().style.strikethrough)
    w.font_style_popup.hide()
    assert the_box().doc.defaultFont().strikeOut()
    # the Properties panel: Superscript, then Subscript — one or the other
    select(w, the_box())
    sup = w.properties_panel.findChild(QToolButton, "fontStyle_superscript")
    sub = w.properties_panel.findChild(QToolButton, "fontStyle_subscript")
    assert sup is not None and sub is not None
    press(sup)
    assert the_box().style.superscript and not the_box().style.subscript
    select(w, the_box())
    sub = w.properties_panel.findChild(QToolButton, "fontStyle_subscript")
    press(sub)
    box = the_box()
    assert box.style.subscript and not box.style.superscript
    fmt = box.doc.begin().begin().fragment().charFormat()
    assert fmt.verticalAlignment() == fmt.VerticalAlignment.AlignSubScript
    # Edit ▸ Text ▸ Subscript takes it off again, one undo step
    select(w, box)
    assert w.act_subscript in w.findChild(type(w.menuBar().actions()[0].menu()),
                                          "menuText").actions()
    one_undo_step(w, w.act_subscript.trigger, lambda: not the_box().style.subscript)
    w.undo_stack.undo()                   # back to subscript for the file
    pump()
    path = save_and_reopen(w, tmp_path)
    (again,) = markups(w, TextItem)
    assert again.style.strikethrough and again.style.subscript
    with pymupdf.open(path) as document:
        said = document.xref_object(next(document[0].annots()).xref)
        assert "line-through" in said and "vertical-align:sub" in said
    image = mupdf_page(path)
    assert not image.isNull()


def test_a_run_of_words_is_struck_through_on_its_own(w):
    from PySide6.QtGui import QTextCursor
    frame = w.document.pages[0].frame
    box = TextItem("keep strike", QRectF(0, 0, 200, 40))
    frame.add_markup(box, QPointF(200, 300))
    select(w, box)
    w.view.begin_item_edit(box) if hasattr(w.view, "begin_item_edit") else box.begin_edit()
    pump()
    editor = w.view.text_editor()
    assert editor is not None
    cursor = editor.textCursor()
    cursor.setPosition(5)
    cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
    editor.setTextCursor(cursor)
    assert w.toggle_strikethrough()
    assert editor.textCursor().charFormat().fontStrikeOut()
    assert not box.style.strikethrough, "only the run, not the box"


# ---------------------------------------------------------------------------
# 6.6 — line-style Manage…
# ---------------------------------------------------------------------------
@pytest.fixture
def no_own_line_styles():
    from calcforge.items import linestyles
    yield
    for name in list(linestyles.CUSTOM):
        linestyles.remove_style(name)
    linestyles.save_custom()


def test_line_style_manage_makes_a_style_that_travels(w, tmp_path, no_own_line_styles):
    from calcforge.items import linestyles
    w.select_tool("line")
    drag(w, page(w, 150, 300), page(w, 400, 300))
    w.select_tool("select")
    (line,) = markups(w, PolyItem)
    select(w, line)
    combo = w.dash_combo
    assert combo.itemText(0) == "Manage…"
    opened = []
    real = w.manage_line_styles
    w.manage_line_styles = lambda: opened.append(real()) or opened[-1]
    pick(combo, linestyles.MANAGE, stays=False)
    pump()
    assert opened, "Manage… opens Line Styles"
    (_line,) = markups(w, PolyItem)
    assert _line.style.line_style == "solid", "the markup keeps its style"
    dialog = opened[0]
    assert dialog.buttons["remove"].isEnabled() is False
    assert dialog.new_style("Fence", "6, 2, 1, 2") == "Fence"
    assert dialog.import_file(str(_lin(tmp_path)), "in") == ["SHORT"]
    dialog.reject()
    pump()
    assert combo.findData("Fence") >= 0 and combo.findData("SHORT") >= 0
    # kept for next time
    linestyles.load_custom()
    assert linestyles.CUSTOM["Fence"] == [6.0, 2.0, 1.0, 2.0]
    select(w, markups(w, PolyItem)[0])

    def the_line():
        return markups(w, PolyItem)[0]
    one_undo_step(w, lambda: pick(w.dash_combo, "Fence"),
                  lambda: the_line().style.line_style == "Fence")
    assert tuple(the_line().style.dash_array) == (6.0, 2.0, 1.0, 2.0)
    path = save_and_reopen(w, tmp_path)
    (again,) = markups(w, PolyItem)
    assert again.style.line_style == "Fence" and again.style.dashes() == [6.0, 2.0, 1.0, 2.0]
    with pymupdf.open(path) as document:
        said = document.xref_object(next(document[0].annots()).xref)
        import re
        assert re.search(r"/D \[\s*6 2 1 2\s*\]", said)
    # taken out again; a markup that has it is drawn the same
    dialog = w.manage_line_styles()
    dialog.list.setCurrentRow([dialog.list.item(i).data(Qt.UserRole)
                               for i in range(dialog.list.count())].index("Fence"))
    assert dialog.buttons["remove"].isEnabled()
    press_button = dialog.buttons["remove"]
    press_button.click()
    dialog.reject()
    pump()
    assert "Fence" not in linestyles.CUSTOM
    (again,) = markups(w, PolyItem)
    assert again.style.dashes() == [6.0, 2.0, 1.0, 2.0]


def _lin(tmp_path):
    path = tmp_path / "acad.lin"
    path.write_text("*SHORT,Short dashes __ __ __\nA,.125,-.0625\n"
                    "*GAS_LINE,Gas line ----GAS----\nA,.5,-.2,[\"GAS\",STANDARD,S=.1],-.25\n")
    return path


# ---------------------------------------------------------------------------
# 6.6 — a size for each line end
# ---------------------------------------------------------------------------
def test_each_line_end_has_its_own_size(w, tmp_path):
    w.select_tool("arrow")
    drag(w, page(w, 150, 300), page(w, 400, 300))
    w.select_tool("select")
    (arrow,) = markups(w, PolyItem)
    select(w, arrow)
    assert arrow.style.arrow_start == "none"
    assert not shown_on_bar(w, w.arrow_start_size_spin), "no start: no start size (Revu)"
    assert shown_on_bar(w, w.arrow_size_spin)

    def the_arrow():
        return markups(w, PolyItem)[0]
    pick(w.arrow_start_combo, "arrow")
    assert the_arrow().style.arrow_start == "arrow"
    assert shown_on_bar(w, w.arrow_start_size_spin)
    # Start ▾ Auto ▾ End ▾ Auto ▾, as Revu's
    bar = w.style_bar
    visible = [bar.widgetForAction(a) for a in bar.actions() if a.isVisible()]
    assert visible.index(w.arrow_start_size_spin) == visible.index(w.arrow_start_combo) + 1
    assert visible.index(w.arrow_size_spin) == visible.index(w.arrow_end_combo) + 1
    one_undo_step(w, lambda: pick(w.arrow_start_size_spin, 2.0),
                  lambda: the_arrow().style.start_size() == pytest.approx(2.0))
    assert the_arrow().style.arrow_size == pytest.approx(1.0), "the end keeps its size"
    pick(w.arrow_size_spin, 0.5)
    arrow = the_arrow()
    assert arrow.style.arrow_size == pytest.approx(0.5)
    assert arrow.style.start_size() == pytest.approx(2.0), "the start keeps its size"
    # the Properties panel has both, in the bar's words (Auto, 25% … 400%)
    select(w, arrow)
    start = w.properties_panel.findChild(QComboBox, "arrowStartSize")
    end = w.properties_panel.findChild(QComboBox, "arrowSize")
    assert start.value() == pytest.approx(2.0) and end.value() == pytest.approx(0.5)
    assert start.currentText() == "200%" and end.currentText() == "50%"
    # drawn so: the start's head is the bigger
    big, small = _head_ink(arrow, 0), _head_ink(arrow, -1)
    assert big > small * 1.8
    path = save_and_reopen(w, tmp_path)
    (again,) = markups(w, PolyItem)
    assert again.style.start_size() == pytest.approx(2.0)
    assert again.style.arrow_size == pytest.approx(0.5)
    image = mupdf_page(path)
    start_point = again.mapToScene(again.points[0])
    end_point = again.mapToScene(again.points[-1])
    frame = w.document.pages[0].frame
    a, b = frame.mapFromScene(start_point), frame.mapFromScene(end_point)

    def red(c):
        return c.red() > 150 and c.green() < 110

    near_start = ink_in(image, QRectF(a.x() * 2, a.y() * 2 - 30, 40, 60), red)
    near_end = ink_in(image, QRectF(b.x() * 2 - 40, b.y() * 2 - 30, 40, 60), red)
    assert near_start > near_end * 1.5, "other readers draw the start bigger too"


def _head_ink(item, which: int) -> int:
    image = QImage(500, 200, QImage.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.translate(50, 100)
    item.paint_visible(painter)
    painter.end()
    tip = item.points[which]
    x0 = int(tip.x()) + 50
    left, right = (x0, x0 + 30) if which == 0 else (x0 - 30, x0)
    return sum(1 for x in range(left, right) for y in range(70, 130)
               if QColor(image.pixel(x, y)).lightness() < 200)


# ---------------------------------------------------------------------------
# the bar still fits at 1280, with the » for anything that does not
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("kind", ["area", "callout", "length", "cloud", "arrow", "text",
                                  "dimension"])
def test_the_bar_fits_1280_for_each_kind(w, kind):
    """Each kind's bar fits at 1280; a length's, as wide as Revu's own, puts
    its Totals behind the » (as it did before), and nothing else."""
    from tests.test_window_layout import _in_overflow
    from calcforge.items.measure import DIMENSION
    assert w.width() == 1280
    frame = w.document.pages[0].frame
    item = {
        "area": lambda: MeasureItem(AREA, [QPointF(0, 0), QPointF(160, 0), QPointF(160, 110)]),
        "callout": lambda: CalloutItem("Note", QRectF(0, 0, 120, 30), [QPointF(-60, 80)]),
        "length": lambda: MeasureItem(LENGTH, [QPointF(0, 0), QPointF(200, 0)]),
        "dimension": lambda: MeasureItem(DIMENSION, [QPointF(0, 0), QPointF(200, 0)]),
        "cloud": lambda: RectItem("cloud", QRectF(0, 0, 120, 60)),
        "arrow": lambda: PolyItem("arrow", [QPointF(0, 0), QPointF(140, 80)]),
        "text": lambda: TextItem("Words", QRectF(0, 0, 120, 30)),
    }[kind]()
    frame.add_markup(item, QPointF(300, 300))
    if kind == "arrow":
        item.style.arrow_start = "arrow"          # both sizes shown: the widest
    w.view.scene().clearSelection()
    item.setSelected(True)
    w.refresh_selection()
    pump()
    bar = w.style_bar
    hidden = _in_overflow(bar)
    if kind == "length":
        widgets = {bar.widgetForAction(a) for a in hidden}
        assert widgets <= {w.totals_button} | {
            bar.widgetForAction(a) for a in w._style_widgets["totals"]}, kind
        return
    assert hidden == [], kind
    assert bar.sizeHint().width() <= bar.width(), kind


# ---------------------------------------------------------------------------
# every new command takes a key (Keyboard Shortcuts)
# ---------------------------------------------------------------------------
def test_the_new_commands_can_be_given_keys_and_pressed(w):
    frame = w.document.pages[0].frame
    box = TextItem("Words", QRectF(0, 0, 200, 60))
    frame.add_markup(box, QPointF(200, 300))
    known = {b.action_id: b for b in w.shortcuts.bindings()}
    for command in ("command.strikethrough", "command.superscript", "command.subscript",
                    "propbar.auto"):
        assert command in known and known[command].category not in ("", "Other"), command
    try:
        w.shortcuts.set_sequence("command.strikethrough", "Ctrl+Alt+K")
        w.shortcuts.set_sequence("propbar.auto", "Ctrl+Alt+J")
        w.apply_shortcuts()
        select(w, box)
        w.view.setFocus()
        key(w, Qt.Key_K, Qt.ControlModifier | Qt.AltModifier)
        (box,) = markups(w, TextItem)
        assert box.style.strikethrough
        select(w, box)
        w.view.setFocus()
        key(w, Qt.Key_J, Qt.ControlModifier | Qt.AltModifier)
        (box,) = markups(w, TextItem)
        assert box.style.font_auto
    finally:
        w.shortcuts.reset()
        w.apply_shortcuts()


# ---------------------------------------------------------------------------
# round 2 (the user, 2026-10-17)
# ---------------------------------------------------------------------------
def _hatched_tools(w):
    """Every tool whose markup takes a hatch, and one of it drawn."""
    from calcforge.ui.stylecaps import HATCH, capabilities
    from calcforge.ui.tools import TOOLS
    for tool in TOOLS:
        if tool.factory is None or tool.key in ("snapshot", "calibrate", "image"):
            continue
        if tool.key.startswith("cutout"):
            continue                  # these cut a hole; they leave nothing behind
        made = tool.factory()
        if getattr(made, "kind", "") == "marquee":
            continue                  # a region being chosen (Crop, Whiteout, Viewport)
        if HATCH in capabilities(made):
            yield tool.key


def test_every_hatched_markup_has_its_hatch_colour_on_the_bar_and_panel(w):
    """A Sketch to Scale rectangle's hatch had no colour on the Properties
    toolbar: every markup with a hatch shows it, on the bar and in the panel,
    and both change it in one undo step."""
    from calcforge.ui import colorpicker
    from calcforge.ui.widgets import ColorButton
    from tests.probe_audit import make
    scaled(w, 50)
    keys = list(_hatched_tools(w))
    for wanted in ("rect", "ellipse", "polygon", "cloud", "measure_area", "measure_volume",
                   "sketch_rect", "sketch_ellipse"):
        assert wanted in keys, wanted
    for index, key_ in enumerate(keys):
        w.new_document()
        w.interactive_prompts = False
        scaled(w, 50)
        w.view.set_zoom(1.0)
        pump()
        item = make(w, key_)
        assert item is not None, key_
        w.select_tool("select")
        w.view.scene().clearSelection()
        item.setSelected(True)
        w.refresh_selection()
        pump()
        button = w.hatch_bar_colour_button
        assert shown_on_bar(w, button), key_
        assert shown_on_bar(w, w.hatch_combo), key_
        bar = w.style_bar
        visible = [bar.widgetForAction(a) for a in bar.actions() if a.isVisible()]
        assert visible.index(button) == visible.index(w.hatch_combo) + 1, key_
        colour = f"#00{index:02x}a0"
        before = w.undo_stack.index()
        colorpicker.ANSWERS.append(colour)
        press(button)
        assert w.undo_stack.index() == before + 1, key_
        (found,) = [i for i in w.view.scene().ordered_markups() if i.uid == item.uid]
        assert found.style.hatch_color == colour, key_
        assert button.color() == colour
        # the Properties panel's own, beside its Hatch list
        w.view.scene().clearSelection()
        found.setSelected(True)
        w.refresh_selection()
        pump()
        panel_button = w.properties_panel.findChild(ColorButton, "hatchColour")
        assert panel_button is not None and panel_button.isVisible(), key_
        colorpicker.ANSWERS.append("#123456")
        press(panel_button)
        (found,) = [i for i in w.view.scene().ordered_markups() if i.uid == item.uid]
        assert found.style.hatch_color == "#123456", key_
        w.undo_stack.undo()
        pump()
        (found,) = [i for i in w.view.scene().ordered_markups() if i.uid == item.uid]
        assert found.style.hatch_color == colour, key_
        w.document.modified = False


def test_the_bars_number_boxes_show_their_widest_value(w):
    """'100%' was cut off in the fill-opacity box: every number box on the
    bar is as wide as its widest value needs, at the default font."""
    from PySide6.QtWidgets import QAbstractSpinBox
    from calcforge.ui.propbar import CloudSizeCombo, LineSpacingCombo, ValueCombo
    box = RectItem("rect", QRectF(0, 0, 120, 60))
    w.document.pages[0].frame.add_markup(box, QPointF(200, 300))
    select(w, box)
    for spin in w.style_bar.findChildren(QAbstractSpinBox):
        metrics = spin.fontMetrics()
        widest = max(metrics.horizontalAdvance(spin.prefix() + spin.textFromValue(v)
                                               + spin.suffix())
                     for v in (spin.minimum(), spin.maximum()))
        assert spin.lineEdit().width() >= widest + 4, spin.objectName()
        assert spin.width() <= widest + 50, spin.objectName()
    for combo in w.style_bar.findChildren(ValueCombo):
        if isinstance(combo, (CloudSizeCombo, LineSpacingCombo)):
            continue                     # closed, each shows its picture only
        widest = max(combo.fontMetrics().horizontalAdvance(combo.itemText(i))
                     for i in range(combo.count()))
        assert combo.width() >= widest + 28, combo.objectName()
    # the fill opacity box draws all of "100%": its last column has ink
    w.fill_opacity_spin.setValue(100)
    pump()
    edit = w.fill_opacity_spin.lineEdit()
    assert edit.cursorRect().right() <= edit.width(), "the text ends inside the box"


@pytest.mark.parametrize("tool", ["rect", "ellipse", "polygon", "line", "arrow", "polyline",
                                  "cloud", "sketch_rect", "sketch_ellipse"])
def test_only_sketch_to_scale_shapes_show_a_size_box_while_placed(w, tool):
    """A plain Rectangle or Ellipse is not to scale: no size box rides its
    corner while it is placed (the user, 2026-10-17); Sketch to Scale's do."""
    from PySide6.QtWidgets import QGraphicsProxyWidget
    scaled(w, 50)
    w.select_tool(tool)
    viewport = w.view.viewport()
    QTest.mouseClick(viewport, Qt.LeftButton, Qt.NoModifier, at(w, page(w, 150, 300)))
    pump()
    for x, y in ((260, 380), (330, 420)):
        QTest.mouseMove(viewport, at(w, page(w, x, y)))
        pump()
    proxies = [i for i in w.view.scene().items()
               if isinstance(i, QGraphicsProxyWidget) and i.isVisible()]
    if tool.startswith("sketch"):
        assert w.view._size_editor is not None and proxies
        # typed with the keyboard, as before: width, Tab, height, Enter
        QTest.keyClicks(QApplication.focusWidget(), "3")
        QTest.keyClick(QApplication.focusWidget(), Qt.Key_Tab)
        QTest.keyClicks(QApplication.focusWidget(), "2")
        QTest.keyClick(QApplication.focusWidget(), Qt.Key_Return)
        pump()
        (shape,) = markups(w, RectItem)
        assert shape.to_scale and shape.size_text.startswith("3.00 m")
    else:
        assert w.view._size_editor is None and not proxies, tool
        key(w, Qt.Key_Escape)
        key(w, Qt.Key_Escape)
