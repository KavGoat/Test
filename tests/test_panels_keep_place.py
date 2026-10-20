"""Changing a control in a panel never moves the panel or takes the focus
away from it (the user, 2026-10-20: "The Checkbox Properties panel scrolls to
the top after I change the selected option inside the panel, which is wrong;
ensure this issue does not exist on any panel").

For each panel, and for the Properties panel each kind of markup: the panel
is scrolled down, a control low in it is changed with the mouse and the keys
as a person changes it, and then the scroll bar is where it was, the control
that was used still has the focus, and the change took effect.
"""
from __future__ import annotations

import re

import pytest
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (QAbstractItemView, QAbstractScrollArea, QAbstractSpinBox,
                               QApplication, QCheckBox, QComboBox, QDialog, QLineEdit,
                               QListWidget, QRadioButton, QScrollArea, QSlider, QWidget)


def pump(times: int = 4) -> None:
    for _ in range(times):
        QApplication.processEvents()


@pytest.fixture
def w(window):
    window.resize(1280, 640)
    window.show()
    window.activateWindow()
    window.view.set_zoom(1.0)
    pump()
    return window


# ---------------------------------------------------------------------------
# finding a control, and knowing it again after a rebuild
# ---------------------------------------------------------------------------
CONTROLS = (QCheckBox, QRadioButton, QComboBox, QAbstractSpinBox, QLineEdit, QListWidget,
            QSlider)


def key_of(widget, root) -> tuple:
    """A control's place in its panel: its kind, name and number among its
    kind, which a panel built afresh for the same thing gives it again."""
    if widget is None:
        return None
    kind = type(widget)
    same = [c for c in root.findChildren(kind) if type(c) is kind]
    return (kind.__name__, widget.objectName(),
            same.index(widget) if widget in same else -1)


def find_by_key(key, root):
    if key is None:
        return None
    name, object_name, number = key
    same = [c for c in root.findChildren(QWidget)
            if type(c).__name__ == name]
    return same[number] if 0 <= number < len(same) else None


def focused_key(root):
    focus = QApplication.focusWidget()
    while focus is not None and not isinstance(focus, CONTROLS) and focus is not root:
        focus = focus.parentWidget()          # a spin box's or a list's own part
    if focus is None or not root.isAncestorOf(focus):
        return None
    return key_of(focus, root)


def _usable(control) -> bool:
    if not control.isEnabled() or not control.isVisible():
        return False
    if isinstance(control, QLineEdit):
        if isinstance(control.parentWidget(), (QAbstractSpinBox, QComboBox)) \
                or control.isReadOnly():
            return False
    if isinstance(control, QComboBox):
        if control.count() < 2 and not control.isEditable():
            return False
    if isinstance(control, QAbstractSpinBox):
        if control.isReadOnly():
            return False
    if isinstance(control, QListWidget):
        return any(control.item(i).flags() & Qt.ItemIsUserCheckable
                   for i in range(control.count()))
    return True


def low_controls(root: QWidget) -> list:
    """The lowest control of each kind in the panel."""
    found = []
    for control in root.findChildren(QWidget):
        if not isinstance(control, CONTROLS) or not _usable(control):
            continue
        place = QRect(control.mapTo(root, QPoint(0, 0)), control.size())
        found.append((place.bottom(), control))
    found.sort(key=lambda pair: -pair[0])
    picked, kinds = [], set()
    for _bottom, control in found:
        kind = next(k for k in CONTROLS if isinstance(control, k))
        if kind in kinds:
            continue
        kinds.add(kind)
        picked.append(control)
    return picked


def bring_low(area: QAbstractScrollArea, control) -> int:
    """Scroll *area* down until *control* is at the bottom of what it shows,
    as a person scrolls down to reach it."""
    viewport = area.viewport()
    bar = area.verticalScrollBar()
    if isinstance(area, QScrollArea):
        bottom = control.mapTo(area.widget(), QPoint(0, control.height())).y()
        bar.setValue(bottom + 6 - viewport.height())
    else:                                       # a list: its last rows in view
        bar.setValue(bar.maximum())
    pump(2)
    return bar.value()


def value_of(control):
    if isinstance(control, (QCheckBox, QRadioButton)):
        return control.isChecked()
    if isinstance(control, QComboBox):
        return control.currentText() if control.isEditable() else control.currentIndex()
    if isinstance(control, QAbstractSpinBox):
        return control.text()
    if isinstance(control, QLineEdit):
        return control.text()
    if isinstance(control, QListWidget):
        return [control.item(i).checkState() for i in range(control.count())]
    if isinstance(control, QSlider):
        return control.value()
    return None


def operate(control) -> None:
    """Change *control* as a person does: a click, a pick from its list, the
    arrow keys or typing."""
    if isinstance(control, (QCheckBox, QRadioButton)):
        QTest.mouseClick(control, Qt.LeftButton, Qt.NoModifier,
                         QPoint(8, control.height() // 2))
    elif isinstance(control, QComboBox) and not control.isEditable():
        # open its list with a click, then the next entry and Enter
        QTest.mouseClick(control, Qt.LeftButton)
        pump(2)
        view = control.view()
        last = control.currentIndex() >= control.count() - 1
        QTest.keyClick(view, Qt.Key_Up if last else Qt.Key_Down)
        QTest.keyClick(view, Qt.Key_Return)
        pump(2)
        if view.isVisible():
            control.hidePopup()
    elif isinstance(control, (QAbstractSpinBox, QSlider)):
        QTest.mouseClick(control, Qt.LeftButton, Qt.NoModifier,
                         QPoint(min(12, control.width() // 3), control.height() // 2))
        top = control.value() >= control.maximum() if hasattr(control, "maximum") else False
        for _ in range(3):                     # (a turn of 1° snaps back to none)
            QTest.keyClick(control, Qt.Key_Down if top else Qt.Key_Up)
    elif isinstance(control, QComboBox):          # editable: type into it
        edit = control.lineEdit()
        QTest.mouseClick(edit, Qt.LeftButton)
        QTest.keyClick(edit, Qt.Key_End)
        QTest.keyClicks(edit, "2")
        QTest.keyClick(edit, Qt.Key_Return)
    elif isinstance(control, QLineEdit):
        QTest.mouseClick(control, Qt.LeftButton)
        number = re.match(r"\s*(\d+(?:\.\d+)?)(.*)", control.text())
        if number:                              # a size: a bigger one
            QTest.keyClick(control, Qt.Key_A, Qt.ControlModifier)
            QTest.keyClicks(control, f"{float(number.group(1)) + 5:g}{number.group(2)}")
        elif not control.text():                # a unit, a name: one
            QTest.keyClicks(control, "m")
        else:
            QTest.keyClick(control, Qt.Key_End)
            QTest.keyClicks(control, "z")
        if not isinstance(control.window(), QDialog):   # (in a dialog Enter is OK)
            QTest.keyClick(control, Qt.Key_Return)
    elif isinstance(control, QListWidget):
        # tick (or untick) the last row's box, where it is drawn
        row = control.item(control.count() - 1)
        control.scrollToItem(row)
        pump(1)
        rect = control.visualItemRect(row)
        QTest.mouseClick(control.viewport(), Qt.LeftButton, Qt.NoModifier,
                         QPoint(rect.left() + 10, rect.center().y()))
    pump(6)


def check_panel(area, root, what: str, state=None, controls=None) -> list:
    """Scroll *area* down to each kind of control low in it, change it, and
    say what went wrong: [] when nothing did. *state* reads what the change
    should change (the document, a setting)."""
    problems = []
    controls = controls if controls is not None else low_controls(root)
    assert controls, f"{what}: no control"
    tried = 0
    for name in [key_of(control, root) for control in controls]:
        control = find_by_key(name, root)
        start = bring_low(area, control)
        if start <= 0:
            continue                           # near the top: nothing to keep
        tried += 1
        before = value_of(control)
        policy = control.focusPolicy()
        was = state() if state is not None else None
        operate(control)
        after_scroll = area.verticalScrollBar().value()
        if after_scroll != start:
            problems.append(f"{what}: {name} moved the panel {start} → {after_scroll}")
        focus = focused_key(root)
        if focus != name and policy != Qt.NoFocus:
            problems.append(f"{what}: {name} lost the focus to {focus}")
        now = find_by_key(name, root)
        if now is None or value_of(now) == before:
            problems.append(f"{what}: {name} did not change ({before!r})")
        elif state is not None and state() == was:
            problems.append(f"{what}: {name} changed nothing")
    assert tried, f"{what}: the panel does not scroll (nothing to test)"
    return problems


# ---------------------------------------------------------------------------
# the Properties panel, for every kind of markup
# ---------------------------------------------------------------------------
def document_state(w):
    return ([frame.serialize_items() for frame in w.view.scene().frames],
            [page.scale.to_dict() for page in w.document.pages])


TOOLS = ["pen", "highlighter", "line", "arrow", "arc", "polyline", "rect", "ellipse",
         "polygon", "cloud", "highlight", "redact", "link", "text", "callout",
         "cloud_callout", "note", "stamp", "flag", "contents", "checkbox",
         "measure_length", "measure_dimension", "measure_polylength", "measure_area",
         "measure_perimeter", "measure_volume", "measure_angle", "measure_radius",
         "measure_diameter", "count", "sketch_rect", "sketch_ellipse"]
OTHERS = ["equation", "calc_block", "table", "table_cells", "sheet_page", "picture",
          "two_markups"]


def _pick(w, *items) -> None:
    w.select_tool("select")
    w.view.scene().clearSelection()
    for item in items:
        item.setSelected(True)
    w.refresh_selection()
    pump()


def subject(w, kind: str) -> None:
    """Put *kind* on the page as a person does, and show it in Properties."""
    from tests.test_every_command_is_bindable import _draw
    from tests.test_usability import markups
    if kind in TOOLS:
        _draw(w, kind, 120, 140, 260, 230)
        _pick(w, markups(w)[-1])
    elif kind == "two_markups":
        _draw(w, "rect", 100, 120, 200, 200)
        _draw(w, "rect", 260, 120, 360, 200)
        _pick(w, *markups(w)[-2:])
    elif kind in ("equation", "calc_block"):
        from tests.test_calc_panels import an_equation
        made = [an_equation(w, "a:2", 100, 120), an_equation(w, "b:a+1", 100, 160)]
        pump()
        found = [i for i in w.view.scene().ordered_markups()
                 if getattr(i, "region", None) is not None]
        _pick(w, *(found if kind == "calc_block" else found[:1]))
        if kind == "calc_block":
            w.insert_block()
            pump()
            block = next(i for i in w.view.scene().ordered_markups()
                         if getattr(i, "TYPE", "") == "calc_block")
            _pick(w, block)
        assert made
    elif kind in ("table", "table_cells"):
        from tests.test_tables import make_table
        table = make_table(w)
        if kind == "table":
            _pick(w, table)
        else:
            from tests.test_sheet_pages import open_at
            open_at(w, table, "B2")
            pump()
    elif kind == "sheet_page":
        from tests.test_sheet_pages import open_at, sheet_page
        run = sheet_page(w)
        open_at(w, run, "B2")
        pump()
    elif kind == "picture":
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        from PySide6.QtGui import QColor, QImage
        from calcforge.items.media import ImageItem
        picture = QImage(40, 40, QImage.Format_RGB32)
        picture.fill(QColor("#3366cc"))
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.WriteOnly)
        picture.save(buffer, "PNG")
        key = w.document.add_asset(bytes(data), ".png")
        item = ImageItem(key, QRectF(0, 0, 120, 120))
        w.document.pages[0].frame.add_markup(item, QPointF(100, 100))
        item.load_from_document(w.document)
        _pick(w, item)


@pytest.mark.parametrize("kind", TOOLS + OTHERS)
def test_the_properties_panel_stays_put_for_every_kind(w, kind):
    w.show_panel("dock_properties", True)
    pump()
    subject(w, kind)
    panel = w.properties_panel
    assert panel._items, f"{kind}: Properties shows nothing"
    assert check_panel(panel, panel.body, f"Properties of {kind}",
                       state=lambda: document_state(w)) == []


def test_the_checkbox_panel_stays_put_as_options_are_ticked_added_and_restyled(w):
    """The user's own case: the option picked in the panel, then an option
    added (the panel is built again for it) and the Box changed on the
    toolbar — the panel stays where it was and the list keeps the keys."""
    from PySide6.QtWidgets import QToolButton
    from calcforge.items.checkbox import CheckboxItem
    w.show_panel("dock_properties", True)
    subject(w, "checkbox")
    item = next(i for i in w.view.scene().ordered_markups() if isinstance(i, CheckboxItem))
    panel = w.properties_panel
    for _ in range(3):
        QTest.mouseClick(panel.body.findChild(QToolButton, "checkboxAddOption"), Qt.LeftButton)
        pump(4)
    options = panel.body.findChild(QListWidget, "checkboxOptions")
    start = bring_low(panel, options)
    assert start > 0
    row = options.item(2)
    rect = options.visualItemRect(row)
    QTest.mouseClick(options.viewport(), Qt.LeftButton, Qt.NoModifier,
                     QPoint(rect.left() + 10, rect.center().y()))
    pump(6)
    listed = key_of(options, panel.body)
    assert item.is_checked(2) and panel.verticalScrollBar().value() == start
    assert focused_key(panel.body) == listed
    count = len(item.options())
    QTest.mouseClick(panel.body.findChild(QToolButton, "checkboxAddOption"), Qt.LeftButton)
    pump(6)
    assert len(item.options()) == count + 1
    assert panel.verticalScrollBar().value() == start, "Add Option threw the panel up"
    assert focused_key(panel.body) == listed
    # the toolbar's Box ▾, which builds the panel again
    from tests.test_propbar_gaps import pick
    focus = focused_key(panel.body)
    pick(w.checkbox_shape_combo, "circle")
    pump(6)
    assert item.box_shape == "circle"
    assert panel.verticalScrollBar().value() == start, "the toolbar's Box threw the panel up"
    assert focus is not None


def test_another_selection_starts_at_the_top_of_the_panel(w):
    w.show_panel("dock_properties", True)
    subject(w, "callout")
    panel = w.properties_panel
    scroll_to = panel.verticalScrollBar().maximum()
    panel.verticalScrollBar().setValue(scroll_to)
    subject(w, "rect")
    pump(4)
    assert panel.verticalScrollBar().value() == 0


# ---------------------------------------------------------------------------
# the other panels
# ---------------------------------------------------------------------------
def a_long_document(w, tmp_path, pages=24):
    """A PDF of *pages* pages with "beam" written on each, opened as a
    person opens one."""
    import pymupdf
    pdf = pymupdf.open()
    for number in range(pages):
        page = pdf.new_page(width=595, height=842)
        for line in range(3):
            page.insert_text((72, 100 + 40 * line), f"beam B{number}-{line} on grid {line}")
    path = tmp_path / "long.pdf"
    pdf.save(str(path))
    w.open_from_command_line(str(path))
    pump(8)
    return path


def at_the_bottom(view) -> int:
    """Scroll a list to its end, as a person does to reach its last rows."""
    bar = view.verticalScrollBar()
    bar.setValue(bar.maximum())
    pump(2)
    assert bar.value() > 0, "the list does not scroll"
    return bar.value()


def rows_up(tree, rows: int) -> int:
    """A scroll bar value *rows* rows above the end."""
    bar = tree.verticalScrollBar()
    step = 1 if tree.verticalScrollMode() == QAbstractItemView.ScrollPerItem \
        else tree.visualItemRect(tree.topLevelItem(0)).height()
    value = bar.maximum() - rows * step
    assert value > 0, "the list is too short"
    return value


def last_shown_row(tree):
    """The lowest row drawn whole in a tree's view."""
    node = tree.itemAt(QPoint(10, 2))
    while node is not None:
        below = tree.itemBelow(node)
        if below is None or tree.visualItemRect(below).bottom() > tree.viewport().height():
            break
        node = below
    assert node is not None
    return node


def stays(view, start, owner, what):
    """The list is where it was and the focus is still in *owner*."""
    pump(6)
    assert view.verticalScrollBar().value() == start, f"{what} moved the list"
    focus = QApplication.focusWidget()
    assert focus is not None and (focus is owner or owner.isAncestorOf(focus)), \
        f"{what} took the focus to {focus}"


def test_the_markups_list_stays_put_while_a_cell_low_in_it_is_edited(w):
    from calcforge.items.shapes import RectItem
    from tests.test_markups_list_editing import double_click_cell, enter, type_over
    frame = w.document.pages[0].frame
    for number in range(40):
        item = RectItem("rect", QRectF(0, 0, 30, 20))
        item.subject = f"Wall {number}"
        frame.add_markup(item, QPointF(40 + (number % 10) * 50, 60 + (number // 10) * 40))
    w.show_markups_list(True)
    w.refresh_lists()
    pump()
    panel = w.markups_panel
    tree = panel.tree
    start = at_the_bottom(tree)
    node = last_shown_row(tree)
    page, uid = node.data(0, Qt.UserRole)
    double_click_cell(panel, uid, "Subject")
    type_over(panel, "Slab edge")
    enter(panel)
    stays(tree, start, tree, "editing a Subject low in the Markups List")
    assert any(i.uid == uid and i.subject == "Slab edge"
               for i in w.document.pages[0].frame.markups())


@pytest.fixture
def a_full_chest(w):
    """Three tool sets of twenty tools each, in List view, put back after."""
    import json
    from calcforge.items.shapes import RectItem
    from calcforge.settings import app_settings
    from calcforge.ui import toolsets
    settings = app_settings()
    names = ("Walls", "Doors", "Windows")
    kept = {key: settings.value(key) for key in (toolsets.TOOLSETS_KEY, "toolchest/views",
                                                 "toolchest/size")}
    sets = []
    for name in names:
        entries = [toolsets.entry_for(RectItem("rect", QRectF(0, 0, 30, 20)),
                                      label=f"{name} {number}") for number in range(20)]
        sets.append(toolsets.ToolSet(name, entries))
    toolsets.save_toolsets(sets)
    panel = w.toolsets_panel
    for name in names:
        panel.views[name] = "list"
    settings.setValue("toolchest/views", json.dumps(panel.views))
    panel.rebuild()
    w.show_panel("dock_toolsets", True)
    pump()
    yield panel
    for key, value in kept.items():
        if value is None:
            settings.remove(key)
        else:
            settings.setValue(key, value)
    for name in names:
        panel.views.pop(name, None)


def test_the_tool_chest_stays_put_as_a_tool_low_in_it_is_picked(w, a_full_chest):
    panel = a_full_chest
    tree = panel.tree
    start = at_the_bottom(tree)
    node = last_shown_row(tree)
    QTest.mouseClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier,
                     tree.visualItemRect(node).center())
    stays(tree, start, tree, "picking a tool low in the Tool Chest")
    entry = panel.current_entry()
    assert entry is not None and entry.label in node.text(0)


def test_the_tool_chest_stays_put_as_a_tools_mode_is_changed(w, a_full_chest):
    from calcforge.ui import toolsets
    panel = a_full_chest
    tree = panel.tree
    at_the_bottom(tree)
    node = last_shown_row(tree)
    QTest.mouseClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier,
                     tree.visualItemRect(node).center())
    pump()
    start = tree.verticalScrollBar().value()
    label = panel.current_entry().label
    # its right-click menu, opened where the row is, and Properties Mode clicked
    menu = panel.build_menu()
    menu.popup(tree.viewport().mapToGlobal(tree.visualItemRect(node).center()))
    pump()
    action = next(a for a in menu.actions() if "Properties" in a.text().replace("&", ""))
    QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier, menu.actionGeometry(action).center())
    stays(tree, start, tree, "Properties Mode on a tool low in the Tool Chest")
    entry = panel.current_entry()
    assert entry is not None and entry.label == label and entry.mode == toolsets.PROPERTIES


def test_the_tool_chest_stays_put_as_its_tool_size_is_changed(w, a_full_chest):
    panel = a_full_chest
    tree = panel.tree
    at_the_bottom(tree)
    start = rows_up(tree, 3)
    tree.verticalScrollBar().setValue(start)
    pump()
    size = panel.size_slider.value()
    QTest.mouseClick(panel.size_slider, Qt.LeftButton, Qt.NoModifier,
                     QPoint(panel.size_slider.width() // 2, panel.size_slider.height() // 2))
    pump()
    size = panel.size_slider.value()
    QTest.keyClick(panel.size_slider, Qt.Key_Right)
    stays(tree, start, panel.size_slider, "the Tool Chest's size slider")
    assert panel.size_slider.value() != size and panel.tool_size == panel.size_slider.value()


def test_the_thumbnails_stay_put_as_a_page_low_in_them_is_picked(w, tmp_path):
    a_long_document(w, tmp_path)
    w.show_panel("dock_pages", True)
    pump(6)
    strip = w.pages_panel.list
    start = at_the_bottom(strip)
    viewport = strip.viewport()
    model = strip.model()
    rows = [row for row in range(model.rowCount())
            if viewport.rect().contains(strip.visualRect(model.index(row, 0)))]
    row = max(rows, key=lambda r: strip.visualRect(model.index(r, 0)).bottom())
    assert row > 0
    QTest.mouseClick(viewport, Qt.LeftButton, Qt.NoModifier,
                     strip.visualRect(model.index(row, 0)).center())
    stays(strip, start, strip, "picking a page low in Thumbnails")
    assert w.current_index == row


def test_bookmarks_stay_put_as_one_low_in_them_is_deleted(w, tmp_path):
    from PySide6.QtWidgets import QPushButton
    from calcforge.core.document import Bookmark
    a_long_document(w, tmp_path)
    w.document.bookmarks = [Bookmark(f"Section {n}.{part}", page.uid, 20.0 + 200 * part)
                            for n, page in enumerate(w.document.pages) for part in range(3)]
    w.refresh_lists()
    w.show_panel("dock_bookmarks", True)
    pump()
    panel = w.bookmarks_panel
    tree = panel.tree
    at_the_bottom(tree)
    start = rows_up(tree, 3)
    tree.verticalScrollBar().setValue(start)
    pump()
    node = last_shown_row(tree)
    gone = node.text(0).strip()
    QTest.mouseClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier,
                     tree.visualItemRect(node).center())
    delete = next(b for b in panel.findChildren(QPushButton) if b.text() == "Delete")
    QTest.mouseClick(delete, Qt.LeftButton)
    stays(tree, start, panel, "deleting a bookmark low in Bookmarks")
    assert gone not in [mark.title for mark in w.document.bookmarks]


def _search(w, words: str, replacement: str = ""):
    w.show_panel("dock_search", True)
    pump()
    panel = w.search_panel
    QTest.mouseClick(panel.query, Qt.LeftButton)
    QTest.keyClicks(panel.query, words)
    QTest.keyClick(panel.query, Qt.Key_Return)
    if replacement:
        QTest.mouseClick(panel.replacement, Qt.LeftButton)
        QTest.keyClicks(panel.replacement, replacement)
    pump(6)
    return panel


def test_search_results_stay_put_as_one_low_in_them_is_shown(w, tmp_path):
    a_long_document(w, tmp_path, pages=12)
    panel = _search(w, "beam")
    tree = panel.results
    start = at_the_bottom(tree)
    node = last_shown_row(tree)
    QTest.mouseClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier,
                     tree.visualItemRect(node).center())
    stays(tree, start, tree, "showing a search result low in Search")
    assert w.current_index == int(node.text(0)) - 1


def test_search_results_stay_put_as_a_markup_low_in_them_is_replaced(w):
    from PySide6.QtWidgets import QPushButton
    from tests.test_markups_list_editing import add
    from calcforge.items.shapes import RectItem
    for number in range(30):
        item = RectItem("rect", QRectF(0, 0, 30, 20))
        item.subject = f"beam {number}"
        add(w, item, (40 + (number % 5) * 100, 60 + (number // 5) * 60))
    panel = _search(w, "beam", "joist")
    tree = panel.results
    at_the_bottom(tree)
    start = rows_up(tree, 3)
    tree.verticalScrollBar().setValue(start)
    pump()
    node = last_shown_row(tree)
    QTest.mouseClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier,
                     tree.visualItemRect(node).center())
    pump()
    start = tree.verticalScrollBar().value()
    replace = next(b for b in panel.findChildren(QPushButton) if b.text() == "Replace")
    QTest.mouseClick(replace, Qt.LeftButton)
    stays(tree, start, panel, "Replace on a result low in Search")
    assert sum("joist" in i.subject for i in w.document.pages[0].frame.markups()) == 1


def test_variables_stay_put_as_one_low_in_them_is_picked_and_made_global(w):
    from tests.test_calc_panels import an_equation
    for number in range(30):
        an_equation(w, f"v{number}:{number}", 60 + (number % 3) * 160, 60 + (number // 3) * 40)
    w.show_panel("dock_variables", True)
    pump(6)
    panel = w.variables_panel
    tree = panel.tree
    start = at_the_bottom(tree)
    node = last_shown_row(tree)
    name = node.text(0)
    QTest.mouseClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier,
                     tree.visualItemRect(node).center())
    stays(tree, start, tree, "picking a variable low in Variables")
    node = last_shown_row(tree)
    assert node.text(0) == name
    menu = panel.build_menu(node)
    menu.popup(tree.viewport().mapToGlobal(tree.visualItemRect(node).center()))
    pump()
    action = next(a for a in menu.actions() if a.text() == "Make Global")
    QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier, menu.actionGeometry(action).center())
    stays(tree, start, tree, "Make Global on a variable low in Variables")
    assert last_shown_row(tree).text(0) == "🌐 " + name


def test_the_maths_panel_stays_put_as_a_button_low_in_it_is_used(w):
    from PySide6.QtWidgets import QToolButton
    from tests.test_calc_modes import into_calc_mode
    w.show_panel("dock_maths", True)
    pump(4)
    panel = w.maths_panel
    into_calc_mode(w, 100, 120)
    pump()
    start = at_the_bottom(panel)
    seen = panel.viewport().rect()
    buttons = [b for b in panel.widget().findChildren(QToolButton) if b.isVisible()
               and not b.isCheckable()            # (a section's heading folds it)
               and seen.contains(QRect(b.mapTo(panel.viewport(), QPoint(0, 0)), b.size()))]
    button = max(buttons, key=lambda b: b.mapTo(panel.viewport(), QPoint(0, 0)).y())
    focus = QApplication.focusWidget()
    QTest.mouseClick(button, Qt.LeftButton)
    pump(6)
    assert panel.verticalScrollBar().value() == start, "the Maths panel moved"
    assert QApplication.focusWidget() is focus, "the equation lost the focus"
    assert w.view.calc.editing() and w.view.calc.item is not None, button.text()
    # a section folded from its heading, low in the panel: the equation
    # keeps the keys
    header = max((h for h in panel.widget().findChildren(QToolButton, "mathsSectionHeader")
                  if h.isVisible() and seen.contains(QRect(
                      h.mapTo(panel.viewport(), QPoint(0, 0)), h.size()))),
                 key=lambda h: h.mapTo(panel.viewport(), QPoint(0, 0)).y())
    folded = header.isChecked()
    QTest.mouseClick(header, Qt.LeftButton)
    pump(4)
    assert header.isChecked() != folded
    assert QApplication.focusWidget() is focus, "folding a section took the focus"


def test_the_page_panel_stays_put(w):
    from calcforge.sheet.pagination import options
    from tests.test_sheet_pages import open_at, sheet_page
    run = sheet_page(w)
    open_at(w, run, "B2")
    w.show_panel("dock_page", True)
    pump(6)
    panel = w.page_panel
    panel.refresh()
    pump()

    def state():
        page = w.current_page()
        return page.setup.to_dict(), page.scale.to_dict(), dict(options(run.sheet))
    assert check_panel(panel, panel.widget(), "Page", state=state) == []


def test_the_preferences_dialog_stays_put(w):
    from calcforge.ui import dialogs, preferences
    dialog = dialogs.PreferencesDialog(preferences.current(), w)
    dialog.show()
    dialog.activateWindow()
    scroller = dialog.findChild(QScrollArea, "preferencesScroll")
    scroller.setFixedHeight(260)                # a short screen's
    pump(4)
    try:
        assert check_panel(scroller, scroller.widget(), "Preferences") == []
    finally:
        dialog.reject()
        dialog.deleteLater()


def test_colour_processing_keeps_the_focus_on_what_is_changed(w):
    """It has no scroll bar; the control used keeps the focus."""
    from calcforge.ui.colorprocess import ColorProcessingDialog
    dialog = ColorProcessingDialog(w, document=w.document, current=0)
    dialog.show()
    dialog.activateWindow()
    pump(4)
    try:
        for name in [key_of(c, dialog) for c in low_controls(dialog)]:
            control = find_by_key(name, dialog)
            if control is None or not control.isVisible():
                continue
            before = value_of(control)
            operate(control)
            assert focused_key(dialog) == name, f"Colour Processing: {name} lost the focus"
            assert value_of(find_by_key(name, dialog)) != before, name
    finally:
        dialog.reject()
        dialog.deleteLater()
