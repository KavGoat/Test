"""Panels and toolbars: pinning, hiding, moving, and remembering.

Somebody who arranges the window once should find it that way tomorrow, and a
panel they pinned should stay where they put it however clumsy the next drag
is.
"""
import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QDockWidget, QToolBar

from markforge.ui.docks import PanelDock


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


def test_a_panel_can_be_hidden_and_brought_back(window):
    properties = panels(window)["dock_properties"]
    assert properties.isVisibleTo(window)
    properties.close()
    assert not properties.isVisibleTo(window)
    properties.toggleViewAction().trigger()
    assert properties.isVisibleTo(window)


def test_show_panels_brings_back_one_default_on_each_side(window):
    for dock in window.panels:
        dock.close()
    window.show_all_panels()
    visible = {dock.objectName() for dock in window.panels
               if dock.isVisibleTo(window)}
    assert visible == {"dock_pages", "dock_properties"}


def test_pinning_a_floating_panel_brings_it_home(window):
    properties = panels(window)["dock_properties"]
    properties.setFloating(True)
    assert properties.isFloating()
    properties.set_pinned(True)
    assert not properties.isFloating()


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
    from markforge.ui import dialogs

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
    from markforge.ui import dialogs
    from markforge.ui.tools import TOOLS

    dialog = dialogs.ToolbarDialog(TOOLS, {t.key for t in TOOLS}, window)
    assert set(dialog.boxes) == {tool.key for tool in TOOLS}
    assert all(box.isChecked() for box in dialog.boxes.values())
    dialog._set_all(False)
    assert dialog.chosen() == set()
    dialog.deleteLater()


# ---------------------------------------------------------------------------
# remembering it
# ---------------------------------------------------------------------------

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
    visible = {dock.objectName() for dock in window.panels
               if dock.isVisibleTo(window)}
    assert visible == {"dock_pages", "dock_properties"}
    assert all(bar.isMovable() for bar in window.toolbars)
    assert window.tool_actions["ellipse"].isVisible()
    assert QSettings("MarkForge", "MarkForge").value("window/state") is None


# ---------------------------------------------------------------------------
# themes
# ---------------------------------------------------------------------------

def test_the_dark_theme_reaches_the_palette_as_well_as_the_stylesheet(window, qapp):
    from PySide6.QtGui import QPalette
    from markforge.theme import DARK, LIGHT, tokens

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
    from markforge.ui import icons

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


def test_a_toolbar_has_a_grip_to_pick_it_up_by(window):
    """A movable toolbar with no handle is a toolbar nobody can move."""
    from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionToolBar

    sheet = QApplication.instance().styleSheet()
    assert "QToolBar::handle" not in sheet or "width: 0" not in sheet
    for bar in window.toolbars:
        assert bar.isMovable()
        option = QStyleOptionToolBar()
        bar.initStyleOption(option)
        extent = bar.style().pixelMetric(QStyle.PM_ToolBarHandleExtent, option, bar)
        assert extent > 0, f"{bar.objectName()} has no grip"


# ---------------------------------------------------------------------------
# everything is remembered
# ---------------------------------------------------------------------------

def test_a_rebound_key_is_saved_the_moment_it_changes(window):
    """A rebinding that only survives a clean quit does not survive a crash."""
    from markforge.ui.shortcuts import ShortcutManager

    window.shortcuts.set_sequence("tool.rect", "y")
    fresh = ShortcutManager()           # as if the application had restarted
    assert fresh.sequence("tool.rect") == "y"


def test_the_theme_is_remembered(window):
    from markforge.app import current_theme
    from markforge.theme import DARK, LIGHT

    window.toggle_theme(True)
    assert current_theme() == DARK
    window.toggle_theme(False)
    assert current_theme() == LIGHT


def test_moving_a_panel_writes_the_layout_out_by_itself(window):
    """Not only on a clean quit: a crash should not cost the arrangement."""
    from PySide6.QtCore import QSettings

    QSettings("MarkForge", "MarkForge").remove("window/state")
    window.addDockWidget(Qt.RightDockWidgetArea, panels(window)["dock_pages"])
    assert window._layout_timer.isActive(), "nothing scheduled a save"
    window._layout_timer.stop()
    window.save_layout()
    assert QSettings("MarkForge", "MarkForge").value("window/state") is not None


def test_hiding_a_panel_schedules_a_save(window):
    window._layout_timer.stop()
    window.show_panel("dock_layers", True)
    window._layout_timer.stop()
    window.show_panel("dock_layers", False)
    assert window._layout_timer.isActive()


def test_a_direct_layout_save_consumes_the_pending_timer(window):
    window.note_layout_change()
    assert window._layout_timer.isActive()
    window.save_layout()
    assert not window._layout_timer.isActive()


def test_the_lookup_panels_are_each_behind_their_own_icon(window):
    """No stack of tabs along the bottom: every panel has an icon on a rail."""
    from markforge.ui.rail import LEFT, RIGHT

    for dock in window.reference_docks:
        name = dock.objectName()
        assert name in window.PANEL_ICONS
        side = window.panel_sides[name]
        rail = window.left_rail if side == LEFT else window.right_rail
        assert name in rail.buttons
        assert window.dockWidgetArea(dock) in (Qt.LeftDockWidgetArea,
                                               Qt.RightDockWidgetArea)


def test_properties_keeps_the_right_side_to_itself(window):
    assert window.dockWidgetArea(window.dock_properties) == Qt.RightDockWidgetArea
    assert window.dockWidgetArea(window.dock_pages) == Qt.LeftDockWidgetArea


def test_page_navigation_and_label_are_centred_in_the_footer(window, qapp):
    window.current_page().label = "Foundation"
    window.refresh_page_bar()
    window.show()
    qapp.processEvents()

    status = window.statusBar()
    assert window.page_label.text() == "· Foundation"
    assert abs(window.page_navigation.geometry().center().x()
               - status.rect().center().x()) <= 1


def test_page_thumbnail_uses_a_centred_responsive_grid_cell(window, qapp):
    window.show()
    qapp.processEvents()
    page_list = window.pages_panel.list
    entry = page_list.item(0)
    box = page_list.visualItemRect(entry)

    assert page_list.gridSize().width() == page_list.viewport().width()
    assert abs(box.center().x() - page_list.viewport().rect().center().x()) <= 1
    assert entry.textAlignment() & Qt.AlignHCenter


def test_properties_can_be_squeezed_away_and_opened_out_again(window, qapp):
    window.show()
    qapp.processEvents()
    dock = window.dock_properties

    window.resizeDocks([dock], [0], Qt.Horizontal)
    qapp.processEvents()
    assert dock.width() <= 1

    window.resizeDocks([dock], [320], Qt.Horizontal)
    qapp.processEvents()
    assert dock.width() >= 300


def test_the_collapse_button_matches_the_state(window):
    dock = panels(window)["dock_layers"]
    bar = dock.titleBarWidget()
    bar.collapse.setChecked(True)
    assert dock.collapsed
    dock.set_collapsed(False)
    assert not bar.collapse.isChecked()


def test_showing_panels_unrolls_the_default_panels(window):
    for dock in window.panels:
        dock.set_collapsed(True)
    window.show_all_panels()
    assert not window.dock_pages.collapsed
    assert not window.dock_properties.collapsed


def test_rolling_a_panel_up_schedules_a_save(window):
    window._layout_timer.stop()
    panels(window)["dock_markups"].set_collapsed(True)
    assert window._layout_timer.isActive()


def _icon_pixels(action, size=24):
    from PySide6.QtCore import QSize
    image = action.icon().pixmap(QSize(size, size)).toImage()
    return [image.pixel(x, y)
            for y in range(0, image.height(), 3)
            for x in range(0, image.width(), 3)]


def test_every_icon_on_the_window_is_redrawn_for_the_theme(window):
    """An icon set once and forgotten keeps its old ink and vanishes."""
    from PySide6.QtGui import QAction

    before = {action: _icon_pixels(action) for action in window._icon_names}
    window.toggle_theme(True)
    try:
        changed = [action for action in before
                   if _icon_pixels(action) != before[action]]
        assert len(changed) == len(before), \
            f"{len(before) - len(changed)} icon(s) kept their light-theme ink"
    finally:
        window.toggle_theme(False)


def test_undo_and_redo_are_among_them(window):
    assert window.act_undo in window._icon_names
    assert window.act_redo in window._icon_names
    before = _icon_pixels(window.act_undo)
    window.toggle_theme(True)
    try:
        assert _icon_pixels(window.act_undo) != before
    finally:
        window.toggle_theme(False)


def test_no_action_with_an_icon_was_left_out(window):
    """Every icon-carrying action on the window must be registered."""
    from PySide6.QtGui import QAction

    stray = [action.text() for action in window.findChildren(QAction)
             # Qt's own clear-buttons on line edits are not ours to re-tint.
             if not action.objectName().startswith("_q_")
             and not action.icon().isNull() and action not in window._icon_names]
    assert stray == []


def test_there_is_one_shortcuts_window_not_two(window):
    labels = [entry.text().replace("&", "")
              for top in window.menuBar().actions()
              for entry in top.menu().actions()]
    assert labels.count("Shortcuts…") == 1
    assert "Keyboard shortcuts" not in labels


def test_preferences_and_shortcuts_live_under_settings(window):
    menus = {action.text().replace("&", ""): action.menu()
             for action in window.menuBar().actions()}
    assert "Settings" in menus
    labels = [action.text() for action in menus["Settings"].actions()]
    assert labels == ["Preferences…", "Shortcuts…"]
    edit = [action.text() for action in menus["Edit"].actions()]
    help_labels = [action.text() for action in menus["Help"].actions()]
    assert "Preferences…" not in edit
    assert "Shortcuts…" not in help_labels

