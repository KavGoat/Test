"""SMath's small dialogs opened for real and answered with the mouse and
keyboard (2026-10-10), not through calcdialogs.ANSWERS: Insert Function,
Insert Matrix, Constants, Insert Operator, Insert Unit and Double-check."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QLabel, QListWidget,
                               QSpinBox, QTableWidget, QTreeWidget)

from tests.test_calc_modes import into_calc_mode, typed, win  # noqa: F401
from tests.test_tables import pump


def answer(how):
    """Run ``how(dialog)`` on the modal dialog as soon as it is up."""
    seen = []

    def act():
        d = QApplication.activeModalWidget()
        if d is None:
            QTimer.singleShot(20, act)
            return
        seen.append(d.windowTitle())
        how(d)
    QTimer.singleShot(0, act)
    return seen


def ok(d):
    d.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()


def test_insert_function_from_the_list(win):
    into_calc_mode(win)
    typed(win, "1+")

    def choose(d):
        lst = d.findChild(QListWidget)
        row = next(i for i in range(lst.count()) if lst.item(i).text() == "sqrt")
        lst.setCurrentRow(row)
        assert any(label.text() for label in d.findChildren(QLabel)), "what it does, below the list"
        ok(d)
    seen = answer(choose)
    win.insert_function()
    assert seen == ["Insert function"]
    assert win.view.calc.item.text().startswith("1+√(")      # SMath draws sqrt as √


def test_insert_matrix_of_the_size_asked(win):
    into_calc_mode(win)

    def size(d):
        rows, cols = d.findChildren(QSpinBox)
        assert (rows.value(), cols.value()) == (3, 3), "3 × 3 to begin with"
        rows.setValue(2)
        cols.setValue(4)
        ok(d)
    answer(size)
    win.insert_matrix()
    assert win.view.calc.item.text() == "mat(,,,,,,,,2,4)", "eight empty places, 2 rows, 4 columns"


def test_cancel_inserts_nothing(win):
    into_calc_mode(win)
    typed(win, "7")
    answer(lambda d: d.reject())
    win.insert_function()
    answer(lambda d: d.reject())
    win.insert_matrix()
    assert win.view.calc.item.text() == "7"


def test_a_constant_by_double_click(win):
    into_calc_mode(win)

    def dbl(d):
        t = d.findChild(QTableWidget)
        assert t.rowCount() > 10
        row = next(r for r in range(t.rowCount()) if t.item(r, 1).text() == "π")
        t.cellDoubleClicked.emit(row, 1)
    answer(dbl)
    win.show_constants()
    assert "π" in win.view.calc.item.text()


def test_an_operator_from_the_tree(win):
    into_calc_mode(win)
    typed(win, "a")

    def choose(d):
        tree = d.findChild(QTreeWidget)
        top = tree.topLevelItem(0)
        tree.setCurrentItem(top.child(0))
        ok(d)
    answer(choose)
    before = win.view.calc.item.text()
    win.insert_operator()
    assert win.view.calc.item.text() != before


def test_a_unit_from_the_list(win):
    into_calc_mode(win)
    typed(win, "5")

    def choose(d):
        lst = d.findChild(QListWidget)
        row = next(i for i in range(lst.count()) if lst.item(i).text() == "kN")
        lst.setCurrentRow(row)
        ok(d)
    answer(choose)
    win.insert_unit()
    pump()
    assert "kN" in win.view.calc.item.text()


def test_double_check_shows_its_findings(win):
    into_calc_mode(win)
    typed(win, "2*3=")
    texts = []

    def read(d):
        texts.extend(label.text() for label in d.findChildren(QLabel))
        d.reject()
    answer(read)
    win.double_check()
    assert any("agree" in t for t in texts)


@pytest.fixture(autouse=True)
def _no_stray_dialogs():
    yield
    for w in QApplication.topLevelWidgets():
        if isinstance(w, QDialog) and w.isVisible():
            w.reject()
