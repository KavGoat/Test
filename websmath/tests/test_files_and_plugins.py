"""importData / exportData.CSV, strings containing separators, regions this
app cannot display (kept and saved unchanged), Insert > Operator and Formula."""
from __future__ import annotations

import os

import pytest

from websmath.engine.display import display_text
from websmath.io.smfile import dumps, loads
from websmath.worksheet import Worksheet


def _type(ws, x, y, text):
    r = ws.add_region(x, y)
    for k in text:
        r.editor.key(k)
    return r


def test_import_export_round_trip(tmp_path):
    ws = Worksheet()
    ws.filename = str(tmp_path / "sheet.sm")  # relative names are relative to the worksheet
    (tmp_path / "a.csv").write_text("1,2,3\n4.5,5,x\n")
    (tmp_path / "b.txt").write_text("1;2,5\n3;4\n")
    a = _type(ws, 18, 18, 'A:importData("a.csv")')
    b = _type(ws, 18, 60, 'B:importData("b.txt",",")')  # decimal comma
    ws.calculate()
    A = a.defined_vars["A"]
    assert (A.nrows, A.ncols) == (2, 3) and A.get(1, 0).value == 4.5 and A.get(1, 2).text == "x"
    B = b.defined_vars["B"]
    assert [x.value for x in B.items] == [1, 2.5, 3, 4]
    e = _type(ws, 18, 100, 'ok:exportData.CSV(B,"out.csv")')
    ws.calculate()
    assert e.defined_vars["ok"].value == 1
    assert (tmp_path / "out.csv").read_text() == "1,2.5\n3,4\n"


def test_import_missing_file_is_an_error(tmp_path):
    ws = Worksheet()
    ws.filename = str(tmp_path / "sheet.sm")
    r = _type(ws, 18, 18, 'A:importData("missing.csv")')
    ws.calculate()
    assert r.error is not None and "missing.csv" in r.error.message


def test_separator_inside_a_string_is_text():
    ws = Worksheet()
    r = _type(ws, 18, 18, 'concat("a,b";"c")=')
    ws.calculate()
    assert display_text(r.display) == '"a,bc"'


PLUGIN_SHEET = '''<?xml version="1.0" encoding="utf-8"?>
<worksheet xmlns="http://smath.info/schemas/worksheet/1.0"><settings ppi="96"/>
<regions type="content">
<region id="0" left="18" top="18" width="120" height="30" color="#000000"><checkbox checked="true" title="Use SI"><input><e type="operand">flag</e></input></checkbox></region>
<region id="1" left="18" top="90" width="300" height="200" color="#000000"><plot type="3d" render="shaded"><input><e type="operand">x</e></input></plot></region>
<region id="2" left="18" top="300" color="#000000" fontSize="10"><math><input><e type="operand">a</e><e type="operand">2</e><e type="operator" args="2">:</e></input></math></region>
</regions></worksheet>'''


def test_unknown_regions_are_kept_unchanged():
    ws = loads(PLUGIN_SHEET)
    kinds = [(r.kind, r.plugin_name, r.pic_w, r.pic_h) for r in ws.ordered()]
    assert kinds[:2] == [("plugin", "checkbox", 120, 30), ("plugin", "3d plot", 300, 200)]
    out = dumps(ws)
    assert '<checkbox checked="true" title="Use SI">' in out and 'render="shaded"' in out
    ws.ordered()[0].y = 45  # moved: the position follows, the content stays
    moved = dumps(ws)
    assert 'top="45"' in moved and '<checkbox checked="true" title="Use SI">' in moved
    assert dumps(loads(out)) == out


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_placeholder_is_drawn_and_selected_not_typed_into(app):
    from websmath.ui.worksheet_view import WorksheetView

    v = WorksheetView(loads(PLUGIN_SHEET))
    box = next(it for it in v.items.values() if it.region.special == "plugin")
    assert box.frame_rect().width() == 120
    v.focus_item(box)
    assert v.focused_item is None and box in v.selected


def test_insert_operator_list_and_formula(app):
    from websmath.ui.mainwindow import MainWindow

    w = MainWindow()
    kinds = {g for g, *_ in MainWindow.OPERATORS}
    assert {"Arithmetic", "Boolean", "Calculus", "Matrix and vector", "Definitions"} <= kinds
    w.insert_formula()
    assert w.view.focused_item is not None and w.view.focused_item.region.kind == "math"
    w._type("2")
    w._type("+")
    w._type("3")
    assert w.view.focused_item.editor.root.text() == "2+3"
    w.close()
