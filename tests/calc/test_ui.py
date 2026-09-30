"""Drive the Qt worksheet the way a user does (offscreen)."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402

from markforge.calc.engine.display import display_text  # noqa: E402
from tests.calc.legacy_ui.worksheet_view import WorksheetView  # noqa: E402


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
    from tests.calc.smfile import load_sm, save_sm

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


def test_calculation_solve(app):
    v = WorksheetView()
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


# -- through the real window: menu shortcuts see the keys first ----------------------
@pytest.fixture
def win(app):
    from tests.calc.legacy_ui.mainwindow import MainWindow

    w = MainWindow()
    w.show()
    w.activateWindow()
    yield w
    _dispose(w)


def _dispose(w):
    """Close WebSMath's window and let Qt delete it, so it cannot keep the
    keyboard focus into the next test (these tests share the process with
    CalcForge's)."""
    from PySide6.QtCore import QCoreApplication, QEvent

    w.close()
    w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QtWidgets.QApplication.instance().processEvents()


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


def test_side_panel_symbols_are_visible_and_insert(app):
    from PySide6.QtTest import QTest

    from tests.calc.legacy_ui.app import use_light_palette
    from tests.calc.legacy_ui.mainwindow import MainWindow

    palette = app.palette()
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
    _dispose(w)
    app.setPalette(palette)


# -- desktop Pages view: margins, gaps, coordinates -------------------------------------
