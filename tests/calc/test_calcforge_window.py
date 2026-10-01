"""WebSMath's window tests, driving the CalcForge window instead.

Ported from tests/calc/test_ui.py (phase 2): the same keystrokes and the same
checks, through CalcForge's real canvas — keys and mouse as Qt events, Calc
mode, equations as page items. Positions are in SMath pixels on page 1:
SMath's 9 px grid is CalcForge's 6.75 pt grid, so region.x/y read the same.
"""
from __future__ import annotations

import random
import sys

import pytest
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QKeyEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from calcforge.calc.docsheet import PT_PER_PX, sheet_for
from calcforge.calc.engine.display import display_text
from calcforge.items.calc import CalcItem
from tests.test_usability import click, drag


class Sheet:
    """What the WebSMath tests asked of their view, on the CalcForge window."""

    def __init__(self, window):
        self.window = window
        self.view = window.view
        self.calc = window.view.calc
        self.calc.mode = "calc"
        self.frame = window.document.pages[0].frame

    # -- where things are ---------------------------------------------------------------
    def scene_point(self, x_px: float, y_px: float) -> QPointF:
        return self.frame.mapToScene(QPointF(x_px * PT_PER_PX, y_px * PT_PER_PX))

    @property
    def focused_item(self):
        return self.calc.item

    @property
    def items(self) -> dict:
        return dict(getattr(sheet_for(self.window.document), "items", {}))

    @property
    def suggestions(self):
        return self.calc.suggestions

    def at_y(self, y_px: float) -> CalcItem:
        return [it for it in self.items.values() if it.region.y == y_px][0]

    # -- doing things ---------------------------------------------------------------------
    def press(self, key, text=""):
        QApplication.sendEvent(self.view, QKeyEvent(QKeyEvent.KeyPress, key, Qt.NoModifier, text))

    def type_at(self, x_px, y_px, text):
        """Click bare paper there (the red cross), then type."""
        self.calc.leave()
        self.view.scene().clearSelection()
        p = self.scene_point(x_px, y_px)
        self.calc.place_cross(self.frame, self.frame.mapFromScene(p))
        for ch in text:
            self.press(0, ch)

    def focus_item(self, item):
        if item is None:
            self.calc.leave()
        else:
            self.calc.focus(item)

    def keys(self, *seq, mods=Qt.NoModifier):
        """Through the window's shortcut handling, as a real keyboard does."""
        target = self.view.viewport()
        self.view.setFocus()
        for k in seq:
            if isinstance(k, str):
                for ch in k:
                    QTest.keyClicks(target, ch)
            else:
                QTest.keyClick(target, k, mods)
        QApplication.instance().processEvents()

    def drag(self, start: QPointF, end: QPointF):
        drag(self.view, start.x(), start.y(), end.x(), end.y())
        sheet_for(self.window.document).settle()


@pytest.fixture
def v(window):
    window.show()
    window.activateWindow()
    return Sheet(window)


def centre(item) -> QPointF:
    return item.mapToScene(item.local_rect().center())


def test_result_waits_until_the_region_is_left(v):
    v.type_at(18, 18, "2+3=")
    item = v.focused_item
    assert item is not None and item.region.pending
    v.press(Qt.Key_Return)
    assert not item.region.pending and display_text(item.region.display) == "5"


def test_other_regions_update_when_region_is_left(v):
    v.type_at(18, 18, "q:5")
    v.press(Qt.Key_Return)
    v.type_at(18, 72, "q=")
    v.press(Qt.Key_Return)
    below = v.at_y(72)
    assert display_text(below.region.display) == "5"
    top = v.at_y(18)
    v.focus_item(top)
    top.editor.set_cursor(top.editor.root, 1)
    v.press(0, "7")
    assert display_text(below.region.display) == "5"      # not yet
    v.press(Qt.Key_Return)                                # leave the region
    assert below.region.error.message == "q - not defined."


def test_autocomplete_lists_units_first(v):
    v.type_at(18, 18, "si")
    labels = [v.suggestions.item(i).text() for i in range(v.suggestions.count())]
    assert labels[:3] == ["kpsi", "ksi", "psi"]
    assert "sin" in labels and "sinh" in labels


def test_drag_below_definition_order(v):
    v.type_at(18, 18, "x:5")
    v.press(Qt.Key_Return)
    v.type_at(18, 72, "x=")
    v.press(Qt.Key_Return)
    use = v.at_y(72)
    start = centre(use)
    v.drag(start, start - QPointF(0, 72 * PT_PER_PX))      # up above the definition
    assert use.region.y < 18
    assert use.region.error.message == "x - not defined."


def test_empty_region_disappears_on_leave(v):
    v.type_at(18, 18, "1")
    v.press(Qt.Key_Backspace)
    v.press(Qt.Key_Return)
    assert not v.items


def test_render_does_not_crash(v):
    for k, s in enumerate(["x=5", "1/3=", "sqrt(16=", "log(8,2=", "abs(-3=", "5'm/'s=", "if(1>0,2",
                           "M:mat(", "2'kN/'m=", "y+1="]):
        v.type_at(18, 18 + 45 * k, s)
    v.focus_item(None)
    assert not v.window.grab().isNull()


def test_export_pdf(v, tmp_path):
    from calcforge.io import export as export_io
    v.type_at(18, 18, "1/3=")
    v.press(Qt.Key_Return)
    out = tmp_path / "sheet.pdf"
    export_io.export_pdf(v.window.document, str(out))
    import pymupdf
    with pymupdf.open(str(out)) as document:
        assert "0.3333" in document[0].get_text()


def test_up_down_move_between_regions(v):
    v.type_at(18, 18, "a:1")
    v.press(Qt.Key_Return)
    v.type_at(18, 72, "b:2")
    first = v.at_y(18)
    v.press(Qt.Key_Up)
    assert v.focused_item is first
    v.press(Qt.Key_Down)
    assert v.focused_item.region.y == 72


def test_a_variable_named_like_a_unit_is_the_variable(v):
    """The user (2026-10-01): "I couldn't type = at all" — m:10 above, then
    m typed, used to block every key until the variable or the unit was
    picked from the list (WebSMath, after SMath Cloud). The variable defined
    here is what is meant; the unit is 'm."""
    v.type_at(18, 18, "m:10")
    v.press(Qt.Key_Return)
    v.type_at(18, 72, "m")
    v.press(0, "=")                           # straight through
    it = v.focused_item
    assert it.editor.root.text() == "m="
    v.press(Qt.Key_Return)
    assert display_text(it.region.display) == "10"
    v.type_at(18, 126, "'m")                  # the unit, as SMath writes one
    v.press(0, "=")
    it = v.focused_item
    v.press(Qt.Key_Return)
    assert display_text(it.region.display) == "1 m"
    v.type_at(18, 180, "m:")                  # and : as well
    assert v.focused_item.editor.root.text().startswith("m≔")
    v.type_at(18, 234, "q+1")                 # no clash: typed straight through
    assert v.focused_item.editor.root.text() == "q+1"


def test_suggestion_keys_follow_site(v):
    v.type_at(18, 18, "sq")
    s = v.suggestions
    assert s.currentItem().text() == "sqrt" and s.tooltip.isVisible()
    v.press(Qt.Key_Return)                    # Enter applies only after moving in the list
    assert not s.isVisible() or v.focused_item.editor.root.text() == "sq"
    v.type_at(18, 72, "sq")
    v.press(Qt.Key_Tab)                       # Tab applies the highlighted entry
    assert v.focused_item.editor.root.text().startswith("√")


def test_drag_region_by_its_frame_while_editing(v):
    v.type_at(18, 18, "x:5")
    item = v.focused_item                     # being edited: dragging inside would select
    edge = item.mapToScene(QPointF(1 * PT_PER_PX, item.local_rect().height() / 2))
    v.drag(edge, edge + QPointF(90 * PT_PER_PX, 45 * PT_PER_PX))
    assert (item.region.x, item.region.y) == (108, 63)
    assert item.editor.selection is None


def test_drag_unfocused_region_anywhere_and_group(v):
    v.type_at(18, 18, "a:1")
    v.press(Qt.Key_Return)
    v.type_at(18, 72, "b:2")
    v.press(Qt.Key_Return)
    v.calc.leave()
    for item in v.items.values():
        item.setSelected(True)
    first = v.at_y(18)
    mid = centre(first)
    v.drag(mid, mid + QPointF(0, 90 * PT_PER_PX))
    assert sorted(it.region.y for it in v.items.values()) == [108, 162]


def test_desired_unit_box(v):
    """While an evaluation is edited a black box for the desired unit follows
    the result; only the box can be edited, a unit gets into it from the list
    (Tab), and when it matches the automatic unit disappears."""
    v.type_at(18, 18, "test:5'kN")
    v.press(Qt.Key_Return)
    v.type_at(18, 72, "test=")
    it = v.focused_item
    v.press(Qt.Key_Return)
    assert display_text(it.region.display) == "5 kN"          # automatic unit
    v.focus_item(it)
    view = it._view
    assert view._result_unit_rect is not None                  # the box is there while editing
    assert it.editor.unit.is_empty()
    box = view._result_unit_rect.translated(view._layout.x, view._baseline)
    view.place_cursor(box.center())
    assert it.editor.in_unit
    v.press(0, "k")
    names = [v.suggestions.item(i).text() for i in range(v.suggestions.count())]
    assert names[:5] == ["k", "K", "kA", "kat", "katal"]      # as SMath Studio desktop
    assert it.region.pending                                   # result waits: the box shows
    v.press(0, "N")
    v.press(Qt.Key_Tab)                                        # kN from the list
    assert it.editor.unit.text() == "'kN"
    v.press(Qt.Key_Return)
    assert display_text(it.region.display) == "5"              # kN matches: no automatic unit
    assert it._view._result_unit_rect is not None              # 'kN stays shown
    v.type_at(18, 126, "test=")
    v.press(Qt.Key_Return)
    last = max(v.items.values(), key=lambda x: x.region.y)
    assert last._view._result_unit_rect is None                # no box when not editing


def _unit_region(v, keys="5'kN*2="):
    v.type_at(18, 18, keys)
    return v.focused_item


def test_delete_works_in_the_unit_box(v):
    item = _unit_region(v)
    v.press(Qt.Key_Right)                     # into the unit box
    for ch in "'kN":
        v.press(0, ch)
    v.press(Qt.Key_Tab)
    ed = item.editor
    assert ed.in_unit and ed.unit.text() == "'kN"
    v.press(Qt.Key_Left)
    v.press(Qt.Key_Delete)                    # k|N -> k
    assert ed.unit.text() == "'k"
    v.press(Qt.Key_Left)
    assert ed.pos == 0
    v.press(Qt.Key_Delete)
    assert ed.unit.text() == ""
    for ch in "'kN":
        v.press(0, ch)
    v.press(Qt.Key_Tab)
    v.press(Qt.Key_Home)
    item.editor.set_cursor(ed.unit, 0)
    v.press(Qt.Key_Delete)                    # |'kN -> 'N (still a unit)
    assert ed.unit.text() == "'N"


def test_click_into_empty_unit_box_shows_the_cursor(v):
    item = _unit_region(v)
    view = item._view
    r = view._result_unit_rect.translated(view._layout.x, view._baseline)
    # a real click on the black box
    p = item.mapToScene(QPointF(r.center().x() * PT_PER_PX, r.center().y() * PT_PER_PX))
    click(v.view, p.x(), p.y())
    ed = item.editor
    assert ed.in_unit and view._row_info(ed.row) is not None


def test_cursor_is_always_drawable_fuzz(v):
    keys = [Qt.Key_Left, Qt.Key_Right, Qt.Key_Home, Qt.Key_End, Qt.Key_Backspace, Qt.Key_Delete, Qt.Key_Tab,
            "'", "k", "N", "m", "/", "s", "^", "2"]
    for seed in range(150):
        rng = random.Random(seed)
        item = _unit_region(v, rng.choice(["5'kN*2=", "3'm/2's=", "(2'm)^2=", "12="]))
        for step in range(30):
            k = rng.choice(keys)
            view = item._view
            if rng.random() < 0.15 and view is not None and view._result_unit_rect is not None:
                view.place_cursor(view._result_unit_rect.translated(view._layout.x, view._baseline).center())
            elif isinstance(k, str):
                v.press(0, k)
            else:
                v.press(k)
            if v.focused_item is not item:
                break
            ed = item.editor
            assert item._view._row_info(ed.row) is not None, (seed, step)
            if k in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Home, Qt.Key_End, Qt.Key_Tab, Qt.Key_Backspace):
                items = ed.row.items
                p = ed.pos
                assert not (0 < p < len(items) and items[p - 1] == "'" and items[p] not in ("'",)
                            and isinstance(items[p], str) and items[p].isalpha()), (seed, step, ed.row.text(), p)
        v.calc.leave()
        for item in list(v.items.values()):
            item.parentItem().remove_markup(item)


# -- through the real window: menu shortcuts see the keys first ----------------------
def test_delete_key_deletes_right_of_the_cursor(v):
    v.type_at(18, 18, "123+45")
    ed = v.focused_item.editor
    ed.set_cursor(ed.root, 1)
    v.keys(Qt.Key_Delete)
    assert ed.root.text() == "13+45"
    v.keys(Qt.Key_End)
    ed.set_cursor(ed.root, 0)
    v.keys(Qt.Key_Delete)
    assert ed.root.text() == "3+45"


def test_delete_key_in_the_unit_box_through_the_window(v):
    v.type_at(18, 18, "5'kN*2=")
    ed = v.focused_item.editor
    v.press(Qt.Key_Right)
    for ch in "'N":
        v.press(0, ch)
    v.press(Qt.Key_Tab)
    assert ed.unit.text() == "'N"
    v.keys(Qt.Key_Left)
    v.keys(Qt.Key_Delete)
    assert ed.unit.text() == ""


def test_shift_arrows_select_like_a_word_processor(v):
    v.type_at(18, 18, "12+345")
    ed = v.focused_item.editor
    v.keys(Qt.Key_Left, mods=Qt.ShiftModifier)
    v.keys(Qt.Key_Left, mods=Qt.ShiftModifier)
    assert ed.selection[1:] == (4, 6)
    v.keys(Qt.Key_Right, mods=Qt.ShiftModifier)
    assert ed.selection[1:] == (5, 6)
    v.keys(Qt.Key_Home, mods=Qt.ShiftModifier)
    assert ed.selection[1:] == (0, 6)
    v.keys(Qt.Key_Left)
    assert ed.selection is None and ed.pos == 0
    v.keys(Qt.Key_End, mods=Qt.ShiftModifier)
    v.press(0, "7")
    assert ed.root.text() == "7"


def test_word_jumps_and_word_selection(v):
    word = Qt.AltModifier if sys.platform == "darwin" else Qt.ControlModifier
    v.type_at(18, 18, "abc+def*12")
    ed = v.focused_item.editor
    v.keys(Qt.Key_Left, mods=word)
    assert ed.pos == 8
    v.keys(Qt.Key_Left, mods=word)
    assert ed.pos == 4
    v.keys(Qt.Key_Right, mods=word | Qt.ShiftModifier)
    assert ed.selection[1:] == (4, 7)
    v.keys(Qt.Key_Delete)
    assert ed.root.text() == "abc+*12"


def test_shift_selection_grows_out_of_a_box(v):
    v.type_at(18, 18, "1+2/3")
    ed = v.focused_item.editor
    assert ed.row is not ed.root
    for _ in range(2):
        v.keys(Qt.Key_Left, mods=Qt.ShiftModifier)
    r, a, b = ed.selection
    assert r is ed.root and b - a == 1


def test_placeholder_is_centred_on_the_equals_sign():
    from PySide6.QtGui import QPainterPath

    from calcforge.calc.ui.layout import Layouter, Style

    lay = Layouter(Style(10))
    ph = lay.placeholder()
    _l, _w, h, bottom = ph.box
    path = QPainterPath()
    path.addText(0, 0, lay.style.font(1.0, op=True), "=")
    b = path.boundingRect()
    assert abs((bottom + h / 2) - (-(b.top() + b.bottom()) / 2)) < 0.3


def test_selection_keys_fuzz(v):
    keys = [Qt.Key_Left, Qt.Key_Right, Qt.Key_Home, Qt.Key_End, Qt.Key_Delete, Qt.Key_Backspace, "7", "x", "+", "/", "^"]
    mods = [Qt.NoModifier, Qt.ShiftModifier, Qt.ControlModifier, Qt.AltModifier,
            Qt.ShiftModifier | Qt.ControlModifier, Qt.ShiftModifier | Qt.AltModifier]
    for seed in range(60):
        rng = random.Random(seed)
        start = rng.choice(["12+345=", "5'kN*2=", "1+2/3", "(a+b)^2"])
        v.type_at(18, 18 + 54 * (seed % 15), start)
        item = v.focused_item
        for _ in range(25):
            k = rng.choice(keys)
            if isinstance(k, str):
                v.press(0, k)
            else:
                v.keys(k, mods=rng.choice(mods))
            if v.focused_item is not item:
                break
            ed = item.editor
            assert 0 <= ed.pos <= len(ed.row.items)
            if ed.selection:
                r, a, b = ed.selection
                assert 0 <= a < b <= len(r.items) and r is ed.row, (seed, ed.root.text())
            assert item._view._row_info(ed.row) is not None
        v.press(Qt.Key_Return)
        v.calc.leave()
        for other in list(v.items.values()):
            other.parentItem().remove_markup(other)


def test_selection_box_is_drawn_while_dragging(v):
    v.type_at(36, 36, "x:1")
    v.press(Qt.Key_Return)
    v.focus_item(None)
    start, end = v.scene_point(10, 10), v.scene_point(150, 80)
    from tests.test_usability import _mouse
    from PySide6.QtCore import QEvent
    QApplication.sendEvent(v.view.viewport(), _mouse(v.view, QEvent.MouseButtonPress, start.x(), start.y()))
    QApplication.sendEvent(v.view.viewport(), _mouse(v.view, QEvent.MouseMove, end.x(), end.y(),
                                                     Qt.NoButton, Qt.LeftButton))
    assert v.view._marquee, "the box is drawn while dragging"
    QApplication.sendEvent(v.view.viewport(), _mouse(v.view, QEvent.MouseButtonRelease, end.x(), end.y()))
    assert not v.view._marquee and v.at_y(36).isSelected()   # the box goes, the selection stays


def test_region_on_second_page_and_drag_across_break(v):
    """CalcForge's pages are fixed (decision 11): a region on page 2 comes
    before nothing on page 1, and dragged onto page 1 it joins page 1."""
    window = v.window
    window.add_page()
    frame2 = window.document.pages[1].frame
    v.calc.place_cross(frame2, QPointF(18 * PT_PER_PX, 27 * PT_PER_PX))
    for ch in "x:1":
        v.press(0, ch)
    item = v.focused_item
    v.press(Qt.Key_Return)
    assert item.parentItem() is frame2 and item.region.y > 1_000_000 - 1
    start = centre(item)
    target = v.frame.mapToScene(QPointF(start.x() - frame2.mapToScene(QPointF(0, 0)).x(), 300))
    v.drag(start, target)
    assert item.parentItem() is v.frame and item.region.y < 1_000_000


def test_shift_wheel_scrolls_sideways(v):
    v.view.set_zoom(4.0)
    v.type_at(18, 18, "w:1")
    v.press(Qt.Key_Return)
    bar = v.view.horizontalScrollBar()
    bar.setValue(bar.minimum())
    before = bar.value()
    ev = QWheelEvent(QPointF(50, 50), QPointF(50, 50), QPoint(0, 0), QPoint(0, -120), Qt.NoButton,
                     Qt.ShiftModifier, Qt.NoScrollPhase, False)
    QApplication.sendEvent(v.view.viewport(), ev)
    assert bar.value() > before


# -- ported in phase 6, when WebSMath's own window went (tests/calc/test_ui.py) ------------
#
# The same keystrokes and checks. WebSMath's right-click menu is CalcForge's
# Equation submenu; its Calculation menu is CalcForge's Calculation › Selection;
# its side panel is the Maths panel.

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


def _equation_menu(v, item):
    menu = v.window.build_context_menu(item, centre(item))
    return next(a.menu() for a in menu.actions() if a.menu() is not None
                and a.text() == "Equation")


def _trigger(menu, *path):
    for title in path[:-1]:
        menu = next(a.menu() for a in menu.actions() if a.text() == title)
    next(a for a in menu.actions() if a.text() == path[-1]).trigger()


def test_copy_paste_regions(v):
    v.type_at(18, 18, "x:5")
    v.press(Qt.Key_Return)
    v.type_at(18, 54, "x=")
    v.press(Qt.Key_Return)
    v.calc.leave()
    v.window.select_all_equations()
    v.window.copy_selection()
    v.window._clipboard = []               # from the clipboard, as another window would
    v.calc.place_cross(v.frame, v.frame.mapFromScene(v.scene_point(18, 180)))
    v.window.paste_items()
    assert len(v.items) == 4
    pasted = sorted((it.region for it in v.items.values()), key=lambda r: r.y)[-1]
    assert display_text(pasted.display) == "5"


def test_copy_paste_inside_equation(v):
    v.type_at(18, 18, "1+2*3")
    ed = v.focused_item.region.editor
    ed.key(" ")  # select 2*3
    v.window.copy_selection()
    ed.set_cursor(ed.root, len(ed.root))
    v.press(0, "+")
    v.window.paste_items()
    assert ed.root.text() == "1+2*3+2*3"


def test_calculation_menu_commands(v):
    v.type_at(18, 18, "1+2*3")
    ed = v.focused_item.region.editor
    ed.key(" ")
    v.window.act_calculate_selection.trigger()
    assert ed.root.text() == "1+6"
    v.type_at(18, 60, "M")
    v.window.act_determinant.trigger()
    assert v.focused_item.region.editor.root.text() == "det(M)"
    v.window.act_invert.trigger()
    assert "^" in v.focused_item.region.editor.root.text()


def test_context_menu_items_match_site(v):
    v.type_at(18, 18, "1/3=")
    item = v.focused_item
    v.calc.leave()
    t = _menu_titles(_equation_menu(v, item))
    top = [x if isinstance(x, str) else x[0] for x in t]
    # SMath Cloud's items for a math region (Cut … Select all are CalcForge's own,
    # on the menu the Equation submenu sits in); Font … Border are decision 20's
    assert top[:top.index("Rounding") + 1] == [
        "Display input data", "-", "Go to definition", "Show description",
        "Disable evaluation", "-", "Ignore units", "-", "Optimization",
        "Decimal places", "Exponential threshold", "Fractions", "Rounding"]
    sub = dict(x for x in t if not isinstance(x, str))
    assert sub["Optimization"] == ["Symbolic", "Numeric", "None"]
    assert sub["Decimal places"][:4] == ["Trailing zeros", "-", "Significant figures mode", "-"]
    assert sub["Decimal places"][4:] == [str(n) if n != 4 else "4 *" for n in range(16)]
    assert sub["Exponential threshold"] == [str(n) if n != 5 else "5 *" for n in range(16)]
    assert sub["Fractions"] == ["Decimal", "Fraction", "Auto", "Default", "-", "Use mixed numbers"]
    assert sub["Rounding"] == ["Half to even", "Away from zero"]


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
def test_context_menu_options_match_site(v, typed, path, shown):
    v.type_at(18, 18, typed)
    item = v.focused_item
    v.calc.leave()
    _trigger(_equation_menu(v, item), *path)
    assert display_text(item.region.display) == shown


def test_context_menu_fractions_and_mixed(v):
    v.type_at(18, 18, "7/3=")
    item = v.focused_item
    v.calc.leave()
    _trigger(_equation_menu(v, item), "Fractions", "Fraction")
    assert display_text(item.region.display) == "7/3"
    _trigger(_equation_menu(v, item), "Fractions", "Use mixed numbers")
    assert display_text(item.region.display) == "2 1/3"
    _trigger(_equation_menu(v, item), "Fractions", "Default")
    assert display_text(item.region.display) == "2.3333"


def test_default_rounding_is_half_to_even_on_the_binary_value(v):
    # observed: 2.00025 = 2.0002 (the double is 2.000249999...), g.e = 9.8066
    v.type_at(18, 18, "2.00025=")
    first = v.focused_item
    v.press(Qt.Key_Return)
    assert display_text(first.region.display) == "2.0002"
    v.type_at(18, 72, "0.125=")
    item = v.focused_item
    v.calc.leave()
    _trigger(_equation_menu(v, item), "Decimal places", "2")
    assert display_text(item.region.display) == "0.12"  # a true tie: to even
    _trigger(_equation_menu(v, item), "Rounding", "Away from zero")
    assert display_text(item.region.display) == "0.13"


def test_display_input_and_disable_evaluation(v):
    v.type_at(18, 18, "x:2")
    v.press(Qt.Key_Return)
    v.type_at(18, 72, "x+3=")
    use = v.focused_item
    v.calc.leave()
    wide = use._view.frame_rect().width()
    _trigger(_equation_menu(v, use), "Display input data")
    assert not use.region.show_input
    assert use._view.frame_rect().width() < wide       # only the result shows
    v.focus_item(use)
    assert use._view.frame_rect().width() >= wide      # the input shows again while editing
    v.calc.leave()
    top = [it for it in v.items.values() if it.region.y == 18][0]
    _trigger(_equation_menu(v, top), "Disable evaluation")
    assert not top.region.enabled
    assert use.region.error is not None and use.region.error.message == "x - not defined."
    v.focus_item(use)
    _trigger(_equation_menu(v, use), "Go to definition")
    assert v.focused_item is use  # x is no longer defined anywhere


def test_calculation_solve(v):
    v.type_at(18, 90, "x^2")
    v.press(Qt.Key_Right)
    v.press(0, "-")
    v.press(0, "9")
    v.focused_item.region.editor.set_cursor(v.focused_item.region.editor.root, 1)  # on x
    v.window.act_solve.trigger()
    below = max(v.items.values(), key=lambda it: it.region.y)
    assert display_text(below.region.display) == "[-3; 3]"


def test_side_panel_symbols_insert(v):
    from calcforge.ui import calcdialogs  # noqa: F401
    v.window.show_panel("dock_maths", True)
    v.type_at(18, 18, "a+")
    sqrt = v.window.maths_panel.section("Arithmetic").button("√")
    QTest.mouseClick(sqrt, Qt.LeftButton)
    assert "√" in v.focused_item.region.editor.root.text()


def test_insert_operator_list_and_formula(v):
    """Ported from test_files_and_operators.py: WebSMath's Insert > Operator."""
    from calcforge.ui import calcdialogs
    from calcforge.ui.calcedit import OPERATORS
    kinds = {g for g, *_ in OPERATORS}
    assert {"Arithmetic", "Boolean", "Calculus", "Matrix and vector", "Definitions"} <= kinds
    v.type_at(18, 18, "2")
    try:
        calcdialogs.ANSWERS["Insert operator"] = "+"
        v.window.insert_operator()
    finally:
        calcdialogs.ANSWERS.clear()
    v.press(0, "3")
    assert v.focused_item.region.editor.root.text() == "2+3"
