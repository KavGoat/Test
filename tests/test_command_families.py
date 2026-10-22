"""One name, one shape, one place for every command family (bug hunt E1–E19,
novice 11/13/19/21/24, Revu audit L1–L6 and B1).

Each family is checked in every place it is offered — the menu bar, the
page (Thumbnails) menu, the canvas and markup right-click menus, a cell's
menu, the toolbars and the panel buttons — for the same names and the same
variants. The menus that pop up are opened the way a person opens them: the
menu bar by a click on its title, a right-click through the real event
path, read while they are up (QApplication.activePopupWidget)."""
from __future__ import annotations

import re

import pytest
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QContextMenuEvent, QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu

from calcforge.items.shapes import RectItem
from calcforge.sheet.pagination import options
from calcforge.ui.menutidy import title_case, walk
from calcforge.ui.tools import TOOL_MAP, TOOLS
from tests.test_sheet_pages import runs, sheet_page, w  # noqa: F401
from tests.test_tables import cell_scene


def pump(times: int = 6) -> None:
    """Let a popup open, a hover land or a click be delivered: menus take
    a few turns of the event loop."""
    for _ in range(times):
        QApplication.instance().processEvents()

INSERTS = ["Blank Page", "Spreadsheet Page", "Pages", "Image Page", "Excel Workbook"]


# -- helpers ---------------------------------------------------------------------------------
def top(window, title: str) -> QMenu:
    return next(a.menu() for a in window.menuBar().actions()
                if a.text().replace("&", "") == title)


def sub(menu: QMenu, *path) -> QMenu:
    for title in path:
        menu = next(a.menu() for a in menu.actions() if a.menu() is not None
                    and a.text() == title)
    return menu


def entry(menu: QMenu, text: str):
    found = [a for a in menu.actions() if a.text() == text]
    assert found, f"{text!r} not in {labels(menu)}"
    return found[0]


def labels(menu: QMenu) -> list:
    return [a.text() for a in menu.actions() if not a.isSeparator() and a.isVisible()]


def groups(menu: QMenu) -> list:
    """The menu's entries, by the separators between them."""
    out, now = [], []
    for action in menu.actions():
        if not action.isVisible():
            continue
        if action.isSeparator():
            if now:
                out.append(now)
            now = []
        else:
            now.append(action.text())
    if now:
        out.append(now)
    return out


def group_of(menu: QMenu, text: str) -> list:
    return next(g for g in groups(menu) if text in g)


def every_text(menu: QMenu) -> list:
    return [a.text() for _path, a in walk(menu) if not a.isSeparator()]


def all_menu_bar_text(window) -> list:
    found = []
    for action in window.menuBar().actions():
        if action.menu() is not None:
            action.menu().aboutToShow.emit()
            found += every_text(action.menu())
    return found


def a_box(window, page: int = 0) -> RectItem:
    frame = window.document.pages[page].frame
    box = RectItem()
    box.set_local_rect(QRectF(0, 0, 120, 80))
    window.view.begin_snapshot([frame])
    frame.add_markup(box, QPointF(100, 100))
    window.view.commit_snapshot("Box")
    window.view.scene().clearSelection()
    box.setSelected(True)
    return box


def right_click(window, widget, local: QPoint, then=None) -> list:
    """A real right-click on *widget*; the menu that pops up is read while it
    is up (and *then(menu)* run on it), then closed. (path, text, enabled)."""
    seen: list = []

    def grab():
        menu = QApplication.activePopupWidget()
        if not isinstance(menu, QMenu):
            QTimer.singleShot(20, grab)
            return
        seen.extend((path, a.text(), a.isEnabled()) for path, a in walk(menu)
                    if not a.isSeparator())
        if then is not None:
            then(menu)
        for _ in range(4):
            popup = QApplication.activePopupWidget()
            if popup is None:
                break
            popup.close()
    QTimer.singleShot(0, grab)
    QApplication.sendEvent(widget, QContextMenuEvent(
        QContextMenuEvent.Mouse, local, widget.mapToGlobal(local)))
    pump()
    return seen


def point_at(menu: QMenu, action) -> None:
    """Move the pointer onto *action*, as a hand does: from somewhere else in
    the menu first."""
    spot = menu.actionGeometry(action).center()
    for x, y in ((4, 4), (spot.x() - 8, spot.y()), (spot.x(), spot.y())):
        QTest.mouseMove(menu, QPoint(x, y))
        pump(2)


def click_menu_bar(window, path: list) -> None:
    """Click the menu bar's title, then each entry, with the mouse."""
    bar = window.menuBar()
    title = next(a for a in bar.actions() if a.text().replace("&", "") == path[0])
    # the pointer goes to the title first, as a hand's does: a menu ignores a
    # click where the pointer was when it opened
    QTest.mouseMove(bar, bar.actionGeometry(title).center())
    pump(2)
    QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier, bar.actionGeometry(title).center())
    pump()
    menu = QApplication.activePopupWidget()
    assert isinstance(menu, QMenu), f"{path[0]} did not open"
    for text in path[1:]:
        action = entry(menu, text)
        assert action.isEnabled(), f"{text} is greyed"
        point_at(menu, action)
        QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier, menu.actionGeometry(action).center())
        pump()
        if action.menu() is not None:
            menu = action.menu()
            assert menu.isVisible(), f"{text} did not open"
    for _ in range(4):
        popup = QApplication.activePopupWidget()
        if popup is None:
            break
        popup.close()
    pump()


@pytest.fixture
def shown(window, qapp):
    window.show()
    window.activateWindow()
    window.view.setFocus()
    qapp.processEvents()
    return window


# -- E1–E4: the insert family ------------------------------------------------------------------
def test_every_insert_is_offered_before_or_after_everywhere(window):
    window.add_page()
    # Document ▸ Insert: the five, each Before / After, dialogs with "…"
    insert = sub(top(window, "Document"), "Insert")
    # first the one-click Add Page, no dialog, no Before / After (the user,
    # 2026-10-22: "There's no simple add page option")
    assert labels(insert) == ["Add Page"] + INSERTS
    assert entry(insert, "Add Page").menu() is None
    shapes = {name: labels(entry(insert, name).menu()) for name in INSERTS}
    assert shapes == {"Blank Page": ["Before…", "After…"], "Spreadsheet Page": ["Before", "After"],
                      "Pages": ["Before…", "After…"], "Image Page": ["Before…", "After…"],
                      "Excel Workbook": ["Before…", "After…"]}
    # the page menu: the same five, with Insert in front, the same shapes
    page = window.page_menu(1)
    on_page = [t for t in labels(page) if t.startswith("Insert ")]
    assert on_page == [f"Insert {name}" for name in INSERTS]
    assert {name: labels(entry(page, f"Insert {name}").menu()) for name in INSERTS} == shapes
    # all five together, in one group
    assert set(on_page) <= set(group_of(page, "Insert Blank Page"))
    # File ▸ Import: the three that come from a file, the same commands
    imports = sub(top(window, "File"), "Import")
    assert labels(imports) == ["Pages", "Image Page", "Excel Workbook", "Tool Set…"]
    for name in ("Pages", "Image Page", "Excel Workbook"):
        assert entry(imports, name) is entry(insert, name)
    # the Thumbnails panel's buttons: the menus' names, Before / After on the arrow
    buttons = window.pages_panel.page_buttons
    assert buttons["add_page"].toolTip().startswith("Insert Blank Page")
    assert buttons["add_sheet_page"].toolTip().startswith("Insert Spreadsheet Page")
    assert labels(buttons["add_page"].menu()) == ["Before…", "After…"]
    assert labels(buttons["add_sheet_page"].menu()) == ["Before", "After"]
    assert buttons["duplicate_page"].toolTip().startswith("Duplicate Page")
    assert buttons["delete_page"].toolTip().startswith("Delete Pages…")
    # the old names are gone everywhere
    everywhere = all_menu_bar_text(window) + every_text(page)
    for gone in ("Pages from Document…", "Add Sheet Page", "Add a page"):
        assert gone not in everywhere


def test_add_sheet_page_is_insert_spreadsheet_page_on_a_sheet(w):
    run = sheet_page(w)
    index = next(i for i, p in enumerate(w.document.pages) if p.sheet is not None)
    menu = w.page_menu(index)
    assert "Add Sheet Page" not in labels(menu)
    after = entry(entry(menu, "Insert Spreadsheet Page").menu(), "After")
    assert after.toolTip().startswith("Another page of this spreadsheet")
    pages = len(w.document.pages)
    after.trigger()
    pump()
    assert len(w.document.pages) == pages + 1
    assert w.document.pages[index + 1].sheet == run.uid, "one more page of the same sheet"


def test_menu_bar_spreadsheet_page_before_by_mouse(shown):
    window = shown
    window.add_page()
    window.go_to_page(1)
    click_menu_bar(window, ["Document", "Insert", "Spreadsheet Page", "Before"])
    assert len(window.document.pages) == 3
    assert window.document.pages[1].sheet is not None, "before page 2, where it was asked"
    click_menu_bar(window, ["File", "Import", "Pages"])           # a submenu, not a dialog


def test_the_insert_keys_put_it_after_the_page_in_view(shown):
    window = shown
    QTest.keyClick(window.view, Qt.Key_N, Qt.ControlModifier | Qt.ShiftModifier)
    pump()
    assert len(window.document.pages) == 2, "Ctrl+Shift+N is Revu's Insert Blank Page"
    # the key is shown beside the choice it makes
    choice = window.act_add_page.menu()
    choice.aboutToShow.emit()
    assert entry(choice, "After…").shortcut().toString() == "Ctrl+Shift+N"


# -- E5: Calc mode's inserts --------------------------------------------------------------
def test_calc_inserts_are_in_insert_here_with_the_calculation_menus_names(window):
    window.toggle_calc_mode(True)
    menu = window.build_context_menu(None, window.document.pages[0].frame.mapToScene(
        QPointF(80, 200)))
    here = entry(menu, "Insert Here").menu()
    assert labels(here)[:4] == ["Equation", window.act_insert_calc_text.text(),
                                window.act_insert_block.text(), window.act_insert_plot.text()]
    assert window.act_insert_block.text() == "Calculation Block"
    calc = labels(top(window, "Calculation"))
    for name in ("Calc Text", "Calculation Block", "Plot"):
        assert name in calc
    assert "Calculation Block" in [a.text() for a in window.calculation_bar.actions()]
    window.toggle_calc_mode(False)


# -- E6: Import / Export don't repeat their menu's word -----------------------------------
def test_import_and_export_entries_do_not_repeat_the_menus_word(window):
    for title in ("Import", "Export"):
        menu = sub(top(window, "File"), title)
        assert not [t for t in labels(menu) if t.startswith(title)]
    assert labels(sub(top(window, "File"), "Export")) == ["PDF…", "Images…", "Markups Summary…"]
    # outside File ▸ Import, Import Tool Set says its whole name
    chest = sub(top(window, "Tools"), "Tool Chest")
    assert "Import Tool Set…" in labels(chest)
    # and the shortcut list names them in full
    names = {b.action_id: b.label for b in window.shortcuts.bindings()}
    assert names["command.export_pdf"] == "Export PDF"
    assert names["command.insert_pdf"] == "Insert Pages"


# -- E7, E8: rotate, extract, split, crop -------------------------------------------------
def test_rotate_pages_is_on_the_document_menu_as_on_the_page_menu(window):
    document = top(window, "Document")
    rotate = entry(document, "Rotate Pages").menu()
    page_rotate = entry(window.page_menu(0), "Rotate Pages").menu()
    assert labels(rotate) == labels(page_rotate) == ["Clockwise", "Anticlockwise"]
    view = sub(top(window, "View"), "Rotate View")
    assert labels(view) == ["Rotate Clockwise", "Rotate Anticlockwise", "Reset Rotation"]
    before = window.current_page().setup.orientation
    window.act_rotate_pages_cw.trigger()
    assert window.current_page().setup.orientation != before


def test_the_page_menu_has_the_document_menus_page_commands(window):
    document = labels(top(window, "Document"))
    page = labels(window.page_menu(0))
    for name in ("Extract Pages…", "Split Document…", "Delete Pages…", "Crop Pages…",
                 "Rotate Pages", "Flatten…", "Unflatten", "Colour Processing…"):
        assert name in document and name in page, name
    # Revu's order and ellipses on the Document menu (audit B1)
    assert document[:8] == ["Document Properties…", "Page Setup…", "Rotate Pages", "Insert",
                            "Extract Pages…", "Split Document…", "Delete Pages…",
                            "Crop Pages…"]


# -- E9, E10: moving and printing pages ----------------------------------------------------
def test_move_is_with_the_clipboard_and_print_with_its_tick(window):
    window.add_page()
    menu = window.page_menu(0)
    assert {"Cut Pages", "Copy Pages", "Paste Pages", "Move Up", "Move Down"} <= \
        set(group_of(menu, "Cut Pages"))
    printing = group_of(menu, "Print Pages…")
    assert "Include in Print && Export" in printing
    assert "Print" not in labels(menu)


# -- E11–E13: scale, page setup, sheet layout ---------------------------------------------
def test_set_scale_has_one_name(window):
    assert window.act_scale.text() == "Set Scale…"
    assert window.act_scale.shortcut().toString() == "Ctrl+Shift+K"
    measure = sub(top(window, "Tools"), "Measure")
    assert window.act_scale in measure.actions() and window.act_viewports in measure.actions()
    assert "Set Scale…" in labels(window.page_menu(0))
    canvas = window.build_context_menu(None, window.document.pages[0].frame.mapToScene(
        QPointF(80, 200)))
    assert "Set Scale…" in labels(canvas)
    everywhere = all_menu_bar_text(window) + every_text(window.page_menu(0))
    assert not [t for t in everywhere if "Page Scale" in t]


def test_the_page_panel_is_not_called_page_setup(window):
    panels = labels(sub(top(window, "Window"), "Panels"))
    assert "Page" in panels and "Page Setup" not in panels
    assert window.dock_page.windowTitle() == "Page"
    assert window.act_page_setup.text() == "Page Setup…"


def test_sheet_layout_has_one_name_and_page_breaks_one_shape(w):
    run = sheet_page(w)
    index = next(i for i, p in enumerate(w.document.pages) if p.sheet is not None)
    assert "Sheet Layout…" in labels(w.page_menu(index))
    bar = sub(top(w, "Calculation"), "Page Layout")
    w.view.tables.open(run, (9, 0))
    pump()
    cell = w.view.tables.cell_menu()
    in_cell = sub(cell, "Page Layout")
    for menu in (bar, in_cell):
        assert labels(menu) == ["Breaks", "Print Area", "Sheet Layout…"]
        assert labels(sub(menu, "Breaks")) == ["Insert Page Break", "Remove Page Break",
                                               "Reset All Page Breaks"]
        assert labels(sub(menu, "Print Area")) == ["Set Print Area", "Clear Print Area"]
    # Excel's Insert ▸ and Delete ▸ entries are still there too
    assert "Insert Page Break" in labels(sub(cell, "Insert"))
    # and the menu bar's Breaks act on the open sheet's active cell
    bar.aboutToShow.emit()
    assert w.act_insert_page_break.isEnabled()
    w.act_insert_page_break.trigger()
    pump()
    (run,) = runs(w)
    assert options(run.sheet)["breaks"] == [9]


def test_a_cells_page_layout_breaks_by_a_real_right_click(w):
    run = sheet_page(w)
    target = cell_scene(run, "A10")
    w.view.centerOn(target)
    pump()

    def press(menu, text):
        action = entry(menu, text)
        spot = menu.actionGeometry(action).center()
        point_at(menu, action)
        QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier, spot)
        pump()
        return action.menu()

    def insert(menu):
        press(press(press(menu, "Page Layout"), "Breaks"), "Insert Page Break")
    seen = right_click(w, w.view.viewport(), w.view.mapFromScene(target), insert)
    assert (("Page Layout", "Breaks"), "Insert Page Break", True) in seen
    pump()
    (run,) = runs(w)
    assert options(run.sheet)["breaks"] == [9]


# -- E14: Flatten and Unflatten together --------------------------------------------------
def test_unflatten_is_wherever_flatten_is(window):
    box = a_box(window)
    markup = window.build_context_menu(box, box.mapToScene(QPointF(0, 0)))
    places = {"Edit": top(window, "Edit"), "Document": top(window, "Document"),
              "Batch": top(window, "Batch"), "page menu": window.page_menu(0),
              "markup menu": markup}
    for where, menu in places.items():
        texts = labels(menu)
        flatten = next(t for t in texts if t.startswith("Flatten"))
        assert texts[texts.index(flatten) + 1] == "Unflatten", where
    assert entry(top(window, "Edit"), "Flatten") is not None
    assert entry(top(window, "Document"), "Flatten…") is window.act_flatten_document


# -- E15: UK spelling everywhere -----------------------------------------------------------
US = re.compile(r"\b(Color|Colors|Colorize|Center|Centered|Gray|Grayscale|Counterclockwise|"
                r"Customize|Customized)\b")


def test_uk_spelling_in_every_menu(w):
    run = sheet_page(w)
    box = a_box(w)
    texts = all_menu_bar_text(w)
    texts += every_text(w.page_menu(0))
    texts += every_text(w.build_context_menu(box, box.mapToScene(QPointF(0, 0))))
    texts += every_text(w.build_context_menu(None, QPointF(80, 200)))
    w.view.tables.open(run, (0, 0))
    texts += every_text(w.view.tables.cell_menu())
    assert not [t for t in texts if US.search(t)]
    assert "Colour Processing…" in texts and w.act_color_processing.text() == "Colour Processing…"


def test_the_colour_dialogs_say_colour(window):
    from calcforge.io.colorproc import NAMES
    from calcforge.ui.changecolors import ChangeColorsDialog
    assert set(NAMES.values()) >= {"Modify Colours", "Colourise", "Greyscale"}
    dialog = ChangeColorsDialog(window, [])
    try:
        assert dialog.windowTitle() == "Change Multiple Colours"
    finally:
        dialog.deleteLater()


# -- E16–E18: the clipboard, hide/lock, order/alignment ---------------------------------------
CLIPBOARD = ["Cut", "Copy", "Paste", "Paste in Place", "Paste Here…", "Duplicate"]
KEEPING = ["Flatten", "Unflatten", "Lock", "Hide", "Show Hidden"]


def test_edit_and_the_markup_menu_group_the_same_families_alike(window):
    box = a_box(window)
    markup = window.build_context_menu(box, box.mapToScene(QPointF(0, 0)))
    edit = top(window, "Edit")
    for menu in (edit, markup):
        clip = group_of(menu, "Cut")
        assert clip[:6] == CLIPBOARD
        assert "Delete" in clip and "Multiply…" in clip
        keep = group_of(menu, "Lock")
        assert [t for t in keep if t in KEEPING] == KEEPING
        assert keep.index("Order") < keep.index("Alignment") < keep.index("Flatten")
        assert labels(entry(menu, "Order").menu()) == ["Bring to Front", "Bring Forward",
                                                       "Send Backward", "Send to Back"]
        assert labels(entry(menu, "Alignment").menu()) == [
            "Align Left", "Align Centre", "Align Right", "Align Top", "Align Middle",
            "Align Bottom", "Align Width", "Align Height", "Align Size",
            "Distribute Horizontally", "Distribute Vertically", "Centre in Document",
            "Flip Horizontal", "Flip Vertical"]
    assert "Align Centre" in labels(sub(edit, "Text"))
    # hidden markups come back from the bare page's menu
    canvas = window.build_context_menu(None, QPointF(80, 200))
    assert "Show Hidden" in labels(canvas)


def test_the_markup_menu_by_a_real_right_click(shown):
    window = shown
    box = a_box(window)
    window.view.centerOn(box)
    pump()
    local = window.view.mapFromScene(box.mapToScene(QPointF(0, 40)))
    seen = right_click(window, window.view.viewport(), local)
    top_level = [text for path, text, _e in seen if not path]
    assert top_level[:6] == CLIPBOARD
    assert "Unflatten" in top_level and "Show Hidden" in top_level


# -- L1, L4: Edit's Pan, Select, Snapshot and PDF Content; Title Case tools ------------------
def test_edit_has_revus_pan_select_snapshot_and_pdf_content(window):
    edit = labels(top(window, "Edit"))
    for name in ("Pan", "Select", "Select All", "Snapshot", "Format Painter", "PDF Content",
                 "Search", "Replace", "Check Spelling"):
        assert name in edit, name
    assert labels(sub(top(window, "Edit"), "PDF Content")) == [
        "Mark for Redaction", "Whiteout", "Apply Redactions…"]
    tools = labels(top(window, "Tools"))
    assert "Navigation" not in tools and "Hyperlink" in tools and "Reuse" in tools
    assert window.act_sticky.text() == "Reuse"


def test_every_tool_name_is_title_case(window):
    for tool in TOOLS:
        assert title_case(tool.label) == tool.label, tool.label
    measure = labels(sub(top(window, "Tools"), "Measure"))
    for name in ("Centre Radius", "Polygon Cut-Out", "Ellipse Cut-Out"):
        assert name in measure
    assert "Text Box" in labels(sub(top(window, "Tools"), "Markup"))


# -- L3, L5: Window ▸ Panels, View's modes ---------------------------------------------------
def test_window_panels_are_alphabetical_with_revus_keys(window):
    panels = sub(top(window, "Window"), "Panels")
    names = labels(panels)
    assert names == sorted(names, key=str.lower)
    keys = {a.text(): a.shortcut().toString() for a in panels.actions()}
    assert keys["Thumbnails"] == "Alt+T" and keys["Bookmarks"] == "Alt+B"
    assert keys["Tool Chest"] == "Alt+X" and keys["Page"] == "Alt+U"
    assert keys["Search"] == "Alt+1" and keys["Markups List"] == "Alt+L"
    assert entry(top(window, "Window"), "Hide/Show Panels").shortcut().toString() == "Shift+F4"
    view = labels(top(window, "View"))
    assert "Single Page Mode" in view and "Continuous Mode" in view


def test_the_panel_keys_and_shift_f4_by_keyboard(shown):
    window = shown
    for key, name in ((Qt.Key_B, "dock_bookmarks"), (Qt.Key_X, "dock_toolsets"),
                      (Qt.Key_U, "dock_page"), (Qt.Key_1, "dock_search"),
                      (Qt.Key_T, "dock_pages")):
        window.show_panel(name, False)
        window.view.setFocus()
        QTest.keyClick(window.view, key, Qt.AltModifier)
        pump()
        assert not window.docks_by_name[name].isHidden(), name
        assert getattr(window, f"act_panel_{name[5:]}").isChecked()
    open_now = [n for n, d in window.docks_by_name.items() if not d.isHidden()]
    QTest.keyClick(window.view, Qt.Key_F4, Qt.ShiftModifier)
    pump()
    assert not [n for n, d in window.docks_by_name.items() if not d.isHidden()]
    QTest.keyClick(window.view, Qt.Key_F4, Qt.ShiftModifier)
    pump()
    assert sorted(n for n, d in window.docks_by_name.items() if not d.isHidden()) == \
        sorted(open_now)


def test_the_menus_mnemonics_leave_alt_t_and_alt_b_to_the_panels(shown):
    window = shown
    titles = [a.text() for a in window.menuBar().actions() if a.menu()]
    assert "T&ools" in titles and "B&atch" in titles
    taken = {re.search(r"&(\w)", t).group(1).lower() for t in titles if "&" in t}
    assert not taken & {"t", "b", "x", "u", "l", "1"}
    window.view.setFocus()
    QTest.keyClick(window, Qt.Key_D, Qt.AltModifier)
    pump()
    popup = QApplication.activePopupWidget()
    assert isinstance(popup, QMenu) and popup.title() == "&Document"
    popup.close()
    pump()


# -- L2: Revu's keys, and nothing lost its key ------------------------------------------------
REVU_KEYS = {"doc_props": "Ctrl+D", "fit_page": "Ctrl+9", "fit_width": "Ctrl+0",
             "actual_size": "Ctrl+8", "delete_page": "Ctrl+Shift+D", "add_page": "Ctrl+Shift+N",
             "scale": "Ctrl+Shift+K", "extract_pages": "Ctrl+Shift+X",
             "crop_page": "Alt+Shift+O", "show_panels": "Shift+F4", "replace_text": "Ctrl+H",
             "array": "Ctrl+M"}
MOVED = {"duplicate": "Ctrl+J", "new_window": "Ctrl+Alt+Shift+N"}


def test_revus_keys_and_the_moved_ones(window):
    for key, sequence in {**REVU_KEYS, **MOVED}.items():
        assert getattr(window, f"act_{key}").shortcut().toString() == sequence, key
    assert window.shortcuts.conflicts() == {}


def test_ctrl_m_is_multiply_in_markup_mode_and_matrix_in_calc_mode(window):
    assert [s.toString() for s in window.act_array.shortcuts()] == ["Ctrl+M"]
    assert window.act_insert_matrix.shortcuts() == []
    window.toggle_calc_mode(True)
    assert [s.toString() for s in window.act_insert_matrix.shortcuts()] == ["Ctrl+M"]
    assert window.act_array.shortcuts() == []
    window.toggle_calc_mode(False)
    assert [s.toString() for s in window.act_array.shortcuts()] == ["Ctrl+M"]


def test_the_zoom_keys_by_keyboard(shown):
    window = shown
    window.view.set_zoom(3.0)
    QTest.keyClick(window.view, Qt.Key_8, Qt.ControlModifier)
    pump()
    assert window.view.zoom() == pytest.approx(1.0), "Ctrl+8 Actual Size"
    QTest.keyClick(window.view, Qt.Key_9, Qt.ControlModifier)
    pump()
    fit_page = window.view.zoom()
    window.view.set_zoom(3.0)
    QTest.keyClick(window.view, Qt.Key_0, Qt.ControlModifier)
    pump()
    assert window.view.zoom() != pytest.approx(3.0), "Ctrl+0 Fit Width"
    assert fit_page != pytest.approx(3.0) and fit_page != pytest.approx(1.0)


# -- novice 19: Ctrl+H ------------------------------------------------------------------------
def test_ctrl_h_opens_search_ready_to_replace(shown):
    window = shown
    QTest.keyClick(window.view, Qt.Key_H, Qt.ControlModifier)
    pump()
    assert not window.dock_search.isHidden()
    assert QApplication.focusWidget() is window.search_panel.query, "nothing to look for yet"
    window.search_panel.query.setText("TBC")
    window.view.setFocus()
    QTest.keyClick(window.view, Qt.Key_H, Qt.ControlModifier)
    pump()
    assert QApplication.focusWidget() is window.search_panel.replacement
    assert window.act_replace_text in top(window, "Edit").actions()


# -- novice 21: one Table -----------------------------------------------------------------------
def test_the_two_table_buttons_are_one_command(window):
    tool = window.tool_actions["table"]
    assert tool in window.calculation_bar.actions(), "the Tools bar's own button"
    assert window.act_insert_table not in window.calculation_bar.actions()
    assert window.act_insert_table.text() == tool.text() == TOOL_MAP["table"].label
    assert window.act_insert_table.toolTip() == TOOL_MAP["table"].hint
    window.act_insert_table.trigger()
    assert window.view.tool_key == "table" and tool.isChecked()


# -- novice 12: Scale Not Set ---------------------------------------------------------------------
def test_the_status_bar_says_when_a_page_has_no_scale(window):
    from calcforge.core.document import PageScale
    window.refresh_scale_label()
    assert window.status_scale.text() == "Scale Not Set"
    window.set_page_scale(PageScale.from_ratio(100))
    window.refresh_scale_label()
    assert window.status_scale.text() == "Scale 1:100"


# -- novice 24: the empty workspace ----------------------------------------------------------------
def test_closing_the_last_tab_leaves_an_empty_workspace(shown):
    window = shown
    QTest.keyClick(window.view, Qt.Key_W, Qt.ControlModifier)
    pump()
    assert window.workspace_empty
    assert window.windowTitle() == "CalcForge" and "Untitled" not in window.windowTitle()
    assert not window.bottom_split.isVisible() and window.empty_workspace.isVisible()
    assert not window.act_save.isEnabled() and not window.tool_actions["rect"].isEnabled()
    assert window.act_new.isEnabled() and window.act_open.isEnabled()
    QTest.keyClick(window, Qt.Key_N, Qt.ControlModifier)
    pump()
    assert not window.workspace_empty and window.bottom_split.isVisible()
    assert window.act_save.isEnabled() and window.tool_actions["rect"].isEnabled()
    # and by mouse: File ▸ Close, then the workspace's own New PDF button
    click_menu_bar(window, ["File", "Close"])
    assert window.workspace_empty
    from PySide6.QtWidgets import QPushButton
    button = window.empty_workspace.findChild(QPushButton, "emptyWorkspace_new")
    QTest.mouseClick(button, Qt.LeftButton)
    pump()
    assert not window.workspace_empty
    # New Tab from the empty workspace takes the blank one's place
    click_menu_bar(window, ["File", "Close"])
    assert window.workspace_empty
    window.act_new_tab.trigger()
    pump()
    assert not window.workspace_empty and window.document_tabs.count() == 1


def test_the_key_list_is_still_complete(window):
    bindings = {window.shortcuts.sequence(b.action_id) for b in window.shortcuts.bindings()}
    for name in dir(window):
        if name.startswith("act_"):
            for key in getattr(window, name).shortcuts():
                text = key.toString()
                if text and text not in window.RESERVED_FOR_TEXT:
                    assert text in bindings, (name, text)
    assert QKeySequence("Ctrl+M").toString() in bindings
