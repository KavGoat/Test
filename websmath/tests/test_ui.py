"""Drive the Qt worksheet the way a user does (offscreen)."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402

from websmath.engine.display import display_text  # noqa: E402
from websmath.ui.worksheet_view import WorksheetView  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def press(view, key, text=""):
    view.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, key, Qt.NoModifier, text))


def type_at(view, x, y, text):
    view.focus_item(None)
    view.scene_.cross = QPointF(x, y)
    for ch in text:
        press(view, 0, ch)


def test_result_waits_until_the_region_is_left(app):
    # SMath Studio desktop: while an evaluation is edited its result is the
    # empty box; it is calculated when the region is left
    v = WorksheetView()
    type_at(v, 18, 18, "2+3=")
    item = v.focused_item
    assert item is not None and item.region.pending
    press(v, Qt.Key_Return)
    assert not item.region.pending and display_text(item.region.display) == "5"


def test_other_regions_update_when_region_is_left(app):
    v = WorksheetView()
    type_at(v, 18, 18, "q:5")
    press(v, Qt.Key_Return)
    type_at(v, 18, 72, "q=")
    press(v, Qt.Key_Return)
    below = [it for it in v.items.values() if it.region.y == 72][0]
    assert display_text(below.region.display) == "5"
    top = [it for it in v.items.values() if it.region.y == 18][0]
    v.focus_item(top)
    top.editor.set_cursor(top.editor.root, 1)
    press(v, 0, "7")
    assert display_text(below.region.display) == "5"  # not yet
    press(v, Qt.Key_Return)  # leave the region
    assert below.region.error.message == "q - not defined."


def test_autocomplete_lists_units_first(app):
    v = WorksheetView()
    type_at(v, 18, 18, "si")
    labels = [v.suggestions.item(i).text() for i in range(v.suggestions.count())]
    assert labels[:3] == ["kpsi", "ksi", "psi"]  # units listed without the apostrophe
    assert "sin" in labels and "sinh" in labels


def test_drag_below_definition_order(app):
    v = WorksheetView()
    type_at(v, 18, 18, "x:5")
    press(v, Qt.Key_Return)
    type_at(v, 18, 72, "x=")
    press(v, Qt.Key_Return)
    use = [it for it in v.items.values() if it.region.y == 72][0]
    use.region.y = 0
    use.setPos(18, 0)
    v.recalculate()
    assert use.region.error.message == "x - not defined."


def test_empty_region_disappears_on_leave(app):
    v = WorksheetView()
    type_at(v, 18, 18, "1")
    press(v, Qt.Key_Backspace)
    press(v, Qt.Key_Return)
    assert not v.items


def test_render_does_not_crash(app):
    v = WorksheetView()
    for k, s in enumerate(["x=5", "1/3=", "sqrt(16=", "log(8,2=", "abs(-3=", "5'm/'s=", "if(1>0,2",
                           "M:mat(", "2'kN/'m=", "y+1="]):
        type_at(v, 18, 18 + 45 * k, s)
    v.focus_item(None)
    img = v.grab()
    assert not img.isNull()


def test_copy_paste_regions(app):
    v = WorksheetView()
    type_at(v, 18, 18, "x:5")
    press(v, Qt.Key_Return)
    type_at(v, 18, 54, "x=")
    press(v, Qt.Key_Return)
    v.select_all()
    v.copy()
    v.scene_.cross = QPointF(18, 180)
    v.paste()
    assert len(v.items) == 4
    pasted = sorted((it.region for it in v.items.values()), key=lambda r: r.y)[-1]
    assert pasted.y > 150 and display_text(pasted.display) == "5"


def test_copy_paste_inside_equation(app):
    v = WorksheetView()
    type_at(v, 18, 18, "1+2*3")
    ed = v.focused_item.editor
    ed.key(" ")  # select 2*3
    v.copy()
    ed.set_cursor(ed.root, len(ed.root))
    press(v, 0, "+")
    v.paste()
    assert ed.root.text() == "1+2*3+2*3"


def test_calculation_menu_commands(app):
    v = WorksheetView()
    type_at(v, 18, 18, "1+2*3")
    ed = v.focused_item.editor
    ed.key(" ")
    v.calculate_selection()
    assert ed.root.text() == "1+6"
    type_at(v, 18, 60, "M")
    v.determinant_selection()
    assert v.focused_item.editor.root.text() == "det(M)"


def test_format_and_areas(app, tmp_path):
    from websmath.io.smfile import load_sm, save_sm

    v = WorksheetView()
    type_at(v, 18, 18, "abc ")  # text region
    v.format_selection(toggle="bold", font_size=14.0, bg_color="#ffff80")
    press(v, Qt.Key_Return)
    v.insert_separator(90)
    v.insert_area(120, 90)
    type_at(v, 18, 153, "y:2")
    press(v, Qt.Key_Return)
    area = [it for it in v.items.values() if it.region.special == "area"][0]
    inside = [it for it in v.items.values() if it.region.y == 153][0]
    v.toggle_area(area)
    assert not inside.isVisible()
    v.toggle_area(area)
    assert inside.isVisible()
    path = tmp_path / "f.sm"
    save_sm(v.worksheet, path)
    ws = load_sm(path)
    kinds = sorted(r.kind for r in ws.regions)
    assert kinds == ["area", "math", "separator", "text"]
    text = [r for r in ws.regions if r.kind == "text"][0]
    assert text.bold and text.font_size == 14 and text.bg_color == "#ffff80"


def test_export_pdf(app, tmp_path):
    from PySide6.QtGui import QPdfWriter

    v = WorksheetView()
    type_at(v, 18, 18, "1/3=")
    out = tmp_path / "sheet.pdf"
    v.render_pages(QPdfWriter(str(out)))
    assert out.stat().st_size > 500


def test_up_down_move_between_regions(app):
    v = WorksheetView()
    type_at(v, 18, 18, "a:1")
    press(v, Qt.Key_Return)
    type_at(v, 18, 72, "b:2")
    first = [it for it in v.items.values() if it.region.y == 18][0]
    press(v, Qt.Key_Up)
    assert v.focused_item is first
    press(v, Qt.Key_Down)
    assert v.focused_item.region.y == 72


def test_variable_unit_clash_needs_a_choice(app):
    v = WorksheetView()
    type_at(v, 18, 18, "m:10")
    press(v, Qt.Key_Return)
    type_at(v, 18, 72, "m")
    ed = v.focused_item.editor
    press(v, 0, "=")  # blocked: m is a variable and a unit
    assert ed.root.text() == "m" and v.suggestions.isVisible()
    press(v, Qt.Key_Return)  # Enter too (nothing chosen with the arrows yet)
    assert v.focused_item is not None and ed.root.text() == "m"
    s = v.suggestions
    s.setCurrentRow([i for i, e in enumerate(s.entries()) if e.name == "m"][0])
    press(v, Qt.Key_Tab)
    press(v, 0, "=")
    it = v.focused_item
    press(v, Qt.Key_Return)
    assert display_text(it.region.display) == "10"
    # choosing the unit instead gives 'm
    type_at(v, 18, 126, "m")
    s.setCurrentRow([i for i, e in enumerate(s.entries()) if e.name == "'m"][0])
    press(v, Qt.Key_Tab)
    press(v, 0, "=")
    it = v.focused_item
    press(v, Qt.Key_Return)
    assert display_text(it.region.display) == "1 m"
    # no clash: typed straight through
    type_at(v, 18, 180, "q+1")
    assert v.focused_item.editor.root.text() == "q+1"


def test_suggestion_keys_follow_site(app):
    v = WorksheetView()
    type_at(v, 18, 18, "sq")
    s = v.suggestions
    assert s.currentItem().text() == "sqrt" and s.tooltip.isVisible()
    press(v, Qt.Key_Return)  # Enter applies only after moving in the list
    assert not s.isVisible() or v.focused_item.editor.root.text() == "sq"
    type_at(v, 18, 72, "sq")
    press(v, Qt.Key_Tab)  # Tab applies the highlighted entry
    assert v.focused_item.editor.root.text().startswith("√")


# -- right-click menu: SMath Cloud's items, with the effects seen on the site ------------

def _menu_titles(menu):
    out = []
    for a in menu.actions():
        if a.isSeparator():
            out.append("-")
        elif a.menu():
            out.append((a.text(), _menu_titles(a.menu())))
        else:
            out.append(a.text())
    return out


def _trigger(menu, *path):
    for title in path[:-1]:
        menu = next(a.menu() for a in menu.actions() if a.text() == title)
    next(a for a in menu.actions() if a.text() == path[-1]).trigger()


def test_context_menu_items_match_site(app):
    v = WorksheetView()
    type_at(v, 18, 18, "1/3=")
    t = _menu_titles(v.context_menu(v.focused_item))
    top = [x if isinstance(x, str) else x[0] for x in t]
    assert top == ["Cut", "Copy", "Paste", "-", "Delete", "-", "Select all", "-", "Display input data", "-",
                   "Go to definition", "Show description", "Disable evaluation", "-", "Ignore units", "-",
                   "Optimization", "Decimal places", "Exponential threshold", "Fractions", "Rounding"]
    sub = dict(x for x in t if not isinstance(x, str))
    assert sub["Optimization"] == ["Symbolic", "Numeric", "None"]
    assert sub["Decimal places"][:4] == ["Trailing zeros", "-", "Significant figures mode", "-"]
    assert sub["Decimal places"][4:] == [str(n) if n != 4 else "4 *" for n in range(16)]
    assert sub["Exponential threshold"] == [str(n) if n != 5 else "5 *" for n in range(16)]
    assert sub["Fractions"] == ["Decimal", "Fraction", "Auto", "Default", "-", "Use mixed numbers"]
    assert sub["Rounding"] == ["Half to even", "Away from zero"]
    # outside a region only the editing items
    v.focus_item(None)
    assert _menu_titles(v.context_menu(None)) == ["Cut", "Copy", "Paste", "-", "Delete", "-", "Select all"]


@pytest.mark.parametrize("typed,path,shown", [
    ("1/3=", ("Decimal places", "2"), "0.33"),
    ("2/3=", ("Decimal places", "0"), "1"),
    ("1234.5678=", ("Decimal places", "Significant figures mode"), "1235"),
    ("0.012345=", ("Decimal places", "Significant figures mode"), "0.01235"),
    ("1.5=", ("Decimal places", "Trailing zeros"), "1.5000"),
    ("12345=", ("Exponential threshold", "2"), "1.2345·10^4"),
    ("1.23*10^9=", ("Exponential threshold", "15"), "1230000000"),
    ("0.75=", ("Fractions", "Auto"), "3/4"),
    ("2+3=", ("Optimization", "None"), "2+3"),
    ("5'm+2=", ("Ignore units",), "7"),
    ("5'm*2'kg=", ("Ignore units",), "10"),
])
def test_context_menu_options_match_site(app, typed, path, shown):
    v = WorksheetView()
    type_at(v, 18, 18, typed)
    item = v.focused_item
    _trigger(v.context_menu(item), *path)
    assert display_text(item.region.display) == shown


def test_context_menu_fractions_and_mixed(app):
    v = WorksheetView()
    type_at(v, 18, 18, "7/3=")
    item = v.focused_item
    _trigger(v.context_menu(item), "Fractions", "Fraction")
    assert display_text(item.region.display) == "7/3"
    _trigger(v.context_menu(item), "Fractions", "Use mixed numbers")
    assert display_text(item.region.display) == "2 1/3"
    _trigger(v.context_menu(item), "Fractions", "Default")
    assert display_text(item.region.display) == "2.3333"


def test_default_rounding_is_half_to_even_on_the_binary_value(app):
    # observed: 2.00025 = 2.0002 (the double is 2.000249999...), g.e = 9.8066
    v = WorksheetView()
    type_at(v, 18, 18, "2.00025=")
    first = v.focused_item
    press(v, Qt.Key_Return)
    assert display_text(first.region.display) == "2.0002"
    type_at(v, 18, 72, "0.125=")
    item = v.focused_item
    _trigger(v.context_menu(item), "Decimal places", "2")
    assert display_text(item.region.display) == "0.12"  # a true tie: to even
    _trigger(v.context_menu(item), "Rounding", "Away from zero")
    assert display_text(item.region.display) == "0.13"


def test_display_input_and_disable_evaluation(app):
    v = WorksheetView()
    type_at(v, 18, 18, "x:2")
    press(v, Qt.Key_Return)
    type_at(v, 18, 72, "x+3=")
    use = v.focused_item
    _trigger(v.context_menu(use), "Display input data")
    assert not use.region.show_input
    press(v, Qt.Key_Return)
    wide = use.frame_rect().width()
    v.focus_item(use)
    assert use.frame_rect().width() > wide  # the input shows again while editing
    press(v, Qt.Key_Return)
    top = [it for it in v.items.values() if it.region.y == 18][0]
    v.focus_item(top)
    _trigger(v.context_menu(top), "Disable evaluation")
    assert not top.region.enabled
    assert use.region.error is not None and use.region.error.message == "x - not defined."
    v.focus_item(use)
    _trigger(v.context_menu(use), "Go to definition")
    assert v.focused_item is use  # x is no longer defined anywhere


def test_region_options_saved_in_sm(app, tmp_path):
    from websmath.io.smfile import load_sm, save_sm

    v = WorksheetView()
    type_at(v, 18, 18, "1/3=")
    item = v.focused_item
    for path in (("Decimal places", "2"), ("Decimal places", "Trailing zeros"), ("Fractions", "Fraction"),
                 ("Optimization", "Numeric"), ("Ignore units",), ("Display input data",)):
        _trigger(v.context_menu(item), *path)
    f = tmp_path / "opts.sm"
    save_sm(v.worksheet, f)
    text = f.read_text(encoding="utf-8")
    assert 'decimalPlaces="2"' in text and 'optimize="2"' in text
    r = load_sm(f).regions[0]
    assert (r.fmt.decimals, r.fmt.trailing_zeros, r.fmt.fractions) == (2, True, "fraction")
    assert (r.optimization, r.ignore_units, r.show_input) == ("numeric", True, False)
    assert display_text(r.display) == "1/3"


def test_calculation_differentiate_and_solve(app):
    v = WorksheetView()
    type_at(v, 18, 18, "f(x")
    press(v, Qt.Key_Right)
    for ch in ":x^3":
        press(v, 0, ch)
    press(v, Qt.Key_Right)
    for ch in "+2*x":
        press(v, 0, ch)
    ed = v.focused_item.editor
    assert ed.root.text() == "f(x)≔x^(3)+2*x"
    v.differentiate_selection()  # cursor is on the last x
    assert ed.root.text() == "f(x)≔3*x^(2)+2"
    press(v, Qt.Key_Return)
    type_at(v, 18, 90, "x^2")
    press(v, Qt.Key_Right)
    press(v, 0, "-")
    press(v, 0, "9")
    v.focused_item.editor.set_cursor(v.focused_item.editor.root, 1)  # on x
    v.solve_selection()
    below = max(v.items.values(), key=lambda it: it.region.y)
    assert display_text(below.region.display) == "[-3; 3]"


def _mouse(v, kind, scene_pt, buttons=Qt.LeftButton):
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent

    vp = QPointF(v.mapFromScene(scene_pt))
    t = {"press": QEvent.MouseButtonPress, "move": QEvent.MouseMove, "release": QEvent.MouseButtonRelease}[kind]
    ev = QMouseEvent(t, vp, v.viewport().mapToGlobal(vp.toPoint()), Qt.LeftButton,
                     buttons if kind != "release" else Qt.NoButton, Qt.NoModifier)
    {"press": v.mousePressEvent, "move": v.mouseMoveEvent, "release": v.mouseReleaseEvent}[kind](ev)


def test_drag_region_by_its_frame_while_editing(app):
    v = WorksheetView()
    type_at(v, 18, 18, "x:5")
    item = v.focused_item  # being edited: dragging inside would select
    edge = item.mapToScene(QPointF(1, item.frame_rect().height() / 2))
    _mouse(v, "press", edge)
    _mouse(v, "move", edge + QPointF(90, 45))
    _mouse(v, "release", edge + QPointF(90, 45))
    assert (item.region.x, item.region.y) == (108, 63)
    assert item.editor.selection is None


def test_drag_unfocused_region_anywhere_and_group(app):
    v = WorksheetView()
    type_at(v, 18, 18, "a:1")
    press(v, Qt.Key_Return)
    type_at(v, 18, 72, "b:2")
    press(v, Qt.Key_Return)
    v.select_all()
    first = [it for it in v.items.values() if it.region.y == 18][0]
    mid = first.mapToScene(first.frame_rect().center())
    _mouse(v, "press", mid)
    _mouse(v, "move", mid + QPointF(0, 90))
    _mouse(v, "release", mid + QPointF(0, 90))
    assert sorted(it.region.y for it in v.items.values()) == [108, 162]


def test_desktop_main_window(app):
    from websmath.ui.mainwindow import MainWindow

    w = MainWindow()
    menus = [a.text().replace("&", "") for a in w.menuBar().actions()]
    assert menus == ["File", "Edit", "View", "Insert", "Calculation", "Tools", "Pages", "Help"]
    calc = [a for a in w.menuBar().actions() if a.text() == "&Calculation"][0].menu()
    titles = [a.text() for a in calc.actions() if a.text()]
    assert "Simplify" not in titles and "Differentiate" in titles and "Solve" in titles
    assert [s.title for s in w.panel.sections][:6] == ["Arithmetic", "Matrices", "Boolean", "Functions",
                                                       "Plot", "Programming"]
    assert "Constants" in [s.title for s in w.panel.sections]
    # pages: a second worksheet in the same window
    first = w.view
    second = w.new_page()
    assert w.view is second and first is not second and len(w.mdi.subWindowList()) == 2
    assert first.scene_.page_mode == "pages"
    w.close()


def test_desired_unit_box(app):
    """While an evaluation is edited a black box for the desired unit follows
    the result; only the box can be edited, a unit gets into it from the list
    (Tab), and when it matches the automatic unit disappears.  Results are
    calculated when the region is left (SMath Studio desktop)."""
    v = WorksheetView()
    type_at(v, 18, 18, "test:5'kN")
    press(v, Qt.Key_Return)
    type_at(v, 18, 72, "test=")
    it = v.focused_item
    press(v, Qt.Key_Return)
    assert display_text(it.region.display) == "5 kN"    # automatic unit
    v.focus_item(it)
    assert it._result_unit_rect is not None             # the box is there while editing
    v.mouseDoubleClickEvent(None)                       # the automatic unit is not editable
    assert it.editor.unit.is_empty()
    box = it._result_unit_rect.translated(it._layout.x, it._baseline)
    it.place_cursor(box.center())
    assert it.editor.in_unit
    press(v, 0, "k")
    names = [v.suggestions.item(i).text() for i in range(v.suggestions.count())]
    assert names[:5] == ["k", "K", "kA", "kat", "katal"]  # as SMath Studio desktop
    assert it.region.pending                            # result waits: the box shows
    press(v, 0, "N")
    press(v, Qt.Key_Tab)                                # kN from the list
    assert it.editor.unit.text() == "'kN"
    press(v, Qt.Key_Return)
    assert display_text(it.region.display) == "5"       # kN matches: no automatic unit
    assert it._result_unit_rect is not None             # 'kN stays shown
    type_at(v, 18, 126, "test=")
    press(v, Qt.Key_Return)
    last = max(v.items.values(), key=lambda x: x.region.y)
    assert last._result_unit_rect is None               # no box when not editing


def _unit_region(app, keys=("5'kN*2=",)):
    v = WorksheetView()
    type_at(v, 18, 18, keys[0])
    return v, v.focused_item


def test_delete_works_in_the_unit_box(app):
    v, item = _unit_region(app)
    press(v, Qt.Key_Right)  # into the unit box
    for ch in "'kN":
        press(v, 0, ch)
    press(v, Qt.Key_Tab)  # apply the suggestion
    ed = item.editor
    assert ed.in_unit and ed.unit.text() == "'kN"
    press(v, Qt.Key_Left)
    press(v, Qt.Key_Delete)  # k|N -> k
    assert ed.unit.text() == "'k"
    press(v, Qt.Key_Left)
    assert ed.pos == 0  # |'k: no invisible stop between ' and k
    press(v, Qt.Key_Delete)  # the visible k goes, and the marker with it
    assert ed.unit.text() == ""
    for ch in "'kN":
        press(v, 0, ch)
    press(v, Qt.Key_Tab)
    press(v, Qt.Key_Home)
    item.editor.set_cursor(ed.unit, 0)
    press(v, Qt.Key_Delete)  # |'kN -> 'N (still a unit), not the variable kN
    assert ed.unit.text() == "'N"


def test_click_into_empty_unit_box_shows_the_cursor(app):
    v, item = _unit_region(app)
    v.show()
    r = item._result_unit_rect.translated(item._layout.x, item._baseline)
    item.place_cursor(r.center())
    ed = item.editor
    assert ed.in_unit and item._row_info(ed.row) is not None


def test_cursor_is_always_drawable_fuzz(app):
    import random

    keys = [Qt.Key_Left, Qt.Key_Right, Qt.Key_Home, Qt.Key_End, Qt.Key_Backspace, Qt.Key_Delete, Qt.Key_Tab,
            "'", "k", "N", "m", "/", "s", "^", "2"]
    for seed in range(150):
        rng = random.Random(seed)
        v, item = _unit_region(app, (rng.choice(["5'kN*2=", "3'm/2's=", "(2'm)^2=", "12="]),))
        for step in range(30):
            k = rng.choice(keys)
            if rng.random() < 0.15 and item._result_unit_rect is not None:
                item.place_cursor(item._result_unit_rect.translated(item._layout.x, item._baseline).center())
            elif isinstance(k, str):
                press(v, 0, k)
            else:
                press(v, k)
            if v.focused_item is not item:
                break
            ed = item.editor
            assert item._row_info(ed.row) is not None, (seed, step)
            if k in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Home, Qt.Key_End, Qt.Key_Tab, Qt.Key_Backspace):
                # a key that moves the cursor never leaves it on the hidden marker slot
                items = ed.row.items
                p = ed.pos
                assert not (0 < p < len(items) and items[p - 1] == "'" and items[p] not in ("'",)
                            and isinstance(items[p], str) and items[p].isalpha()), (seed, step, ed.row.text(), p)


# -- through the real window: menu shortcuts see the keys first ----------------------
@pytest.fixture
def win(app):
    from websmath.ui.mainwindow import MainWindow

    w = MainWindow()
    w.show()
    w.activateWindow()
    yield w
    w.close()


def _keys(w, *seq, mods=Qt.NoModifier):
    from PySide6.QtTest import QTest

    target = w.view.viewport()
    w.view.setFocus()
    for k in seq:
        if isinstance(k, str):
            for ch in k:
                QTest.keyClicks(target, ch)
        else:
            QTest.keyClick(target, k, mods)
    app = QtWidgets.QApplication.instance()
    app.processEvents()


def test_delete_key_deletes_right_of_the_cursor(win):
    v = win.view
    type_at(v, 18, 18, "123+45")
    ed = v.focused_item.editor
    ed.set_cursor(ed.root, 1)
    _keys(win, Qt.Key_Delete)
    assert ed.root.text() == "13+45"
    _keys(win, Qt.Key_End)
    ed.set_cursor(ed.root, 0)
    _keys(win, Qt.Key_Delete)
    assert ed.root.text() == "3+45"


def test_delete_key_in_the_unit_box_through_the_window(win):
    v = win.view
    type_at(v, 18, 18, "5'kN*2=")
    item = v.focused_item
    ed = item.editor
    press(v, Qt.Key_Right)
    for ch in "'N":
        press(v, 0, ch)
    press(v, Qt.Key_Tab)
    assert ed.unit.text() == "'N"
    _keys(win, Qt.Key_Left)  # |N, as in the photo
    _keys(win, Qt.Key_Delete)
    assert ed.unit.text() == ""


def test_shift_arrows_select_like_a_word_processor(win):
    v = win.view
    type_at(v, 18, 18, "12+345")
    ed = v.focused_item.editor
    _keys(win, Qt.Key_Left, mods=Qt.ShiftModifier)
    _keys(win, Qt.Key_Left, mods=Qt.ShiftModifier)
    assert ed.selection[1:] == (4, 6)
    _keys(win, Qt.Key_Right, mods=Qt.ShiftModifier)  # shrinks back from the anchor
    assert ed.selection[1:] == (5, 6)
    _keys(win, Qt.Key_Home, mods=Qt.ShiftModifier)
    assert ed.selection[1:] == (0, 6)
    _keys(win, Qt.Key_Left)  # a plain arrow collapses to the start
    assert ed.selection is None and ed.pos == 0
    _keys(win, Qt.Key_End, mods=Qt.ShiftModifier)
    press(v, 0, "7")  # typing replaces the selection
    assert ed.root.text() == "7"


def test_word_jumps_and_word_selection(win):
    import sys

    word = Qt.AltModifier if sys.platform == "darwin" else Qt.ControlModifier
    v = win.view
    type_at(v, 18, 18, "abc+def*12")
    ed = v.focused_item.editor
    _keys(win, Qt.Key_Left, mods=word)
    assert ed.pos == 8  # before 12
    _keys(win, Qt.Key_Left, mods=word)
    assert ed.pos == 4  # before def
    _keys(win, Qt.Key_Right, mods=word | Qt.ShiftModifier)
    assert ed.selection[1:] == (4, 7)  # def
    _keys(win, Qt.Key_Delete)
    assert ed.root.text() == "abc+*12"


def test_shift_selection_grows_out_of_a_box(win):
    v = win.view
    type_at(v, 18, 18, "1+2/3")
    ed = v.focused_item.editor
    assert ed.row is not ed.root  # in the denominator
    for _ in range(2):
        _keys(win, Qt.Key_Left, mods=Qt.ShiftModifier)
    r, a, b = ed.selection
    assert r is ed.root and b - a == 1  # the whole fraction


def test_text_region_selection(win):
    v = win.view
    type_at(v, 18, 18, '"hello world')
    item = v.focused_item
    ed = item.editor
    assert ed.kind == "text"
    import sys

    word = Qt.AltModifier if sys.platform == "darwin" else Qt.ControlModifier
    _keys(win, Qt.Key_Left, mods=word | Qt.ShiftModifier)
    assert ed.text_selection() == (6, 11)
    press(v, 0, "X")
    assert ed.text == "hello X"
    _keys(win, Qt.Key_Home, mods=Qt.ShiftModifier)
    _keys(win, Qt.Key_Delete)
    assert ed.text == ""
    item.update()


def test_placeholder_is_centred_on_the_equals_sign(app):
    from PySide6.QtGui import QPainterPath

    from websmath.ui.layout import Layouter, Style

    lay = Layouter(Style(10))
    ph = lay.placeholder()
    _l, _w, h, bottom = ph.box
    path = QPainterPath()
    path.addText(0, 0, lay.style.font(1.0, op=True), "=")
    b = path.boundingRect()
    assert abs((bottom + h / 2) - (-(b.top() + b.bottom()) / 2)) < 0.3


def test_selection_keys_fuzz(win):
    import random

    v = win.view
    keys = [Qt.Key_Left, Qt.Key_Right, Qt.Key_Home, Qt.Key_End, Qt.Key_Delete, Qt.Key_Backspace, "7", "x", "+", "/", "^"]
    mods = [Qt.NoModifier, Qt.ShiftModifier, Qt.ControlModifier, Qt.AltModifier,
            Qt.ShiftModifier | Qt.ControlModifier, Qt.ShiftModifier | Qt.AltModifier]
    for seed in range(60):
        rng = random.Random(seed)
        start = rng.choice(["12+345=", "5'kN*2=", "1+2/3", '"hello world', "(a+b)^2"])
        type_at(v, 18, 18 + 54 * seed, start)
        item = v.focused_item
        for _ in range(25):
            k = rng.choice(keys)
            if isinstance(k, str):
                press(v, 0, k)
            else:
                _keys(win, k, mods=rng.choice(mods))
            if v.focused_item is not item:
                break
            ed = item.editor
            if ed.kind == "text":
                sel = ed.text_selection()
                assert 0 <= ed.text_pos <= len(ed.text)
                assert sel is None or 0 <= sel[0] < sel[1] <= len(ed.text)
            else:
                assert 0 <= ed.pos <= len(ed.row.items)
                if ed.selection:
                    r, a, b = ed.selection
                    assert 0 <= a < b <= len(r.items) and r is ed.row, (seed, ed.root.text())
                assert item._row_info(ed.row) is not None
        press(v, Qt.Key_Return)


def test_selection_box_is_drawn_while_dragging(app):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QImage, QPainter

    v = WorksheetView()
    type_at(v, 36, 36, "x:1")
    press(v, Qt.Key_Return)
    v.focus_item(None)
    _mouse(v, "press", QPointF(10, 10))
    _mouse(v, "move", QPointF(150, 80))
    assert v.scene_.rubber is not None and v.selected
    img = QImage(200, 120, QImage.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    v.scene_.render(p, QRectF(0, 0, 200, 120), QRectF(0, 0, 200, 120))
    p.end()
    # the dotted blue frame is on screen at the box's right edge
    edge = [QColor(img.pixel(x, y)) for x in range(146, 152) for y in range(20, 70)]
    assert any(c.blue() > 150 and c.red() < 100 for c in edge)
    _mouse(v, "release", QPointF(150, 80))
    assert v.scene_.rubber is None and v.selected  # the box goes, the selection stays


def test_side_panel_symbols_are_visible_and_insert(app):
    from PySide6.QtTest import QTest

    from websmath.app import use_light_palette
    from websmath.ui.mainwindow import MainWindow

    use_light_palette(app)
    w = MainWindow()
    w.show()
    for sec in w.panel.sections:
        for b in sec.buttons:
            if b.isEnabled():  # black on the white panel, whatever the system theme
                assert b.palette().color(b.foregroundRole()).lightness() < 60, (sec.title, b.text())
    v = w.view
    type_at(v, 18, 18, "a+")
    sqrt = next(b for b in w.panel.sections[0].buttons if b.text() == "√")
    QTest.mouseClick(sqrt, Qt.LeftButton)
    assert "√" in v.focused_item.editor.root.text()
    w.close()


# -- desktop Pages view: margins, gaps, coordinates -------------------------------------
def test_page_coordinates_round_trip(app):
    from websmath.ui.worksheet_view import CONTENT_H, PAGE_MARGIN, PAGE_STEP

    v = WorksheetView()
    sc = v.scene_
    assert sc.page_mode == "pages"
    for x, y in [(0, 0), (18, 18), (100, CONTENT_H - 1), (50, CONTENT_H), (7, 2 * CONTENT_H + 300)]:
        p = sc.to_scene(x, y)
        back = sc.to_sheet(p)
        assert abs(back.x() - x) < 1e-9 and abs(back.y() - y) < 1e-9
    # the first row of page 2 is drawn below page 2's top margin
    p = sc.to_scene(0, CONTENT_H)
    assert p.y() == PAGE_STEP + PAGE_MARGIN and p.x() == PAGE_MARGIN
    # a click in the gap between pages belongs to the next page's first row
    gap = sc.to_sheet(QPointF(100, PAGE_STEP - 5))
    assert gap.y() == CONTENT_H


def test_region_on_second_page_and_drag_across_break(app):
    from websmath.ui.worksheet_view import CONTENT_H, PAGE_MARGIN, PAGE_STEP

    v = WorksheetView()
    type_at(v, 18, CONTENT_H + 27, "x:1")
    item = v.focused_item
    press(v, Qt.Key_Return)
    assert item.region.y >= CONTENT_H
    assert item.pos().y() == PAGE_STEP + PAGE_MARGIN + (item.region.y - CONTENT_H)
    # drag it up by its frame onto page 1
    start = item.mapToScene(QPointF(1, 5))
    _mouse(v, "press", start)
    _mouse(v, "move", start - QPointF(0, 100))
    _mouse(v, "release", start - QPointF(0, 100))
    assert item.region.y < CONTENT_H  # moved onto page 1 in worksheet coordinates
    assert item.pos() == v.scene_.to_scene(item.region.x, item.region.y)


def test_view_modes_keep_worksheet_positions(app):
    v = WorksheetView()
    type_at(v, 36, 45, "y:2")
    item = v.focused_item
    press(v, Qt.Key_Return)
    for mode in ("none", "bounds", "pages"):
        v.set_page_mode(mode)
        assert (item.region.x, item.region.y) == (36, 45)
        assert item.pos() == v.scene_.to_scene(36, 45)
    v.set_page_mode("none")
    assert item.pos() == QPointF(36, 45)


def test_shift_wheel_scrolls_sideways(app):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QWheelEvent

    v = WorksheetView()
    v.resize(300, 300)
    v.show()
    type_at(v, 1400, 18, "w:1")  # far right: the sheet is wider than the window
    press(v, Qt.Key_Return)
    bar = v.horizontalScrollBar()
    bar.setValue(0)
    ev = QWheelEvent(QPointF(50, 50), QPointF(50, 50), QPoint(0, 0), QPoint(0, -120), Qt.NoButton,
                     Qt.ShiftModifier, Qt.NoScrollPhase, False)
    v.wheelEvent(ev)
    assert bar.value() > 0


def test_line_block_sizes_round_trip():
    from websmath.io.smfile import dumps, loads

    import pathlib

    beam = pathlib.Path(__file__).resolve().parents[2] / "smath" / "SMath Studio" / "examples" / "Beam.sm"
    if not beam.exists():
        pytest.skip("SMath examples not present")
    from websmath.io.smfile import load_sm

    ws = load_sm(beam)
    texts = [r.editor.root.text() for r in ws.ordered() if r.kind == "math"]
    assert not any(";1;1}" in t or ";3;1}" in t for t in texts)  # the size operands are not statements
    again = loads(dumps(ws))
    assert [r.editor.root.text() for r in again.ordered() if r.kind == "math"] == texts
