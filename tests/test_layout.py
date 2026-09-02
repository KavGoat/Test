"""Panels and toolbars: pinning, hiding, moving, and remembering.

Somebody who arranges the window once should find it that way tomorrow, and a
panel they pinned should stay where they put it however clumsy the next drag
is.
"""
import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QDockWidget, QToolBar

from calcforge.ui.docks import PanelDock


def panels(window):
    return {dock.objectName(): dock for dock in window.panels}


def toolbars(window):
    return {bar.objectName(): bar for bar in window.toolbars}


# ---------------------------------------------------------------------------
# panels
# ---------------------------------------------------------------------------

def test_every_panel_is_one_that_can_be_pinned(window):
    assert window.panels
    for dock in window.panels:
        assert isinstance(dock, PanelDock)
        assert dock.objectName()


def test_the_expected_panels_are_there(window):
    assert set(panels(window)) == {
        "dock_pages", "dock_properties", "dock_variables", "dock_functions",
        "dock_layers", "dock_markups", "dock_problems"}


def test_a_panel_can_be_hidden_and_brought_back(window):
    properties = panels(window)["dock_properties"]
    assert properties.isVisibleTo(window)
    properties.close()
    assert not properties.isVisibleTo(window)
    properties.toggleViewAction().trigger()
    assert properties.isVisibleTo(window)


def test_show_every_panel_brings_them_all_back(window):
    for dock in window.panels:
        dock.close()
    window.show_all_panels()
    assert all(dock.isVisibleTo(window) for dock in window.panels)


def test_a_pinned_panel_cannot_be_dragged_or_floated(window):
    variables = panels(window)["dock_variables"]
    assert variables.features() & QDockWidget.DockWidgetMovable

    variables.set_pinned(True)
    assert variables.pinned
    assert not variables.features() & QDockWidget.DockWidgetMovable
    assert not variables.features() & QDockWidget.DockWidgetFloatable
    # …but it can still be put away
    assert variables.features() & QDockWidget.DockWidgetClosable


def test_pinning_a_floating_panel_brings_it_home(window):
    properties = panels(window)["dock_properties"]
    properties.setFloating(True)
    assert properties.isFloating()
    properties.set_pinned(True)
    assert not properties.isFloating()


def test_the_title_bar_has_pin_float_and_close(window):
    bar = panels(window)["dock_variables"].titleBarWidget()
    assert bar.label.text() == "Variables"
    assert bar.pin.isCheckable()
    assert bar.float_button.isEnabled()
    assert bar.close_button.isEnabled()


def test_the_pin_button_pins_the_panel(window):
    dock = panels(window)["dock_variables"]
    bar = dock.titleBarWidget()
    bar.pin.setChecked(True)
    assert dock.pinned
    assert not bar.float_button.isEnabled()   # nothing to float while pinned
    bar.pin.setChecked(False)
    assert not dock.pinned
    assert bar.float_button.isEnabled()


def test_pin_every_panel_at_once(window):
    window.pin_all_panels(True)
    assert all(dock.pinned for dock in window.panels)
    window.pin_all_panels(False)
    assert not any(dock.pinned for dock in window.panels)


def test_a_panel_can_go_to_any_edge(window):
    pages = panels(window)["dock_pages"]
    assert pages.allowedAreas() == Qt.AllDockWidgetAreas
    for area in (Qt.RightDockWidgetArea, Qt.TopDockWidgetArea,
                 Qt.BottomDockWidgetArea, Qt.LeftDockWidgetArea):
        window.addDockWidget(area, pages)
        assert window.dockWidgetArea(pages) == area


# ---------------------------------------------------------------------------
# toolbars
# ---------------------------------------------------------------------------

def test_the_toolbars_can_be_moved_to_any_edge(window):
    for bar in window.toolbars:
        assert bar.isMovable()
        assert bar.allowedAreas() == Qt.AllToolBarAreas
    tools = toolbars(window)["toolbar_tools"]
    for area in (Qt.LeftToolBarArea, Qt.RightToolBarArea, Qt.BottomToolBarArea,
                 Qt.TopToolBarArea):
        window.addToolBar(area, tools)
        assert window.toolBarArea(tools) == area


def test_the_toolbars_can_be_locked(window):
    window.lock_toolbars(True)
    assert not any(bar.isMovable() for bar in window.toolbars)
    window.lock_toolbars(False)
    assert all(bar.isMovable() for bar in window.toolbars)


def test_a_toolbar_can_be_hidden_and_brought_back(window):
    style = toolbars(window)["toolbar_style"]
    assert style.toggleViewAction().isCheckable()
    style.setVisible(False)
    assert not style.isVisibleTo(window)
    style.setVisible(True)
    assert style.isVisibleTo(window)


def test_choosing_which_tools_are_on_the_toolbar(window, monkeypatch):
    from calcforge.ui import dialogs

    monkeypatch.setattr(dialogs.ToolbarDialog, "exec",
                        lambda self: dialogs.QDialog.Accepted)
    monkeypatch.setattr(dialogs.ToolbarDialog, "chosen",
                        lambda self: {"select", "rect", "cloud"})
    window.customise_toolbar()

    assert window.tool_actions["rect"].isVisible()
    assert not window.tool_actions["ellipse"].isVisible()
    # a hidden tool is still reachable by its key
    from PySide6.QtCore import QPointF
    assert window.run_typed_binding("e", Qt.NoModifier, QPointF(100, 100))
    assert window.view.current_tool().key == "ellipse"


def test_the_toolbar_dialog_lists_every_tool(window):
    from calcforge.ui import dialogs
    from calcforge.ui.tools import TOOLS

    dialog = dialogs.ToolbarDialog(TOOLS, {t.key for t in TOOLS}, window)
    assert set(dialog.boxes) == {tool.key for tool in TOOLS}
    assert all(box.isChecked() for box in dialog.boxes.values())
    dialog._set_all(False)
    assert dialog.chosen() == set()
    dialog.deleteLater()


# ---------------------------------------------------------------------------
# remembering it
# ---------------------------------------------------------------------------

def test_the_arrangement_survives_a_restart(window, qapp):
    from calcforge.ui.mainwindow import MainWindow

    pages = panels(window)["dock_pages"]
    window.addDockWidget(Qt.RightDockWidgetArea, pages)
    pages.set_pinned(True)
    panels(window)["dock_functions"].close()
    window.lock_toolbars(True)
    window.visible_tools = {"select", "rect"}
    window.save_layout()

    second = MainWindow()
    second.confirm_discard = lambda: True
    try:
        again = panels(second)
        assert second.dockWidgetArea(again["dock_pages"]) == Qt.RightDockWidgetArea
        assert again["dock_pages"].pinned
        assert not again["dock_functions"].isVisibleTo(second)
        assert not any(bar.isMovable() for bar in second.toolbars)
        assert second.tool_actions["rect"].isVisible()
        assert not second.tool_actions["ellipse"].isVisible()
    finally:
        second.close()
        second.deleteLater()


def test_resetting_the_layout_puts_everything_back(window):
    pages = panels(window)["dock_pages"]
    window.addDockWidget(Qt.RightDockWidgetArea, pages)
    window.pin_all_panels(True)
    window.lock_toolbars(True)
    panels(window)["dock_layers"].close()
    window.visible_tools = {"select"}
    window.apply_visible_tools()

    window.reset_layout()

    assert window.dockWidgetArea(pages) == Qt.LeftDockWidgetArea
    assert not any(dock.pinned for dock in window.panels)
    assert all(dock.isVisibleTo(window) for dock in window.panels)
    assert all(bar.isMovable() for bar in window.toolbars)
    assert window.tool_actions["ellipse"].isVisible()
    assert QSettings("CalcForge", "CalcForge").value("window/state") is None


# ---------------------------------------------------------------------------
# themes
# ---------------------------------------------------------------------------

def test_the_dark_theme_reaches_the_palette_as_well_as_the_stylesheet(window, qapp):
    from PySide6.QtGui import QPalette
    from calcforge.theme import DARK, LIGHT, tokens

    window.toggle_theme(True)
    palette = qapp.palette()
    assert palette.color(QPalette.Base).name() == tokens(DARK)["field"]
    assert palette.color(QPalette.Window).name() == tokens(DARK)["surface"]
    assert palette.color(QPalette.Text).lightness() > 150     # light text

    window.toggle_theme(False)
    palette = qapp.palette()
    assert palette.color(QPalette.Base).name() == tokens(LIGHT)["field"]
    assert palette.color(QPalette.Text).lightness() < 100     # dark text


def test_icons_are_redrawn_for_the_theme(window):
    from calcforge.ui import icons

    window.toggle_theme(True)
    dark_ink = icons.INK
    assert icons.icon_theme() == "dark"
    window.toggle_theme(False)
    assert icons.icon_theme() == "light"
    assert icons.INK != dark_ink
    # dark ink on a dark toolbar is an empty toolbar
    from PySide6.QtGui import QColor
    assert QColor(dark_ink).lightness() > QColor(icons.INK).lightness()


def test_a_toolbar_icon_actually_changes_colour(window):
    """The action has to be given the new drawing, not just the palette."""
    from PySide6.QtCore import QSize

    def pixels(action):
        image = action.icon().pixmap(QSize(24, 24)).toImage()
        return {image.pixel(x, y) for x in range(24) for y in range(24)}

    action = window.tool_actions["select"]
    window.toggle_theme(False)
    light = pixels(action)
    window.toggle_theme(True)
    dark = pixels(action)
    assert light != dark


def test_the_page_looks_the_same_in_both_themes(window):
    """The sheet is the sheet, whatever the frame around it does."""
    window.select_tool("text")
    from tests.test_usability import drag as ui_drag
    ui_drag(window.view, 100, 100, 340, 160)
    box = window.view.editing_item()
    box.set_text("Steel beam design")
    box.style.text_color = "#111318"
    window.view.end_item_edit()

    window.toggle_theme(False)
    light = window.current_page().frame.render_image(dpi=60, for_print=False)
    window.toggle_theme(True)
    dark = window.current_page().frame.render_image(dpi=60, for_print=False)
    assert light == dark, "the theme changed what is on the paper"
