"""Panels as tabs, toolbars in side columns, and Revu's compact Properties
toolbar (the user, 2026-10-15: "There shouldn't be panel stacked on panel on
the side; allow toolbars to be dragged to the side on their own column (can't
join the panel column). … The Properties toolbar is still really wide and not
exactly like Bluebeam for sizes, thickness, hatches, styles.")

(The file buttons in the title row were withdrawn by the user: the title bar
is to be Windows' own.)
"""
import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtWidgets import QToolBar

from calcforge.items.measure import AREA, MeasureItem
from calcforge.items.shapes import RectItem
from calcforge.items.text import CalloutItem
from calcforge.ui.rail import LEFT, RIGHT


def _settle(qapp, times=8):
    for _ in range(times):
        qapp.processEvents()


def _in_overflow(bar: QToolBar) -> list:
    hidden = []
    for action in bar.actions():
        if action.isSeparator() or not action.isVisible():
            continue
        widget = bar.widgetForAction(action)
        if widget is None or not widget.isVisible():
            hidden.append(action)
    return hidden


def _bars(window):
    return {bar.objectName(): bar for bar in window.toolbars}


def _select(window, item, at=QPointF(260, 240)):
    window.view.frame().add_markup(item, at)
    if hasattr(item, "refresh"):
        item.refresh(page=window.current_page())
    window.view.scene().clearSelection()
    item.setSelected(True)
    window.refresh_selection()
    return item


# ---------------------------------------------------------------------------
# panels are tabs, never stacked
# ---------------------------------------------------------------------------

def _both_open(window, docks, qapp):
    """Open panels together, as only something outside the rail can (Qt
    lists a hidden panel among nobody's tabs)."""
    window._changing_panels = True       # the rail's one-a-side rule held off
    try:
        for dock in docks:
            dock.setVisible(True)
        _settle(qapp)
    finally:
        window._changing_panels = False


def _on_screen(window, area) -> list:
    """The panels in *area* that can be seen: a tab behind another is moved
    out of the window by Qt; a panel stacked under another is not."""
    return [dock for dock in window.panels
            if window.dockWidgetArea(dock) == area and dock.isVisible()
            and not dock.isFloating() and window.rect().intersects(dock.geometry())]


def test_two_panels_on_one_side_are_tabs_not_stacked(window, qapp):
    window.show()
    _settle(qapp)
    right = window.dock_properties, window.dock_page
    # both open at once (from outside the rail): one over the other as tabs,
    # at the same place, never one above the other
    _both_open(window, right, qapp)
    assert window.dock_page in window.tabifiedDockWidgets(window.dock_properties)
    assert all(dock.isVisible() for dock in right)
    assert len(_on_screen(window, Qt.RightDockWidgetArea)) == 1


def test_a_panel_dropped_on_the_other_side_joins_its_tabs(window, qapp):
    window.show()
    _settle(qapp)
    # as a drop from the user: Qt puts it in the area, the window does the rest
    window.addDockWidget(Qt.RightDockWidgetArea, window.dock_pages)
    _settle(qapp)
    assert window.panel_sides["dock_pages"] == RIGHT
    assert "dock_pages" in window.right_rail.buttons
    assert "dock_pages" not in window.left_rail.buttons
    shown = [dock for dock in window.panels
             if window.dockWidgetArea(dock) == Qt.RightDockWidgetArea and not dock.isHidden()]
    assert shown == [window.dock_pages], "one panel at a time on a side"
    _both_open(window, (window.dock_pages, window.dock_properties), qapp)
    assert window.dock_pages in window.tabifiedDockWidgets(window.dock_properties)
    assert len(_on_screen(window, Qt.RightDockWidgetArea)) == 1


def test_a_layout_saved_with_stacked_panels_is_tabbed_when_restored(window, qapp):
    window.show()
    _settle(qapp)
    # an arrangement from before: the two stacked one above the other
    window._tabifying = True                      # (as the old window did it)
    window.removeDockWidget(window.dock_search)
    window.addDockWidget(Qt.LeftDockWidgetArea, window.dock_search)   # below the others
    _both_open(window, (window.dock_search, window.dock_pages), qapp)
    window._tabifying = False
    assert len(_on_screen(window, Qt.LeftDockWidgetArea)) == 2, "stacked, as it was saved"
    stacked = window.saveState()
    window.restoreState(stacked)
    _settle(qapp)
    _both_open(window, (window.dock_search, window.dock_pages), qapp)
    assert window.dock_search in window.tabifiedDockWidgets(window.dock_pages)
    assert len(_on_screen(window, Qt.LeftDockWidgetArea)) == 1


# ---------------------------------------------------------------------------
# toolbars in side columns
# ---------------------------------------------------------------------------

def test_a_toolbar_on_the_left_edge_is_a_column_outside_the_rail_and_panels(window, qapp):
    window.show()
    _settle(qapp)
    measure = _bars(window)["toolbar_measure"]
    assert measure.isAreaAllowed(Qt.LeftToolBarArea)
    window.addToolBar(Qt.LeftToolBarArea, measure)
    _settle(qapp)
    assert window.toolBarArea(measure) == Qt.LeftToolBarArea
    assert measure.orientation() == Qt.Vertical
    assert measure.toolButtonStyle() == Qt.ToolButtonIconOnly
    rail = window.left_rail_bar.geometry()
    column = measure.geometry()
    assert column.right() < rail.left(), "outside the rail, at the window's edge"
    assert column.right() < window.dock_pages.geometry().left()
    # a second one has a column of its own too
    calculation = _bars(window)["toolbar_calculation"]
    window.addToolBar(Qt.LeftToolBarArea, calculation)
    _settle(qapp)
    assert calculation.geometry().x() != measure.geometry().x()
    assert max(calculation.geometry().right(), measure.geometry().right()) < \
        window.left_rail_bar.geometry().left()
    # remembered, and locking still works
    state = window.saveState()
    window._default_toolbar_rows()
    window.restoreState(state)
    _settle(qapp)
    assert window.toolBarArea(measure) == Qt.LeftToolBarArea
    assert measure.geometry().right() < window.left_rail_bar.geometry().left()
    window.lock_toolbars(True)
    assert not measure.isMovable()
    window.lock_toolbars(False)


def test_the_right_edge_works_the_same_way(window, qapp):
    window.show()
    _settle(qapp)
    tools = _bars(window)["toolbar_tools"]
    window.addToolBar(Qt.RightToolBarArea, tools)
    _settle(qapp)
    assert tools.geometry().left() > window.right_rail_bar.geometry().right()
    assert tools.geometry().left() > window.dock_properties.geometry().right()


def test_the_properties_toolbar_stays_top_or_bottom(window, qapp):
    """Its lists and boxes do not work stood on end."""
    window.show()
    _settle(qapp)
    style = window.style_bar
    assert not style.isAreaAllowed(Qt.LeftToolBarArea)
    window.addToolBar(Qt.LeftToolBarArea, style)             # as an old layout might
    window._toolbars_off_the_rails()
    assert window.toolBarArea(style) == Qt.TopToolBarArea


# ---------------------------------------------------------------------------
# the Properties toolbar
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["callout", "area"])
def test_the_properties_bar_fits_1280_with_one_row_and_no_overflow(window, qapp, kind):
    window.show()
    _settle(qapp)
    assert window.width() == 1280
    item = (CalloutItem("See detail 4", QRectF(0, 0, 120, 30), [QPointF(-60, 80)])
            if kind == "callout" else
            MeasureItem(AREA, [QPointF(0, 0), QPointF(160, 0), QPointF(160, 110)]))
    _select(window, item)
    _settle(qapp)
    bar = window.style_bar
    assert _in_overflow(bar) == []
    assert bar.sizeHint().width() <= bar.width()


def test_the_properties_bar_reads_line_fill_hatch_font_in_revus_order(window, qapp):
    window.show()
    _settle(qapp)
    _select(window, CalloutItem("Note", QRectF(0, 0, 120, 30), [QPointF(-60, 80)]))
    _settle(qapp)
    bar = window.style_bar
    shown = [bar.widgetForAction(a) for a in bar.actions() if a.isVisible()]
    order = [w for w in shown if w in (window.stroke_button, window.opacity_spin,
                                       window.dash_combo, window.width_spin,
                                       window.arrow_end_combo, window.arrow_size_spin,
                                       window.fill_button, window.fill_opacity_spin,
                                       window.callout_shape_combo, window.font_family_combo,
                                       window.font_spin, window.text_colour_button,
                                       window.font_style_button)]
    assert order == [window.stroke_button, window.opacity_spin, window.dash_combo,
                     window.width_spin, window.arrow_end_combo, window.arrow_size_spin,
                     window.fill_button, window.fill_opacity_spin,
                     window.callout_shape_combo, window.font_family_combo, window.font_spin,
                     window.text_colour_button, window.font_style_button]
    assert shown[0] is window.style_kind_menu
    assert window.arrow_start_combo not in shown, "a callout's leader has an End only"
    # compact, as Revu's
    assert window.width_spin.width() <= 82
    assert window.opacity_spin.width() <= 62 and window.fill_opacity_spin.width() <= 62
    assert window.font_spin.width() <= 58
    assert window.hatch_combo.sizeHint().width() <= 70
    # Set as Default is not on the bar; B/I/U are behind Style ▾
    assert window.default_button not in shown
    for button in window.font_buttons.values():
        assert button.window() is window.font_style_popup


def test_area_measurements_have_units_caption_and_totals(window, qapp):
    window.show()
    _settle(qapp)
    window.current_page().scale = window.current_page().scale.from_ratio(100)
    one = _select(window, MeasureItem(AREA, [QPointF(0, 0), QPointF(100, 0), QPointF(100, 100),
                                              QPointF(0, 100)]))
    two = MeasureItem(AREA, [QPointF(0, 0), QPointF(100, 0), QPointF(100, 100), QPointF(0, 100)])
    window.view.frame().add_markup(two, QPointF(400, 400))
    two.refresh(page=window.current_page())
    two.setSelected(True)
    window.refresh_selection()
    _settle(qapp)
    bar = window.style_bar
    shown = [bar.widgetForAction(a) for a in bar.actions() if a.isVisible()]
    for widget in (window.units_button, window.caption_button, window.totals_button,
                   window.highlight_button, window.cutout_button):
        assert widget in shown
    total = window.totals_button.currentText()
    assert total.startswith("Area = ")
    single = float(one.measured_text.split()[0])
    assert float(total.split("=")[1].split()[0]) == pytest.approx(2 * single, rel=0.02)
    # Caption ▾: Show Caption, one undo step
    window._fill_caption_menu()
    assert window.caption_show_action.isChecked()
    before = window.undo_stack.count()
    window.caption_show_action.setChecked(False)
    assert window.undo_stack.count() == before + 1
    shown_labels = [i.show_label for i in window.selected_items()]
    assert shown_labels == [False, False]
    # Units ▾: the page's area unit
    window._fill_units_panel()
    window.units_area_combo.setCurrentIndex(window.units_area_combo.findData("mm^2"))
    window._units_chosen()
    assert window.current_page().scale.area_unit == "mm^2"
    assert "mm²" in window.totals_button.currentText()


def _one_undo_step(window, change, check, pick):
    before = window.undo_stack.index()
    change()
    assert window.undo_stack.index() == before + 1
    assert check()
    window.undo_stack.undo()
    assert not check(), "undone in one step"
    window.undo_stack.redo()
    assert check()
    window.view.scene().clearSelection()         # undo and redo rebuild the markups
    pick().setSelected(True)
    window.refresh_selection()


def test_each_control_changes_the_selected_markup_in_one_undo_step(window, qapp):
    window.show()
    _settle(qapp)
    box = RectItem("rect")
    box.set_local_rect(QRectF(0, 0, 150, 90))
    _select(window, box)

    def the_box():                      # undo rebuilds the markups: found afresh
        return [i for i in window.view.frame().markups() if isinstance(i, RectItem)][0]

    _one_undo_step(window, lambda: window.width_spin.setValue(3.0),
                   lambda: the_box().style.width == pytest.approx(3.0), the_box)
    _one_undo_step(window, lambda: window.opacity_spin.setValue(40),
                   lambda: the_box().style.opacity == pytest.approx(0.4), the_box)
    _one_undo_step(window, lambda: window.fill_opacity_spin.setValue(20),
                   lambda: the_box().style.fill_opacity == pytest.approx(0.2), the_box)
    _one_undo_step(window, lambda: window.hatch_combo.setCurrentIndex(
        window.hatch_combo.findData("horizontal")),
        lambda: the_box().style.hatch == "horizontal", the_box)
    _one_undo_step(window, lambda: window.dash_combo.setCurrentIndex(
        window.dash_combo.findData("dash")),
        lambda: the_box().style.line_style == "dash", the_box)
    _one_undo_step(window, lambda: window.highlight_button.setChecked(True),
                   lambda: the_box().style.blend == "multiply", the_box)
    assert the_box().style.width == pytest.approx(3.0)

    window.view.scene().clearSelection()
    callout = _select(window, CalloutItem("Note", QRectF(0, 0, 120, 30), [QPointF(-60, 80)]),
                      QPointF(500, 300))

    def the_callout():
        return [i for i in window.view.frame().markups() if isinstance(i, CalloutItem)][0]

    _one_undo_step(window, lambda: window.font_spin.setValue(22),
                   lambda: the_callout().style.font_size == pytest.approx(22), the_callout)
    # typed into the size box, as Revu's takes it
    window.font_spin.setEditText("18")
    _one_undo_step(window, lambda: window.font_spin.lineEdit().editingFinished.emit(),
                   lambda: the_callout().style.font_size == pytest.approx(18), the_callout)
    _one_undo_step(window, lambda: window.font_buttons["bold"].setChecked(True),
                   lambda: the_callout().style.bold, the_callout)
    _one_undo_step(window, lambda: window.arrow_size_spin.setValue(2.0),
                   lambda: the_callout().style.arrow_size == pytest.approx(2.0), the_callout)
    assert window.arrow_size_spin.currentText() == "200%"
    _one_undo_step(window, lambda: window.callout_shape_combo.setCurrentIndex(1),
                   lambda: the_callout().shape_kind == "cloud", the_callout)
    assert callout is not None


def test_the_type_menu_keeps_calcforges_extras(window, qapp):
    window.show()
    _settle(qapp)
    box = RectItem("rect")
    box.set_local_rect(QRectF(0, 0, 150, 90))
    _select(window, box)
    window.style_kind_menu.showPopup()
    _settle(qapp)
    panel = window.style_more_popup
    assert panel.isVisible()
    for widget in (window.subject_field, window.dash_scale_spin, window.hatch_colour_button,
                   window.hatch_scale_spin, window.hatch_opacity_spin, window.default_button):
        assert widget.window() is panel and widget.isVisible()
    assert window.style_kind_label.text() == "Rectangle"
    assert window.default_button.isEnabled()
    panel.hide()
    before = window.undo_stack.count()
    window.dash_scale_spin.setValue(2.0)
    assert window.undo_stack.count() == before + 1
