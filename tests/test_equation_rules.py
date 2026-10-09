"""Conditional formatting of equations (calc/condformat.py): the font size
and background follow the result — per equation, by preset, and for the
whole document by variable name; results with units never match."""
from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

import tests.calc.test_calcforge_window as cw
from calcforge.calc.condformat import DCR_EXAMPLE, look_for
from calcforge.calc.docsheet import sheet_for
from calcforge.items.calc import CalcItem
from calcforge.ui.condformat import apply_document_rules, set_rules

RED, GREEN = "#ffc9c9", "#d3f9d8"


@pytest.fixture
def v(window):
    window.show()
    window.activateWindow()
    return cw.Sheet(window)


def pump():
    QApplication.instance().processEvents()


def equation(v, y_px, keys):
    v.type_at(36, y_px, "")
    v.keys(keys)
    v.press(Qt.Key_Return)
    v.calc.leave()
    pump()


def item(v, text):
    text = text.replace(":", "≔")
    for i in v.window.view.scene().items():
        if isinstance(i, CalcItem) and i.region is not None and i.region.editor.root.text() == text:
            return i
    raise KeyError(text)


def drawn_with(v, it, colour) -> int:
    """How many pixels of the colour the equation is drawn with on screen."""
    from PySide6.QtGui import QColor
    view = v.window.view
    view.set_zoom(4.0)            # text big enough for its ink to be its colour
    view.centerOn(it.mapToScene(it.local_rect().center()))
    pump()
    image = view.viewport().grab().toImage()
    box = view.mapFromScene(it.mapRectToScene(it.local_rect())).boundingRect()
    want = QColor(colour)
    n = 0
    for x in range(max(0, box.left()), min(image.width(), box.right())):
        for y in range(max(0, box.top()), min(image.height(), box.bottom())):
            c = image.pixelColor(x, y)
            if abs(c.red() - want.red()) < 12 and abs(c.green() - want.green()) < 12 and abs(c.blue() - want.blue()) < 12:
                n += 1
    return n


def set_value(v, it, keys):
    """Retype a definition."""
    region = it.region
    v.calc.focus(it)
    v.keys(Qt.Key_End)
    for _ in range(len(region.editor.root.text())):
        v.keys(Qt.Key_Backspace)
    v.keys(keys)
    v.calc.leave()
    pump()


def test_own_rules_colour_the_equation_by_its_result(v):
    equation(v, 18, "DCR:1.2")
    equation(v, 54, "DCR=")
    shown = item(v, "DCR=")
    set_rules(v.window, [shown], DCR_EXAMPLE, "")
    pump()
    assert look_for(shown, v.window.document.settings) ["bg"] == RED
    assert drawn_with(v, shown, RED) > 20
    assert shown.region.bg_color.lower() == "#ffffff", "its own background is kept"
    assert "#ffc9c9" not in str(shown.source()), "the record keeps its own look"
    set_value(v, item(v, "DCR:1.2"), "DCR:0.8")
    shown = item(v, "DCR=")
    assert look_for(shown, v.window.document.settings) ["bg"] == GREEN
    assert drawn_with(v, shown, GREEN) > 20 and drawn_with(v, shown, RED) == 0


def test_a_definition_follows_the_value_it_defines(v):
    equation(v, 18, "a:2")
    equation(v, 54, "DCR:a+0")
    defined = item(v, "DCR:a+0")
    set_rules(v.window, [defined], [{"op": ">", "a": 1.0, "size": 14.0, "bg": RED}], "")
    pump()
    assert defined._view.style.size_pt == 14.0, "laid out at the rule's size"
    assert defined.region.font_size == 10.0
    set_value(v, item(v, "a:2"), "a:0.5")
    defined = item(v, "DCR:a+0")
    assert look_for(defined, v.window.document.settings) == {}
    assert defined._view.style.size_pt == 10.0


def test_presets_and_document_rules_by_name(v):
    apply_document_rules(v.window, {"presets": {"DCR": DCR_EXAMPLE},
                                    "by_name": [["DCR*", "DCR"]]})
    equation(v, 18, "DCR.b:1.5")
    equation(v, 54, "x:1.5")
    pump()
    assert look_for(item(v, "DCR.b:1.5"), v.window.document.settings) ["bg"] == RED
    assert look_for(item(v, "x:1.5"), v.window.document.settings) == {}
    other = item(v, "x:1.5")
    set_rules(v.window, [other], None, "DCR")
    assert look_for(other, v.window.document.settings) ["bg"] == RED
    v.window.undo_stack.undo()
    assert look_for(item(v, "x:1.5"), v.window.document.settings) == {}


def test_results_with_units_never_match(v):
    equation(v, 18, "M:250'kN")
    equation(v, 54, "M=")
    shown = item(v, "M=")
    set_rules(v.window, [shown], [{"op": ">", "a": 1.0, "bg": RED}], "")
    assert look_for(shown, v.window.document.settings) == {}


def test_rules_are_saved_and_copied(v, tmp_path):
    equation(v, 18, "u:3")
    eq = item(v, "u:3")
    set_rules(v.window, [eq], DCR_EXAMPLE, "")
    data = eq.serialize()
    assert data["cond_rules"][0]["bg"] == RED
    copy = eq.clone()
    assert copy.cond_rules == eq.cond_rules
    v.window.document.settings.calc_rules = {"presets": {"P": DCR_EXAMPLE}, "by_name": [["u", "P"]]}
    from calcforge.core.document import DocumentSettings
    again = DocumentSettings.from_dict(v.window.document.settings.to_dict())
    assert again.calc_rules["by_name"] == [["u", "P"]]


def test_the_menu_dialog(v):
    v.window.interactive_prompts = False
    equation(v, 18, "DCR:1.2")
    eq = item(v, "DCR:1.2")
    from calcforge.ui.condformat import open_equation_rules
    open_equation_rules(v.window, [eq])
    dialog = v.window._last_rules_dialog
    dialog.editor.dcr()
    dialog.own.setChecked(True)
    dialog.save_preset("DCR")
    dialog.own.setChecked(True)
    dialog.accept()
    eq = item(v, "DCR:1.2")
    assert eq.cond_rules and v.window.document.settings.calc_rules["presets"]["DCR"][0]["bg"] == RED
    assert look_for(eq, v.window.document.settings) ["bg"] == RED


def test_rules_set_colour_bold_and_underline_too(v):
    equation(v, 18, "DCR:1.3")
    eq = item(v, "DCR:1.3")
    set_rules(v.window, [eq], DCR_EXAMPLE, "")
    pump()
    look = look_for(eq, v.window.document.settings)
    assert look == {"color": "#c92a2a", "bold": True, "bg": RED}
    assert eq._view.style.bold and eq._view.style.color.name() == "#c92a2a"
    assert eq.region.color == "#000000" and not eq.region.bold, "its own look is kept"
    assert drawn_with(v, eq, "#c92a2a") > 5


def test_the_equation_menu_colour_and_bold_show_on_maths(v):
    from calcforge.ui import calcmenu
    equation(v, 18, "y:2")
    eq = item(v, "y:2")
    calcmenu.change(v.window, [eq], "Colour", lambda r: setattr(r, "color", "#1971c2"))
    calcmenu.change(v.window, [eq], "Bold", lambda r: setattr(r, "bold", True))
    eq = item(v, "y:2")
    assert drawn_with(v, eq, "#1971c2") > 5
    assert eq._view.style.bold
