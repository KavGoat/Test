"""Markup interaction, round 6 (2026-10-16): the novice round's and the bug
hunt's markup findings, driven the way a person drives them — real mouse
presses on the viewport at the places things are drawn, real keys, right-click
menus read from the popup that opens.
"""
from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from calcforge.items.calc import CalcItem
from calcforge.items.measure import MeasureItem
from calcforge.items.shapes import RectItem
from calcforge.items.text import CalloutItem, TextItem


@pytest.fixture
def w(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    pump()
    return window


def pump(n=2):
    for _ in range(n):
        QApplication.instance().processEvents()


def vp(w):
    return w.view.viewport()


def screen(w, point: QPointF) -> QPoint:
    return w.view.mapFromScene(point)


def page(w, x, y) -> QPointF:
    """A point on page 1, in canvas coordinates."""
    return w.document.pages[0].frame.mapToScene(QPointF(x, y))


def press(w, point, modifiers=Qt.NoModifier):
    QTest.mousePress(vp(w), Qt.LeftButton, modifiers, screen(w, point))


def move(w, point):
    QTest.mouseMove(vp(w), screen(w, point))


def release(w, point, modifiers=Qt.NoModifier):
    QTest.mouseRelease(vp(w), Qt.LeftButton, modifiers, screen(w, point))


def click(w, point, modifiers=Qt.NoModifier):
    press(w, point, modifiers)
    release(w, point, modifiers)
    pump()


def drag(w, a: QPointF, b: QPointF, modifiers=Qt.NoModifier):
    press(w, a, modifiers)
    for t in (0.25, 0.5, 0.75, 1.0):
        move(w, QPointF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t))
    release(w, b, modifiers)
    pump()


def key(w, k, modifiers=Qt.NoModifier):
    QTest.keyClick(vp(w), k, modifiers)
    pump()


def markups(w, kind=None):
    found = w.view.scene().ordered_markups()
    return [i for i in found if kind is None or isinstance(i, kind)]


def draw_rect(w, x, y, width, height):
    w.select_tool("rect")
    drag(w, page(w, x, y), page(w, x + width, y + height))
    w.select_tool("select")
    return markups(w, RectItem)[-1]


def scene_rect(item) -> QRectF:
    return item.mapRectToScene(item.local_rect().normalized())


# -- 1. a multi-selection moves as one (finding 1.7) -------------------------------

def test_pressing_the_edge_of_one_of_several_selected_markups_moves_them_all(w):
    rects = [draw_rect(w, 100 + 40 * i, 200, 20, 14) for i in range(5)]
    key(w, Qt.Key_A, Qt.ControlModifier)
    assert all(r.isSelected() for r in rects)
    before = [scene_rect(r).topLeft() for r in rects]
    sizes = [scene_rect(r).size() for r in rects]
    # its top stroke between the corner's control point and the middle one
    # (round 7: each of several selected keeps its own handles)
    top_edge = rects[2].mapToScene(QPointF(5, 0))
    drag(w, top_edge, top_edge + QPointF(30, 25))
    after = [scene_rect(r).topLeft() for r in rects]
    for b, a in zip(before, after):
        assert (a - b).x() == pytest.approx(30, abs=1.5)
        assert (a - b).y() == pytest.approx(25, abs=1.5)
    assert [scene_rect(r).size() for r in rects] == sizes


def test_a_corner_of_one_of_several_selected_markups_resizes_only_it(w):
    """Round 7 (the user, 2026-10-16): several selected markups each keep
    their own control points, as in Revu; a corner resizes its own markup."""
    one = draw_rect(w, 100, 200, 120, 80)
    two = draw_rect(w, 300, 200, 120, 80)
    click(w, scene_rect(one).center())
    click(w, scene_rect(two).center(), Qt.ShiftModifier)
    assert one.isSelected() and two.isSelected()
    size, start = scene_rect(one).size(), scene_rect(two).topLeft()
    two_size = scene_rect(two).size()
    corner = scene_rect(one).bottomRight()
    drag(w, corner, corner + QPointF(40, 30))
    assert scene_rect(one).width() == pytest.approx(size.width() + 40, abs=1.5)
    assert scene_rect(one).height() == pytest.approx(size.height() + 30, abs=1.5)
    assert scene_rect(two).topLeft() == start and scene_rect(two).size() == two_size


def test_a_handle_takes_the_press_only_inside_the_square_it_is_drawn_in(w):
    one = draw_rect(w, 100, 200, 120, 80)
    click(w, scene_rect(one).center())
    w.view.set_zoom(3.0)
    w.view.centerOn(scene_rect(one).center())
    pump()
    size = scene_rect(one).size()
    pixel = 1.0 / w.view.transform().m11()
    side = one.mapToScene(one.handle_points()["e"])
    # 6 px right of the middle handle of the right side: outside the 5 px dot
    # drawn there (a reach of 4 pt, 8 px at this zoom, used to catch it)
    off = side + QPointF(6 * pixel, 0)
    drag(w, off, off + QPointF(40, 0))
    assert scene_rect(one).size() == size
    # on the dot itself it still resizes
    side = one.mapToScene(one.handle_points()["e"])
    drag(w, side, side + QPointF(40, 0))
    assert scene_rect(one).width() == pytest.approx(size.width() + 40, abs=2)


def test_a_multi_selection_draws_no_box_round_the_lot(w, tmp_path):
    one = draw_rect(w, 100, 200, 100, 50)
    two = draw_rect(w, 300, 300, 100, 50)
    key(w, Qt.Key_A, Qt.ControlModifier)
    assert w.view.scene().many_selected()
    assert w.view._selected_group() is None        # round 7: no group box
    click(w, page(w, 600, 600))
    click(w, scene_rect(one).center())
    assert one.isSelected() and not two.isSelected()
    assert not w.view.scene().many_selected()


# -- helpers for what pops up ---------------------------------------------------------

def watching(handler, every=20, limit=4000):
    """Run *handler(widget)* on the first popup menu or modal dialog that
    opens while the caller does something that blocks on it."""
    seen = {"done": False}
    timer = QTimer()
    timer.setInterval(every)
    started = time.perf_counter()

    def look():
        if seen["done"] or (time.perf_counter() - started) * 1000 > limit:
            timer.stop()
            return
        widget = next((candidate for candidate in (QApplication.activePopupWidget(),
                                                    QApplication.activeModalWidget())
                       if candidate is not None and candidate.isVisible()), None)
        if widget is not None:
            seen["done"] = True
            timer.stop()
            handler(widget)
    timer.timeout.connect(look)
    timer.start()
    return timer


def back_to_the_window(w, limit=3.0):
    """Wait until the keyboard is the window's again after a popup: no popup
    or modal dialog left, and the main window active.

    The offscreen platform makes a popup menu the active window and hands
    activation back to the main window only some events after the menu has
    closed. A key sent before then reaches no shortcut, so a Ctrl+Z straight
    after a right-click menu was lost on a loaded machine. This waits for
    that state rather than for a fixed time; if it never comes (the platform
    has no window manager to do it), it asks for it, as clicking the window
    would."""
    deadline = time.perf_counter() + limit
    asked = False
    while True:
        QApplication.instance().processEvents()
        popup = QApplication.activePopupWidget() or QApplication.activeModalWidget()
        if popup is None and QApplication.activeWindow() is w and w.isActiveWindow():
            return True
        if time.perf_counter() > deadline:
            if asked:
                return False
            asked = True
            w.activateWindow()
            deadline = time.perf_counter() + limit
        time.sleep(0.005)


def right_click_menu(w, point: QPointF, pick: str = ""):
    """Right-click at *point* the way the mouse does, read the menu that
    opens, and click *pick* in it (or close it). Returns its entries."""
    got = {}

    def handle(menu):
        got["labels"] = [a.text() for a in menu.actions() if a.text()]
        # no pick: close it (an empty pick used to "click" the first
        # separator and leave the menu open)
        target = next((a for a in menu.actions() if pick and a.text() == pick), None)
        if target is not None:
            QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier,
                             menu.actionGeometry(target).center())
        else:
            menu.close()
    keep = watching(handle)
    from PySide6.QtGui import QContextMenuEvent
    local = screen(w, point)
    QTest.mousePress(vp(w), Qt.RightButton, Qt.NoModifier, local)
    QTest.mouseRelease(vp(w), Qt.RightButton, Qt.NoModifier, local)
    pump()
    if "labels" not in got:
        # offscreen Qt makes no context-menu event of its own from a right
        # button: send the one the platform sends for that click
        QApplication.sendEvent(vp(w), QContextMenuEvent(
            QContextMenuEvent.Mouse, local, vp(w).mapToGlobal(local)))
        pump()
    keep.stop()
    # what comes next may be a key: it has to reach the window, not the
    # menu that has just closed
    back_to_the_window(w)
    return got.get("labels", [])


def heading(w) -> str:
    from PySide6.QtWidgets import QLabel
    label = w.properties_panel.findChild(QLabel, "propHeading")
    return label.text() if label is not None else ""


# -- 2. only measurements ask for a scale --------------------------------------------

def test_a_rectangle_never_asks_for_a_scale(w):
    w.interactive_prompts = True
    asked = []
    keep = watching(lambda d: (asked.append(d.windowTitle()), d.reject()))
    draw_rect(w, 100, 200, 120, 80)
    w.select_tool("ellipse")
    drag(w, page(w, 300, 200), page(w, 400, 260))
    w.select_tool("select")
    pump(3)
    keep.stop()
    assert asked == []
    assert len(markups(w)) == 2
    assert w.status_scale.text() == "Scale Not Set"


@pytest.mark.parametrize("tool", ["measure_diameter", "measure_radius", "count",
                                  "measure_angle", "measure_perimeter"])
def test_every_measurement_asks_for_a_scale_and_cancel_keeps_it(w, tool):
    w.interactive_prompts = True
    asked = []

    def cancel(dialog):
        asked.append(dialog.windowTitle())
        dialog.reject()
    keep = watching(cancel)
    w.select_tool(tool)
    a, b, c = page(w, 150, 300), page(w, 300, 300), page(w, 300, 420)
    if tool in ("measure_diameter", "measure_radius"):
        drag(w, a, b)
    elif tool == "count":
        click(w, a)
    else:
        click(w, a)
        click(w, b)
        click(w, c)
        if tool == "measure_perimeter":
            key(w, Qt.Key_Return)
    pump(3)
    keep.stop()
    assert len(asked) == 1, asked
    drawn = [m for m in markups(w) if not isinstance(m, RectItem)]
    assert len(drawn) == 1                      # cancelled, and still drawn
    assert not w.current_page().scale.is_calibrated()


# -- 3. a text box is dragged out (round 7: tests/test_round7_shapes.py) -------------

def test_a_dragged_text_box_is_ready_to_type_in(w):
    click(w, page(w, 600, 600))
    key(w, Qt.Key_T)                              # Revu's key for the Text Box tool
    assert w.view.tool_key == "text"
    click(w, page(w, 200, 300))                   # a click alone places nothing
    assert markups(w, TextItem) == [] and w.view.tool_key == "text"
    drag(w, page(w, 100, 400), page(w, 400, 460))
    QTest.keyClicks(vp(w), "Hello")
    pump()
    box = w.view.editing_item()
    assert isinstance(box, TextItem)
    assert box.text() == "Hello"
    assert box.local_rect().width() == pytest.approx(300, abs=3)
    key(w, Qt.Key_Escape)
    assert [m.text() for m in markups(w, TextItem)] == ["Hello"]


# -- 4. a measurement's value is never under its handles -----------------------------

def an_area(w):
    w.select_tool("measure_area")
    for x, y in ((150, 300), (400, 300), (400, 480), (150, 480)):
        click(w, page(w, x, y))
    key(w, Qt.Key_Return)
    w.select_tool("select")
    (area,) = markups(w, MeasureItem)
    return area


@pytest.mark.parametrize("zoom", [0.5, 1.0, 3.0])
def test_the_area_value_is_not_covered_by_its_handles(w, zoom):
    area = an_area(w)
    click(w, area.mapToScene(area.points[0]) + QPointF(30, 30))
    assert area.isSelected()
    w.view.set_zoom(zoom)
    w.view.centerOn(area.mapToScene(area.local_rect().center()))
    pump()
    from PySide6.QtGui import QFontMetricsF
    metrics = QFontMetricsF(area.style.font())
    centre = area._label_anchor() + area.label_offset
    half_w = (metrics.horizontalAdvance(area.value_text) + 8) / 2
    half_h = metrics.height() / 2
    words = QRectF(centre.x() - half_w + 4, centre.y() - half_h, 2 * half_w - 8, 2 * half_h)
    from calcforge.items.base import CONTROL_HALF_PX, view_zoom
    dot = CONTROL_HALF_PX / view_zoom(area)
    for key_, point in area.handle_points().items():
        square = QRectF(point.x() - dot, point.y() - dot, 2 * dot, 2 * dot)
        assert not square.intersects(words), key_


def test_the_area_values_dot_moves_the_value_without_a_jump(w):
    area = an_area(w)
    click(w, area.mapToScene(area.points[0]) + QPointF(30, 30))
    assert not area.label_rect().contains(area.handle_points()["lbl"])   # beside the words
    dot = area.mapToScene(area.handle_points()["lbl"])
    before = area.label_offset
    drag(w, dot, dot + QPointF(40, 20))
    moved = area.label_offset - before
    assert moved.x() == pytest.approx(40, abs=2) and moved.y() == pytest.approx(20, abs=2)


# -- 5. every markup has its tool's name as Subject ---------------------------------

def test_markups_get_the_tools_name_as_subject(w):
    draw_rect(w, 100, 100, 80, 50)
    w.select_tool("cloud")
    drag(w, page(w, 250, 100), page(w, 350, 160))
    w.select_tool("callout")
    click(w, page(w, 100, 300))
    click(w, page(w, 200, 260))
    key(w, Qt.Key_Escape)
    w.select_tool("cloud_callout")
    drag(w, page(w, 300, 300), page(w, 380, 360))
    click(w, page(w, 450, 260))
    key(w, Qt.Key_Escape)
    w.select_tool("text")
    drag(w, page(w, 100, 500), page(w, 250, 540))
    QTest.keyClicks(vp(w), "x")
    key(w, Qt.Key_Escape)
    w.select_tool("select")
    subjects = sorted(m.subject for m in markups(w))
    assert subjects == sorted(["Rectangle", "Cloud", "Callout", "Cloud+", "Text Box"])
    cloud_plus = next(m for m in markups(w) if m.subject == "Cloud+")
    click(w, cloud_plus.mapToScene(cloud_plus.local_rect().center()))
    assert heading(w) == "Cloud+ Properties"
    callout = next(m for m in markups(w) if m.subject == "Callout")
    click(w, callout.mapToScene(callout.local_rect().center()))
    assert heading(w) == "Callout Properties"


# -- 6. a measurement's properties read in its units ---------------------------------

def test_area_unit_reads_m2_and_the_size_is_called_the_document_size(w):
    from PySide6.QtWidgets import QDoubleSpinBox, QFormLayout
    from calcforge.ui.widgets import UnitCombo
    area = an_area(w)
    click(w, area.mapToScene(area.points[0]) + QPointF(30, 30))
    pump()
    unit = w.properties_panel.findChild(UnitCombo, "measureAreaUnit")
    assert unit is not None and unit.shownText() in ("m²", "mm²")
    assert "^" not in unit.shownText()
    assert all("^" not in unit.itemText(i) for i in range(unit.count()))
    width = w.properties_panel.findChild(QDoubleSpinBox, "layoutWidth")
    form = width.parentWidget().parentWidget().layout()
    labels = []
    for row in range(form.rowCount()):
        item = form.itemAt(row, QFormLayout.LabelRole)
        if item is not None and item.widget() is not None:
            labels.append(item.widget().text())
    assert "Document Width:" in labels and "Document Height:" in labels
    # choosing mm² from the list still keeps the unit as the page needs it
    unit.setCurrentIndex(unit.findText("mm²"))
    pump()
    assert w.current_page().scale.area_unit == "mm^2"


# -- 7. Shift/Ctrl+click adds an equation ---------------------------------------------

@pytest.mark.parametrize("mode", ["markup", "calc"])
@pytest.mark.parametrize("modifier", [Qt.ShiftModifier, Qt.ControlModifier])
def test_shift_or_ctrl_click_picks_a_second_equation_too(w, mode, modifier):
    from tests.test_calc_panels import an_equation
    first = an_equation(w, "a:=1", 100, 120)
    second = an_equation(w, "b:=2", 100, 200)
    w.toggle_calc_mode(mode == "calc")
    click(w, page(w, 600, 600))
    click(w, first.mapToScene(first.local_rect().center()))
    click(w, second.mapToScene(second.local_rect().center()), modifier)
    picked = [i for i in w.view.scene().selectedItems() if isinstance(i, CalcItem)]
    assert set(picked) == {first, second}


# -- 9. the Markups List ----------------------------------------------------------------

def test_markups_list_pages_ascend_without_empty_ones_and_the_funnel_filters(w):
    for _ in range(3):
        w.document.add_page()
    w.rebuild_scenes()
    pump()
    for index in (0, 2):
        frame = w.document.pages[index].frame
        w.view.centerOn(frame.mapToScene(QPointF(200, 200)))
        pump()
        w.select_tool("rect")
        drag(w, frame.mapToScene(QPointF(100, 100)), frame.mapToScene(QPointF(200, 160)))
        w.select_tool("cloud")
        drag(w, frame.mapToScene(QPointF(300, 100)), frame.mapToScene(QPointF(400, 160)))
    w.select_tool("select")
    w.refresh_lists()
    panel = w.markups_panel
    tree = panel.tree
    tops = [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]
    assert tops == ["Page 1", "Page 3"]

    header = tree.header()
    panel.show()
    header.resizeSection(1, 120)
    pump()
    column = panel.COLUMNS.index("Type")
    funnel = header.filter_rect(column).center()
    got = {}

    def untick_cloud(menu):
        got["title"] = menu.title()
        cloud = next(a for a in menu.actions() if a.text() == "Cloud")
        QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier, menu.actionGeometry(cloud).center())
        menu.close()
    keep = watching(untick_cloud)
    sorted_by = (header.sortIndicatorSection(), header.sortIndicatorOrder())
    QTest.mouseClick(header.viewport(), Qt.LeftButton, Qt.NoModifier, funnel)
    for _ in range(20):
        pump()
        if got:
            break
        time.sleep(0.03)
    keep.stop()
    assert got.get("title") == "Filter Type"
    assert (header.sortIndicatorSection(), header.sortIndicatorOrder()) == sorted_by
    kinds = {tree.topLevelItem(i).child(j).text(1)
             for i in range(tree.topLevelItemCount())
             for j in range(tree.topLevelItem(i).childCount())}
    assert kinds == {"Rectangle"}
    # elsewhere on the heading a click sorts
    QTest.mouseClick(header.viewport(), Qt.LeftButton, Qt.NoModifier,
                     QPoint(header.sectionViewportPosition(column) + 10, header.height() // 2))
    pump()
    assert header.sortIndicatorSection() == column


# -- 10. markup styles ------------------------------------------------------------------

def test_save_as_markup_style_from_the_right_click_menu_and_its_title(w):
    w.select_tool("callout")
    click(w, page(w, 100, 300))
    click(w, page(w, 200, 260))
    QTest.keyClicks(vp(w), "check")
    key(w, Qt.Key_Escape)
    w.select_tool("select")
    (callout,) = markups(w, CalloutItem)
    callout.style.width = 3.0
    centre = callout.mapToScene(callout.local_rect().center())
    click(w, centre)
    labels = right_click_menu(w, centre, pick="Save as Markup Style")
    assert "Save as Markup Style" in labels
    at = labels.index("Save as Markup Style")
    assert labels[at - 1] == "Add to Tool Chest"
    from calcforge.ui.markupstyles import styles_for
    assert len(styles_for("callout")) == 1
    w.select_tool("callout")
    key(w, Qt.Key_1)
    w.properties_panel.show_items([])
    assert heading(w) == "Callout Style 1"


# -- 11. equations: kN·m on the screen, and error notes clear of the next one ----------

def test_an_answers_units_are_written_kn_dot_m_on_the_screen(w):
    from tests.test_calc_panels import an_equation
    item = an_equation(w, "M:=3'kN*2'm=", 100, 120)
    view = item._view
    texts = []

    def walk(box):
        if getattr(box, "text", None):
            texts.append(box.text)
        for child in getattr(box, "children", []):
            walk(child)
    walk(view._layout)
    assert "kN·m" in texts, texts
    from calcforge.calc.engine.display import DUnit
    assert item.region.display.unit == DUnit([("kN", 1), ("m", 1)], [])


def test_an_error_note_does_not_overlap_the_equation_under_it(w):
    from tests.test_calc_panels import an_equation
    first = an_equation(w, "t:=fc", 100, 120)
    second = an_equation(w, "u:=1", 100, 120 + first.local_rect().height() + 4)
    assert first._error_message()
    note = first.mapRectToScene(first._error_note_rect())
    assert not note.intersects(second.mapRectToScene(second.local_rect()))
    assert first.boundingRect().contains(first._error_note_rect())
    # with room under it, the note is under it
    lone = an_equation(w, "v:=gg", 400, 400)
    rect = lone._error_note_rect()
    assert rect.top() >= lone.local_rect().bottom()


# -- 8. stalls: nothing slow left in the click -------------------------------------------

def test_building_the_properties_panel_does_not_go_through_the_windows_event_filter(w):
    """Every event of a rebuild went through the window's Python filter on
    the way: twice the time of the building itself (a right-click on a
    Cloud+ took 220 ms)."""
    import sys
    from calcforge.ui.mainwindow import MainWindow
    from calcforge.ui.widgets import WheelBelongsToTheScroller
    w.select_tool("cloud_callout")
    drag(w, page(w, 200, 300), page(w, 300, 360))
    click(w, page(w, 380, 260))
    key(w, Qt.Key_Escape)
    w.select_tool("select")
    (callout,) = markups(w, CalloutItem)
    codes = {MainWindow.eventFilter.__code__, WheelBelongsToTheScroller.eventFilter.__code__}
    seen = []

    def spy(frame, event, _arg):
        if event == "call" and frame.f_code in codes:
            seen.append(frame.f_code.co_qualname)
    sys.setprofile(spy)
    try:
        w.properties_panel.show_items([callout])
    finally:
        sys.setprofile(None)
    assert seen == []
    # and the filters are back for what comes next: a key while typing
    sys.setprofile(spy)
    try:
        QTest.keyClick(vp(w), Qt.Key_Shift)
        pump()
    finally:
        sys.setprofile(None)
    assert seen


def test_the_dictionary_is_read_in_the_background_when_a_word_tool_is_picked(w, monkeypatch):
    """It was read at the click that opened the first box to type in: the
    first Cloud+ stalled for a quarter of a second."""
    from calcforge.core import spelling
    monkeypatch.setattr(spelling, "_shared", None)
    w.select_tool("cloud_callout")
    checker = spelling.shared()
    assert checker._loading is not None or checker._words is not None
    assert checker.knows("colour") and not checker.knows("teh")
