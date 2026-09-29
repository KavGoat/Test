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
