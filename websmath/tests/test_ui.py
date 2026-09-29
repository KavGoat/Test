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


def test_typing_creates_region_and_evaluates_live(app):
    v = WorksheetView()
    type_at(v, 18, 18, "2+3=")
    item = v.focused_item
    assert item is not None and display_text(item.region.display) == "5"


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
    assert labels[:3] == ["'kpsi", "'ksi", "'psi"]
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
