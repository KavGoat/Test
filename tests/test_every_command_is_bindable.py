"""Every command a person can give can be given a key (the user,
2026-10-16: "Whatever features you add should show up in the shortcuts
manager as a feature, and then the user can add whatever shortcuts they want
with typical shortcut keys").

The walk opens the real window's menus the way a person does — the menu bar
(each menu shown, so what fills itself as it opens is filled), the
right-click menu of each kind of thing on the page, of a thumbnail, a cell, a
heading, a sheet tab, a document tab, a Markups List row, the Tool Chest, a
ruler, the Variables panel — and reads every toolbar and panel button. The
right-click menus run modally, so each is read from
``QApplication.activePopupWidget()`` by a timer while it is open.

Every entry must carry a command id that the Keyboard Shortcuts list knows,
under a real category. Entries that are data (Open Recent's files, Undo
History's steps, a tool set's name, a filter's values) and greyed lines that
only say something are the only ones left out.

Then a key is given to a command from each category through the dialog
itself — keys pressed into its key box — and pressed where the command acts,
and the command has to have run.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QKeyCombination, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QContextMenuEvent, QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (QAbstractButton, QApplication, QLineEdit, QMenu,
                               QPushButton, QToolBar, QToolButton, QWidgetAction)

from calcforge.ui import bindable
from tests.test_usability import drag, on_page


def right_click(view, x, y):
    """A right-click on the canvas at scene point (x, y), delivered where
    Qt delivers a mouse's: to the viewport (the scroll area itself ignores
    a mouse's context-menu event)."""
    local = view.mapFromScene(QPointF(x, y))
    QApplication.sendEvent(view.viewport(), QContextMenuEvent(
        QContextMenuEvent.Mouse, local, view.viewport().mapToGlobal(local)))


def pump(times: int = 2) -> None:
    for _ in range(times):
        QApplication.instance().processEvents()


# ---------------------------------------------------------------------------
# reading menus
# ---------------------------------------------------------------------------
class Walk:
    """What the walk found: every entry and button, and where."""

    def __init__(self, window):
        self.window = window
        self.entries: list[dict] = []
        self.problems: list[str] = []

    # -- menus -----------------------------------------------------------------
    def read(self, menu: QMenu, where: str, path=(), depth=0) -> None:
        """Every entry of *menu*, each submenu opened as a person opens it."""
        if depth > 6:
            return
        for action in menu.actions():
            if action.isSeparator() or not action.isVisible():
                continue
            text = bindable.clean(action.text())
            if isinstance(action, QWidgetAction) and not text:
                continue
            sub = action.menu()
            self.entries.append(dict(
                where=where, path=" ▸ ".join(list(path) + [text]), text=text,
                id=action.property(bindable.COMMAND), sub=sub is not None,
                data=bool(action.property(bindable.DATA) or menu.property(bindable.DATA)),
                info=bindable.is_info(action)))
            if sub is not None:
                sub.popup(menu.mapToGlobal(QPoint(menu.width(), 0)))
                pump(1)
                self.read(sub, where, tuple(path) + (text,), depth + 1)
                sub.close()
                pump(1)

    def open_and_read(self, menu, where: str) -> None:
        """A menu built and handed back, opened as it would be."""
        if menu is None:
            self.problems.append(f"{where}: no menu was built")
            return
        menu.popup(QPoint(40, 40))
        pump(1)
        self.read(menu, where)
        menu.close()
        pump(1)

    def capture(self, trigger, where: str) -> None:
        """Run *trigger*, which opens a menu modally, and read that menu
        while it is open."""
        seen = []

        def poll():
            popup = QApplication.activePopupWidget()
            if isinstance(popup, QMenu) and not seen:
                seen.append(popup)
                timer.stop()
                self.read(popup, where)
                while QApplication.activePopupWidget() is not None:
                    QApplication.activePopupWidget().close()
        timer = QTimer()
        timer.setInterval(5)
        timer.timeout.connect(poll)
        timer.start()
        try:
            trigger()
            pump(2)
        finally:
            timer.stop()
        if not seen:
            self.problems.append(f"{where}: no menu opened")

    # -- bars and panels -----------------------------------------------------
    def button(self, button: QAbstractButton, where: str) -> None:
        if not button.isVisibleTo(button.window()) or bindable.is_field(button):
            return               # a value (a colour, a tick box) or a menu's face
        command = button.property(bindable.BUTTON)
        action = button.defaultAction() if isinstance(button, QToolButton) else None
        if not command and action is not None:
            command = action.property(bindable.COMMAND)
        label = bindable.clean(button.text()) or bindable.clean(
            button.toolTip().split("\n")[0]) or button.objectName()
        self.entries.append(dict(where=where, path=label, text=label, id=command, sub=False,
                                 data=bool(button.property(bindable.DATA)), info=False))
        menu = button.menu() if isinstance(button, (QToolButton, QPushButton)) else None
        if menu is not None and (action is None or action.menu() is not menu):
            self.open_and_read(menu, f"{where} ▸ {label}")

    def toolbar(self, bar: QToolBar) -> None:
        where = f"{bar.windowTitle()} toolbar"
        for action in bar.actions():
            if action.isSeparator() or not action.isVisible():
                continue
            widget = bar.widgetForAction(action)
            if isinstance(action, QWidgetAction) or (
                    widget is not None and not isinstance(widget, QToolButton)):
                target = action.defaultWidget() if isinstance(action, QWidgetAction) \
                    else widget
                if target is None:
                    continue
                buttons = [target] if isinstance(target, QAbstractButton) else \
                    target.findChildren(QAbstractButton)
                for button in buttons:
                    self.button(button, where)
                continue
            text = bindable.clean(action.text()) or action.toolTip().split("\n")[0]
            self.entries.append(dict(where=where, path=text, text=text,
                                     id=action.property(bindable.COMMAND), sub=False,
                                     data=False, info=False))
            menu = action.menu() or (widget.menu() if isinstance(widget, QToolButton)
                                     else None)
            if menu is not None:
                self.open_and_read(menu, f"{where} ▸ {text}")

    def widgets(self, root, where: str) -> None:
        for button in root.findChildren(QAbstractButton):
            self.button(button, where)

    # -- the verdict -----------------------------------------------------------
    def unbindable(self) -> list[str]:
        from calcforge.ui.shortcuts import BY_ID
        known = {b.action_id: b for b in self.window.shortcuts.bindings()}
        out = []
        for entry in self.entries:
            if entry["sub"] and not entry["id"]:
                continue
            if entry["data"] or entry["info"]:
                continue
            command = entry["id"]
            binding = known.get(command) or BY_ID.get(command)
            if not command:
                out.append(f"{entry['where']}: {entry['path']} — no command id")
            elif binding is None:
                out.append(f"{entry['where']}: {entry['path']} — {command} not in the list")
            elif binding.category in ("", "Other"):
                out.append(f"{entry['where']}: {entry['path']} — {command} has no category "
                           "(add it to bindable_list.COMMANDS)")
        return sorted(set(out))


# ---------------------------------------------------------------------------
# the walk
# ---------------------------------------------------------------------------
def shown(window):
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    pump()
    return window


def _menubar(walk):
    for top in walk.window.menuBar().actions():
        menu = top.menu()
        if menu is not None:
            walk.open_and_read(menu, bindable.clean(top.text()))


def _bars_and_panels(walk, state=""):
    window = walk.window
    for bar in window.findChildren(QToolBar):
        if bar.isVisible():
            walk.toolbar(bar)
    for dock in window.panels:
        title = dock.windowTitle()
        was_hidden = dock.isHidden()
        window.show_panel(dock.objectName(), True)
        pump()
        for section in getattr(dock.widget(), "sections", []):
            section.set_collapsed(False)           # the Maths panel's, every one open
        pump()
        if dock.widget() is not None:
            walk.widgets(dock.widget(), f"{title} panel{state}")
        if was_hidden:
            window.show_panel(dock.objectName(), False)
    if not window.markups_panel.isVisible():
        window.act_markups_list.setChecked(True)
        pump()
    walk.widgets(window.markups_panel, f"Markups List{state}")
    walk.widgets(window.statusBar(), "Status bar")


def _draw(window, tool, x0, y0, x1, y1):
    """Draw one markup with *tool* the way a person does."""
    from calcforge.ui.tools import ANCHOR, CLICK, CLOUD, CLOUDY, DRAG, FREE, POLY, TOOL_MAP
    from tests.test_usability import click, double_click, press_key, type_text
    view = window.view
    mode = TOOL_MAP[tool].mode
    window.select_tool(tool)
    p, q = on_page(window, 0, x0, y0), on_page(window, 0, x1, y1)
    view.centerOn(QPointF(*p))
    pump(1)
    if mode in (DRAG, FREE, CLOUDY):
        drag(view, p[0], p[1], q[0], q[1])
    elif mode == POLY:
        click(view, p[0], p[1])
        click(view, q[0], p[1])
        double_click(view, q[0], q[1])
    elif mode == CLICK:
        click(view, p[0], p[1])
    elif mode == ANCHOR:
        click(view, p[0], p[1])
        click(view, q[0], q[1])
    elif mode == CLOUD:
        drag(view, p[0], p[1], q[0], q[1])
        click(view, q[0] + 30, q[1] + 30)
    pump(1)
    if view.is_editing():
        type_text(view, "x")
    press_key(view, Qt.Key_Escape)
    press_key(view, Qt.Key_Escape)
    window.select_tool("select")
    pump(1)


def _item_menu(walk, item, where):
    window = walk.window
    window.view.scene().clearSelection()
    item.setSelected(True)
    pump(1)
    centre = item.mapToScene(item.local_rect().center()) if hasattr(item, "local_rect") \
        else item.sceneBoundingRect().center()
    window.view.centerOn(centre)
    pump(1)
    walk.capture(lambda: right_click(window.view, centre.x(), centre.y()), where)
    # and its Properties: the buttons there are commands too
    window.show_panel("dock_properties", True)
    window.view.scene().clearSelection()
    item.setSelected(True)
    pump(4)
    walk.widgets(window.properties_panel, f"Properties of {where[len('Right-click '):]}")


def markup_scenarios(walk):
    """Every kind of markup's right-click menu, the empty page's, the
    Markups List's, the Tool Chest's, a thumbnail's, a document tab's and a
    ruler's."""
    from tests.test_usability import markups
    from calcforge.ui.mainwindow import forget_recent_files, remember_recent_file
    window = walk.window
    # File ▸ Open Recent with a file on it: Clear Recent Files is a command
    remember_recent_file(__file__)
    made = {}
    spots = [(60 + 130 * (n % 4), 60 + 90 * (n // 4)) for n in range(40)]
    from calcforge.ui.tools import ANCHOR, CLICK, CLOUD, CLOUDY, DRAG, FREE, POLY, TOOLS
    slot = 0
    for tool in TOOLS:
        if tool.mode not in (DRAG, FREE, POLY, CLICK, ANCHOR, CLOUD, CLOUDY) or tool.key in (
                "select", "pan", "snapshot", "crop", "crop_image", "image", "calibrate",
                "viewport", "whiteout", "table", "eraser", "zoom"):
            continue
        before = {id(i) for i in markups(window)}
        x, y = spots[slot]
        slot += 1
        try:
            _draw(window, tool.key, x, y, x + 90, y + 50)
        except Exception as error:  # noqa: BLE001 - reported below
            walk.problems.append(f"drawing {tool.key}: {error!r}")
            continue
        new = [i for i in markups(window) if id(i) not in before]
        if new:
            made[tool.key] = new[0]
        if slot >= len(spots):
            break
    kinds = {}
    for key, item in made.items():
        kinds.setdefault((type(item).__name__, getattr(item, "kind", "")), (key, item))
    for (name, kind), (key, item) in kinds.items():
        _item_menu(walk, item, f"Right-click a {key} markup")
    rects = [i for k, i in made.items() if k in ("rect", "ellipse")]
    if len(rects) >= 2:
        window.view.scene().clearSelection()
        for item in rects:
            item.setSelected(True)
        centre = rects[0].mapToScene(rects[0].local_rect().center())
        walk.capture(lambda: right_click(window.view, centre.x(), centre.y()),
                     "Right-click two markups")
    # the menu bar with markups selected: Tools ▸ Selected Markups is full
    _menubar(walk)
    forget_recent_files()
    # the empty page
    window.view.scene().clearSelection()
    spot = on_page(window, 0, 520, 760)
    window.view.centerOn(QPointF(*spot))
    pump(1)
    walk.capture(lambda: right_click(window.view, *spot), "Right-click the empty page")
    # the Markups List
    panel = window.markups_panel
    window.show_markups_list(True) if hasattr(window, "show_markups_list") else None
    pump()
    panel.tree.selectAll()
    pump(1)
    walk.open_and_read(panel._row_menu(None), "Markups List row")
    window.view.scene().clearSelection()
    pump(1)
    # Tool Chest
    chest = window.toolsets_panel
    walk.open_and_read(chest.build_chest_menu(), "Tool Chest ▸ Tool Sets")
    walk.open_and_read(chest.build_set_menu(), "Tool Chest ▸ a set's gear")
    walk.open_and_read(chest.build_menu(), "Tool Chest ▸ a tool")
    # a thumbnail, through its own right-click
    window.add_page()
    pump()
    strip = window.pages_panel.list
    window.show_panel("dock_pages", True)
    pump()
    point = strip.visualItemRect(strip.item(0)).center()
    walk.capture(lambda: window.pages_panel._context_menu(point), "Right-click a thumbnail")
    # a document tab (two documents open)
    window.open_in_new_tab()
    pump()
    bar = window.document_tabs
    walk.capture(lambda: window._tab_context_menu(bar.tabRect(0).center()),
                 "Right-click a document tab")
    # a ruler
    window.act_rulers.setChecked(True)
    pump()
    from calcforge.ui.rulers import Ruler
    rulers = window.findChildren(Ruler)
    if rulers:
        ruler = rulers[0]
        walk.capture(lambda: ruler.contextMenuEvent(QContextMenuEvent(
            QContextMenuEvent.Mouse, QPoint(5, 5), ruler.mapToGlobal(QPoint(5, 5)))),
            "Right-click a ruler")
    else:
        walk.problems.append("no ruler to right-click")
    _bars_and_panels(walk)
    # each tool in hand: the Properties toolbar and the Markup Styles bar
    # show what that tool has
    from calcforge.ui.tools import TOOLS as ALL_TOOLS
    window.show_panel("dock_properties", True)
    for tool in ALL_TOOLS:
        window.select_tool(tool.key)
        pump(1)
        walk.toolbar(window.style_bar)
        walk.toolbar(window.markup_styles.bar)
        walk.widgets(window.properties_panel, f"Properties with {tool.key} in hand")
    # a markup style of one's own, and its right-click menu
    window.select_tool("rect")
    pump(1)
    bar = window.markup_styles.bar
    bar.refresh(force=True)
    if bar.add_button is not None:
        bar.add_button.click()
        pump()
    numbered = [b for b in bar.buttons if getattr(b, "number", 0)]
    if numbered:
        walk.toolbar(bar)
        button = numbered[0]
        walk.capture(lambda: bar._menu(button, QPoint(4, 4)), "Right-click a markup style")
    else:
        walk.problems.append("no markup style could be made")
    window.select_tool("select")
    pump(1)


def table_scenarios(walk):
    from tests.test_tables import cell_scene, make_table
    window = walk.window
    table = make_table(window)
    window.view.tables.open(table)
    pump()
    point = cell_scene(table, "B2")
    walk.capture(lambda: right_click(window.view, point.x(), point.y()),
                 "Right-click a table cell")
    tables = window.view.tables
    walk.capture(lambda: tables.context_menu(QPoint(10, 10), heading=("row", 1)),
                 "Right-click a row heading")
    walk.capture(lambda: tables.context_menu(QPoint(10, 10), heading=("col", 1)),
                 "Right-click a column heading")
    _bars_and_panels(walk, " (table open)")
    _menubar(walk)
    tables.close()
    pump()
    _item_menu(walk, table, "Right-click a closed table")


def sheet_scenarios(walk):
    from tests.test_sheet_pages import open_at, sheet_page
    from tests.test_tables import cell_scene
    window = walk.window
    run = sheet_page(window)
    open_at(window, run, "C5")
    point = cell_scene(run, "C5")
    walk.capture(lambda: right_click(window.view, point.x(), point.y()),
                 "Right-click a spreadsheet cell")
    tables = window.view.tables
    tables._change("Filter", lambda wb, s: __import__(
        "calcforge.sheet.data", fromlist=["set_filter"]).set_filter(wb, s, (0, 0, 5, 3)))
    pump()
    from calcforge.ui import datatools
    walk.open_and_read(datatools.filter_menu(tables, 2, None), "A filtered column")
    tabs = window.sheet_tabs
    if tabs.bar.count():
        walk.capture(lambda: tabs._menu(tabs.bar.tabRect(0).center()), "Right-click a sheet tab")
    else:
        walk.problems.append("no sheet tab")
    _bars_and_panels(walk, " (spreadsheet)")


def calc_scenarios(walk):
    from tests.test_calc_panels import an_equation
    from tests.test_usability import click, press_key, type_text
    window = walk.window
    window.toggle_calc_mode(True)
    pump()
    _bars_and_panels(walk, " (Calc mode)")
    spot = on_page(window, 0, 400, 700)
    window.view.centerOn(QPointF(*spot))
    pump(1)
    walk.capture(lambda: right_click(window.view, *spot), "Right-click the page in Calc mode")
    _menubar(walk)
    window.toggle_calc_mode(False)
    pump()
    equation = an_equation(window, "a:2")
    pump()
    _item_menu(walk, equation, "Right-click an equation")
    second = an_equation(window, "a+1=", 100, 200)
    window.view.scene().clearSelection()
    for item in (equation, second):
        item.setSelected(True)
    window.insert_block()
    pump()
    from calcforge.items.calc import CalcBlockItem, CalcTextItem
    blocks = [i for i in window.view.scene().items() if isinstance(i, CalcBlockItem)]
    if blocks:
        _item_menu(walk, blocks[0], "Right-click a calculation block")
    else:
        walk.problems.append("no calculation block was made")
    window.toggle_calc_mode(True)
    spot = on_page(window, 0, 100, 400)
    click(window.view, *spot)
    window.insert_calc_text()
    type_text(window.view, "Words")
    press_key(window.view, Qt.Key_Escape)
    press_key(window.view, Qt.Key_Escape)
    pump()
    texts = [i for i in window.view.scene().items() if isinstance(i, CalcTextItem)]
    if texts:
        _item_menu(walk, texts[0], "Right-click calculation text")
    panel = window.variables_panel
    window.show_panel("dock_variables", True)
    pump()
    tree = panel.tree
    found = None
    for r in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(r)
        for node in [top] + [top.child(c) for c in range(top.childCount())]:
            if panel.row_of(node) is not None:
                found = node
                break
        if found is not None:
            break
    if found is not None:
        tree.scrollToItem(found)
        point = tree.visualItemRect(found).center()
        walk.capture(lambda: panel._menu(point), "Variables panel row")
    else:
        walk.problems.append("the Variables panel had no row")


SCENARIOS = (markup_scenarios, table_scenarios, sheet_scenarios, calc_scenarios)


@pytest.fixture
def walked(qapp):
    """Every scenario, each in a window of its own."""
    from calcforge.ui.mainwindow import MainWindow
    results = []
    for scenario in SCENARIOS:
        window = MainWindow()
        window.confirm_discard = lambda: True
        window.interactive_prompts = False
        window.resize(1280, 860)
        shown(window)
        walk = Walk(window)
        scenario(walk)
        results.append((scenario.__name__, walk))
    yield results
    for _name, walk in results:
        window = walk.window
        for state in getattr(window, "_open_documents", []):
            document = state.get("document")
            if document is not None:
                document.modified = False
        window.document.modified = False
        window.undo_stack.clear()
        window.view.setScene(None)
        window.close()
        window.deleteLater()
    pump(3)


def test_every_command_in_the_window_can_be_given_a_key(walked):
    problems, missing, count = [], [], 0
    for name, walk in walked:
        problems += [f"{name}: {p}" for p in walk.problems]
        missing += walk.unbindable()
        count += len(walk.entries)
    assert count > 600, f"the walk found only {count} entries"
    assert not problems, "the walk could not reach:\n  " + "\n  ".join(problems)
    assert not missing, (f"{len(missing)} commands cannot be given a key:\n  "
                         + "\n  ".join(missing))


def test_every_listed_command_has_a_category_and_a_place(window):
    from calcforge.ui.bindable_list import COMMANDS
    shown(window)
    bindings = window.shortcuts.bindings()
    assert not [b.action_id for b in bindings if b.category in ("", "Other")]
    for command_id, (label, category, scope) in COMMANDS.items():
        assert label and category and scope, command_id
        assert window.commands.places(command_id), command_id
    ids = [b.action_id for b in bindings]
    assert len(ids) == len(set(ids)), "a command is listed twice"


# ---------------------------------------------------------------------------
# a key given through the dialog, pressed where the command acts
# ---------------------------------------------------------------------------
def open_dialog(window):
    from calcforge.ui import dialogs
    dialog = dialogs.ShortcutManagerDialog(window.shortcuts, window)
    dialog.show()
    pump()
    return dialog


def give_key(dialog, command_id, key, mods=Qt.NoModifier):
    """Click the command's key box and press *key* into it, as a person does."""
    dialog.filter.setText("")
    row = dialog.rows[command_id]
    dialog.table.scrollToItem(dialog.table.item(row, 0))
    editor = dialog.editors[command_id]
    pump(1)
    QTest.mouseClick(editor, Qt.LeftButton)
    pump(1)
    assert QApplication.focusWidget() is editor
    assert dialog.table.currentRow() == row
    QTest.keyClick(editor, key, mods)
    pump(1)
    return editor


def press(window, key, mods=Qt.NoModifier, target=None):
    window.activateWindow()
    widget = target or window.view
    widget.setFocus()
    pump(1)
    QTest.keyClick(QApplication.focusWidget() or widget, key, mods)
    pump(2)


def rect(window, x=100, y=120, w=120, h=70):
    from tests.test_usability import markups
    before = {id(i) for i in markups(window)}
    _draw(window, "rect", x, y, x + w, y + h)
    (made,) = [i for i in markups(window) if id(i) not in before]
    return made


def select(window, *items):
    window.view.scene().clearSelection()
    for item in items:
        item.setSelected(True)
    pump(1)


def test_a_key_given_in_the_dialog_runs_a_command_of_each_group(window, tmp_path):
    """One command from each group, from every kind of place: the menu
    bar, a menu filled as it opens, a right-click menu, a cell's menu, a
    toolbar button, a panel's button, a document tab's menu."""
    from calcforge.ui.mainwindow import recent_files, remember_recent_file
    from tests.test_usability import markups
    shown(window)
    dialog = open_dialog(window)
    samples = {
        # group: (command, key)
        "File": ("menu.file.open_recent.clear_recent_files", Qt.Key_F13),
        "Edit": ("command.hide", Qt.Key_F14),
        "View": ("menu.view.dimmer.50_pct", Qt.Key_F15),
        "Pages": ("page.paper_size.a3", Qt.Key_F16),
        "Pages (insert)": ("insert.add_page.before", Qt.Key_F17),
        "Markup": ("canvas.convert_to_polygon", Qt.Key_F18),
        "Measure": ("tool.measure_area", Qt.Key_F19),
        "Calculation": ("command.auto_calc", Qt.Key_F20),
        "Panels": ("markuprow.width.2_pt", Qt.Key_F21),
        "Window": ("doctab.duplicate_tab", Qt.Key_F22),
        "Help": ("command.record_slowdowns", Qt.Key_F23),
        "Spreadsheet": ("cell.merge.merge_across", Qt.Key_F24),
    }
    for _group, (command_id, key) in samples.items():
        editor = give_key(dialog, command_id, key)
        name = QKeySequence(key).toString(QKeySequence.PortableText)
        assert editor.text() == name
        # it acts at once: no OK to press, and it is remembered
        assert window.shortcuts.sequence(command_id) == name
    assert dialog.clashes() == []
    dialog.close()
    pump()

    # File: a menu-bar entry the menu fills in as it opens
    remember_recent_file(str(tmp_path / "a.pdf"))
    press(window, Qt.Key_F13)
    assert recent_files() == []
    # Edit: the window's own command
    first = rect(window)
    select(window, first)
    press(window, Qt.Key_F14)
    assert first.hidden
    # View: one level of the Dimmer
    press(window, Qt.Key_F15)
    level = next(a for a in window.dimmer_levels.actions() if a.text() == "50%")
    assert level.isChecked()
    # Pages: a page's own menu, for the page in view
    press(window, Qt.Key_F16)
    assert window.document.pages[window.current_index].setup.size_name == "A3"
    # Pages: Insert ▸ Blank Page ▸ Before
    count = len(window.document.pages)
    press(window, Qt.Key_F17)
    assert len(window.document.pages) == count + 1
    # Markup: a markup's right-click entry, for the selection
    before = {id(i) for i in markups(window)}
    _draw(window, "ellipse", 300, 300, 400, 360)
    (ellipse,) = [i for i in markups(window) if id(i) not in before]
    select(window, ellipse)
    press(window, Qt.Key_F18)
    assert ellipse not in markups(window), "the ellipse is a polygon now"
    # Measure: a tool
    press(window, Qt.Key_F19)
    assert window.view.current_tool().key == "measure_area"
    window.select_tool("select")
    # Calculation: a toggle on the Calculation menu
    was = window.act_auto_calc.isChecked()
    press(window, Qt.Key_F20)
    assert window.act_auto_calc.isChecked() != was
    # Panels: the Markups List's right-click menu, for the markups picked there
    second = rect(window, 300, 450)
    window.act_markups_list.setChecked(True)
    pump()
    select(window, second)
    pump(2)
    press(window, Qt.Key_F21)
    assert second.style.width == 2.0
    # Window: a document tab's menu
    tabs = window.document_tabs.count()
    press(window, Qt.Key_F22)
    assert window.document_tabs.count() == tabs + 1
    # Help
    was = window.act_record_slowdowns.isChecked()
    press(window, Qt.Key_F23)
    assert window.act_record_slowdowns.isChecked() != was
    if window.act_record_slowdowns.isChecked():
        window.act_record_slowdowns.setChecked(False)
    # Spreadsheet: a cell's right-click entry, in an open table
    from tests.test_tables import make_table
    table = make_table(window)
    window.view.tables.open(table)
    window.view.tables.select((0, 0), (1, 1), (0, 0))
    pump()
    press(window, Qt.Key_F24)
    assert any(list(m)[:4] == [0, 0, 0, 1] for m in table.sheet.merges), table.sheet.merges


def test_a_key_already_in_use_can_be_reassigned_or_left(window):
    shown(window)
    dialog = open_dialog(window)
    give_key(dialog, "page.move_down", Qt.Key_S, Qt.ControlModifier)
    assert dialog.conflict.isVisible()
    assert "Save" in dialog.conflict_text.text()
    # not applied while it is in question
    assert window.shortcuts.sequence("page.move_down") == ""
    QTest.mouseClick(dialog.keep_button, Qt.LeftButton)
    pump(1)
    assert not dialog.conflict.isVisible()
    assert dialog.editors["page.move_down"].text() == ""
    assert window.shortcuts.sequence("command.save") == "Ctrl+S"

    give_key(dialog, "page.move_down", Qt.Key_S, Qt.ControlModifier)
    QTest.mouseClick(dialog.reassign_button, Qt.LeftButton)
    pump(1)
    assert window.shortcuts.sequence("page.move_down") == "Ctrl+S"
    assert window.shortcuts.sequence("command.save") == ""
    assert dialog.editors["command.save"].text() == ""
    assert not window.act_save.shortcuts()
    assert dialog.clashes() == []

    # a key that means something else only where this one cannot act is no
    # clash: Shift+F2 is a cell's note, and only in an open table
    give_key(dialog, "page.move_up", Qt.Key_F2, Qt.ShiftModifier)
    assert not dialog.conflict.isVisible()
    assert window.shortcuts.sequence("page.move_up") == "Shift+F2"
    dialog.close()


def remembered(command_id):
    """What the settings file holds for *command_id*: the key a later
    session starts with ("" when it is cleared; None when it is the default)."""
    from calcforge.settings import app_settings
    value = app_settings().value(f"shortcuts/{command_id}", None)
    return None if value is None else str(value)


def test_clear_reset_one_and_reset_all_act_at_once_and_are_remembered(window):
    shown(window)
    dialog = open_dialog(window)
    give_key(dialog, "command.save_all", Qt.Key_F9, Qt.ControlModifier | Qt.AltModifier)
    assert window.act_save_all.shortcut().toString() == "Ctrl+Alt+F9"
    assert remembered("command.save_all") == "Ctrl+Alt+F9"
    # Clear, with the mouse
    QTest.mouseClick(dialog.clear_button, Qt.LeftButton)
    pump(1)
    assert dialog.editors["command.save_all"].text() == ""
    assert window.act_save_all.shortcut().isEmpty()
    assert remembered("command.save_all") is None, "back to its default, none"
    # Reset one puts the command's own key back
    give_key(dialog, "command.save", Qt.Key_F9, Qt.ControlModifier | Qt.AltModifier)
    assert window.act_save.shortcut().toString() == "Ctrl+Alt+F9"
    QTest.mouseClick(dialog.reset_button, Qt.LeftButton)
    pump(1)
    assert window.act_save.shortcut().toString() == "Ctrl+S"
    # Reset all
    give_key(dialog, "page.move_up", Qt.Key_Insert, Qt.AltModifier)
    give_key(dialog, "command.rulers", Qt.Key_R, Qt.ControlModifier | Qt.AltModifier)
    assert window.act_rulers.shortcut().toString() == "Ctrl+Alt+R" or \
        dialog.conflict.isVisible()
    QTest.mouseClick(dialog.reset_all_button, Qt.LeftButton)
    pump(1)
    assert window.shortcuts.sequence("page.move_up") == ""
    assert window.shortcuts.sequence("command.rulers") == ""
    assert remembered("page.move_up") is None
    assert remembered("command.rulers") is None
    dialog.close()


def test_the_usual_keys_can_all_be_pressed_in(window):
    shown(window)
    dialog = open_dialog(window)
    command = "page.move_up"
    chords = (
        (Qt.Key_K, Qt.ControlModifier | Qt.AltModifier | Qt.ShiftModifier),
        (Qt.Key_K, Qt.AltModifier | Qt.ShiftModifier), (Qt.Key_K, Qt.MetaModifier),
        (Qt.Key_F1, Qt.ShiftModifier), (Qt.Key_F24, Qt.NoModifier),
        (Qt.Key_Insert, Qt.NoModifier), (Qt.Key_Delete, Qt.AltModifier),
        (Qt.Key_Home, Qt.AltModifier), (Qt.Key_End, Qt.AltModifier),
        (Qt.Key_PageUp, Qt.AltModifier), (Qt.Key_PageDown, Qt.AltModifier | Qt.ShiftModifier),
        (Qt.Key_Left, Qt.ControlModifier | Qt.AltModifier))
    cases = [(key, mods, QKeySequence(QKeyCombination(mods, key)).toString(
        QKeySequence.PortableText)) for key, mods in chords]
    cases += [(Qt.Key_7, Qt.NoModifier, "7"), (Qt.Key_J, Qt.NoModifier, "j")]
    for key, mods, written in cases:
        editor = give_key(dialog, command, key, mods)
        assert editor.text() == written, (key, mods)
        if dialog.conflict.isVisible():
            QTest.mouseClick(dialog.keep_button, Qt.LeftButton)
            pump(1)
        else:
            assert window.shortcuts.sequence(command) == written
    dialog.close()


def test_the_list_is_searched_by_name_by_key_and_by_group(window):
    shown(window)
    dialog = open_dialog(window)

    def shown_ids():
        return [i for i, r in dialog.rows.items() if not dialog.table.isRowHidden(r)]
    QTest.keyClicks(dialog.filter, "paper size a3")
    assert shown_ids() == ["page.paper_size.a3"]
    dialog.filter.clear()
    QTest.mouseClick(dialog.key_search, Qt.LeftButton)
    QTest.keyClick(dialog.key_search, Qt.Key_S, Qt.ControlModifier)
    pump(1)
    assert "command.save" in shown_ids() and "page.move_up" not in shown_ids()
    QTest.keyClick(dialog.key_search, Qt.Key_Backspace)
    dialog.group_filter.setCurrentIndex(dialog.group_filter.findData("Spreadsheet"))
    assert shown_ids() and all(dialog._by_id[i].category == "Spreadsheet"
                                for i in shown_ids())
    dialog.group_filter.setCurrentIndex(0)
    # each says where it is offered
    where = dialog.table.item(dialog.rows["command.rotate_pages_cw"], 4).text()
    assert "Document ▸ Rotate Pages" in where
    where = dialog.table.item(dialog.rows["page.paper_size.a3"], 4).text()
    assert "thumbnail" in where
    dialog.close()


def test_a_rebound_command_is_silent_while_typing(window):
    from tests.test_usability import swallowed
    shown(window)
    dialog = open_dialog(window)
    give_key(dialog, "menu.view.dimmer.50_pct", Qt.Key_K, Qt.AltModifier)
    give_key(dialog, "page.paper_size.a3", Qt.Key_K)            # a bare letter
    assert not dialog.conflict.isVisible()
    assert window.shortcuts.sequence("page.paper_size.a3") == "k"
    dialog.close()
    pump()
    def size():
        return window.document.pages[window.current_index].setup.size_name
    before = size()
    assert before != "A3"
    # in a text box on the page
    window.select_tool("text")
    p, q = on_page(window, 0, 100, 100), on_page(window, 0, 340, 150)
    drag(window.view, p[0], p[1], q[0], q[1])
    assert window.view.is_editing()
    assert swallowed(window, Qt.Key_K, Qt.AltModifier)
    QTest.keyClick(QApplication.focusWidget() or window.view, Qt.Key_K)
    pump(1)
    assert size() == before, "k was typed, not run"
    window.view.end_item_edit()
    window.select_tool("select")
    # in the menu bar's search box
    box = window._search_box if hasattr(window, "_search_box") else None
    boxes = [box] if box is not None else [
        f for f in window.findChildren(QLineEdit) if f.isVisible() and not f.isReadOnly()]
    for field in boxes[:1]:
        field.setFocus()
        pump(1)
        QTest.keyClick(field, Qt.Key_K)
        pump(1)
        assert size() == before, "k was typed into the box"
    # on the page in Calc mode a letter starts an equation
    window.toggle_calc_mode(True)
    pump()
    press(window, Qt.Key_K)
    assert size() == before
    press(window, Qt.Key_Escape)
    press(window, Qt.Key_Escape)
    window.toggle_calc_mode(False)
    pump()
    # and on the page in Markup mode the letter runs the command
    press(window, Qt.Key_K)
    assert size() == "A3"
