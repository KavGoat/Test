"""importData, strings containing separators, Insert > Operator and Formula."""
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


def test_import_data(tmp_path):
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


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


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
