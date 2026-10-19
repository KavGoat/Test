"""What writing the user manual found the program doing differently from what
its own tooltips, catalogue and manual said (2026-10-19), each now made to do
what an engineer expects — SMath's, Excel's and Revu's behaviour where they
apply — and driven the way a person uses it."""
from __future__ import annotations

import os

import pytest
from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QDesktopServices, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from calcforge.calc.engine import files
from calcforge.calc.engine.errors import SMathError
from calcforge.calc.engine.values import String
from tests.calc.test_behaviour import error, result, sheet


@pytest.fixture
def data_folder(tmp_path, monkeypatch):
    folder = tmp_path / "user"
    monkeypatch.setattr(files, "data_folder", str(folder))
    return folder


# -- 1. wfile, rfile and dfile, as SMath has them -----------------------------------------
def test_wfile_rfile_and_dfile_keep_a_value_in_the_data_folder(data_folder):
    ws, rs = sheet("F:2.5'kN", 'wfile(F,"load")=', 'rfile("load")=', 'dfile("load")=',
                   'dfile("load")=')
    _, wrote, read, deleted, again = rs
    assert result(wrote) == "1" and error(wrote) is None
    assert result(read) == "2.5 kN"
    assert result(deleted) == "1" and result(again) == "0"
    assert not (data_folder / "load").exists()


def test_a_matrix_with_units_and_text_come_back_exactly(data_folder):
    from calcforge.calc.engine.values import Matrix, Q
    value = Matrix(2, 2, [Q(1.5e-7), Q(2500.0, (1, 1, -2, 0, 0, 0, 0, 0, 0, 0, 0)),
                          String("a b: (c)"), Q(3 + 4j)])
    back = files.read_value_text(files.value_text(value))
    assert back == value


def test_the_files_are_named_only_never_a_path(data_folder):
    for name in ("../secret", "/etc/passwd", "a\\b", "C:x", "", ".."):
        with pytest.raises(SMathError, match="A file name only"):
            files._data_file(String(name))


def test_nothing_is_written_while_the_equation_is_being_typed(data_folder):
    from calcforge.calc.worksheet import Worksheet
    ws = Worksheet()
    r = ws.add_region(18, 9)
    r.editor.type('wfile(7,"live")=')
    ws.calculate_region(r)                      # live, as each key is typed
    assert result(r) == "1" and not (data_folder / "live").exists()
    ws.update_after_edit(r)                     # the equation is left
    assert (data_folder / "live").read_text(encoding="utf-8") == "7"


def test_every_function_offered_is_one_that_works():
    import calcforge.calc.engine.evaluator  # noqa: F401  (registers every function)
    from calcforge.calc.engine import builtins
    from calcforge.calc.engine.catalog import FUNCTIONS
    assert [n for n, *_ in FUNCTIONS if not builtins.known(n)] == []
    # description(): equations have none, so it is not offered — but SMath
    # worksheets that use it still calculate
    from calcforge.calc.engine.catalog import NOT_OFFERED
    from calcforge.calc.ui.suggest import suggestion_list
    from calcforge.ui import calcdialogs
    assert "description" in NOT_OFFERED
    assert "description" not in [label for label, _ in suggestion_list("desc", [])]
    seen = {}
    monkey = calcdialogs.pick
    try:
        calcdialogs.pick = lambda parent, title, entries: seen.setdefault("names", [n for n, _ in entries])
        calcdialogs.function_to_insert(None)
    finally:
        calcdialogs.pick = monkey
    assert "description" not in seen["names"] and "wfile" in seen["names"]
    ws, (r,) = sheet('description("x")=')
    assert error(r) is None


# -- 2. vectorize works element by element -------------------------------------------------
def test_vectorize_applies_the_expression_element_by_element():
    ws, rs = sheet("v:stack(1,2,3)", "v*v=", "vectorize(v*v)=", "f(x):x*x+1",
                   "vectorize(f(v))=", "vectorize(2*v'm)=", "vectorize(v*augment(1,2))=")
    _, dot, squares, _, called, units, mismatch = rs
    assert result(dot) == "14"
    assert result(squares) == "[1; 4; 9]"
    assert result(called) == "[2; 5; 10]"
    assert result(units) == "[2 m; 4 m; 6 m]"
    assert error(mismatch) == "Matrix dimensions do not match."


# -- 3. round's mode -------------------------------------------------------------------------
@pytest.mark.parametrize("typed, shown", [
    ('round(2.5,0,"te")=', "2"), ('round(3.5,0,"te")=', "4"), ('round(2.5,0,"TE")=', "2"),
    ('round(2.5,0,"afz")=', "3"), ('round(-2.5,0,"afz")=', "-3"), ('round(0.125,2,"te")=', "0.12"),
    ('round(2.25\'m,1,"te")=', "2.2 m"),
])
def test_round_takes_smaths_rounding_modes(typed, shown):
    ws, (r,) = sheet(typed)
    assert result(r) == shown


def test_an_unknown_rounding_mode_is_an_error():
    ws, (r,) = sheet('round(2.5,0,"up")=')
    assert "te" in error(r) and "afz" in error(r)


# -- 4. custom units with the apostrophe in equations ----------------------------------------
def test_a_custom_unit_is_written_with_the_apostrophe_in_equations():
    ws, rs = sheet("kips:1000'lbf", "2'kips=", "F:3'kips", "F=", "2'kipz=")
    _, two, _, f, undefined = rs
    assert result(two) == "8.8964 kN" and error(two) is None
    assert result(f) == "13.3447 kN"
    assert error(undefined) == "'kipz - not defined."


def test_a_custom_unit_follows_its_definition():
    ws, rs = sheet("kips:1000'lbf", "2'kips=")
    definition, two = rs
    for _ in range(3):
        definition.editor.key("BACK")
    definition.editor.type("kN")              # kips:1000'kN
    assert definition.editor.root.text() == "kips≔1000'kN"
    ws.update_after_edit(definition)
    assert result(two) == "2 MN"


def test_a_custom_unit_counts_in_double_check():
    from calcforge.calc.engine.verify import double_check
    ws, _ = sheet("kips:1000'lbf", "F:2'kips", "F=")
    report = double_check(ws)
    assert not report.mismatches and report.unchecked == 0 and report.checked >= 1


# -- 5. "]" is SMath's Add line ----------------------------------------------------------------
def test_close_bracket_starts_and_extends_a_program():
    keys = list("f(x):") + ["]"] + list("a:x+1") + ["]"] + list("b:a*2") + ["]"] + list("a+b")
    ws, (f, call) = sheet(keys, "f(3)=")
    assert f.editor.root.text() == "f(x)≔line{a≔x+1;b≔a*2;a+b}"
    assert result(call) == "12"


def test_close_bracket_on_a_selection_makes_it_the_first_line():
    ws, (r,) = sheet(list("y:2") + ["SHIFT+LEFT", "]"] + list("3"))
    assert r.editor.root.text() == "y≔line{2;3}"


# -- the real window ---------------------------------------------------------------------------
@pytest.fixture
def win(window):
    window.show()
    window.activateWindow()
    window.view.setFocus()
    yield window
    from calcforge.ui import calcdialogs
    calcdialogs.ANSWERS.clear()


def _blue_and_red(window, item, path=None):
    """Pixels of SMath's unit blue and error red in the equation as drawn
    (the scene drawn at eight times, the equation's box only)."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QPainter
    QApplication.processEvents()
    box = item.sceneBoundingRect()
    image = QImage(int(box.width() * 8), int(box.height() * 8), QImage.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    window.view.scene().render(painter, QRectF(image.rect()), box)
    painter.end()
    if path:
        image.save(path)
    blue = red = 0
    for x in range(image.width()):
        for y in range(image.height()):
            c = image.pixelColor(x, y)
            if c.blue() > 180 and c.red() < 90 and c.green() < 90:
                blue += 1
            elif c.red() > 180 and c.green() < 90 and c.blue() < 90:
                red += 1
    return blue, red


def test_a_custom_unit_typed_in_the_window_is_blue_and_worked_out(win):
    from calcforge.calc.engine.display import display_text
    from tests.test_calc_panels import an_equation
    an_equation(win, "kips:1000'lbf", 100, 100)
    item = an_equation(win, "2'kips=", 100, 160)
    assert item.region.error is None
    assert display_text(item.region.display) == "8.8964 kN"
    blue, red = _blue_and_red(win, item, os.environ.get("CALCFORGE_SHOT"))
    assert blue > 20 and red == 0


def test_close_bracket_typed_in_the_window_adds_a_line(win):
    from tests.test_calc_modes import into_calc_mode
    into_calc_mode(win, 100, 120)
    for ch in "g(x):":
        QTest.keyClicks(win.view.viewport(), ch)
    QTest.keyClicks(win.view.viewport(), "]")
    for ch in "x+1":
        QTest.keyClicks(win.view.viewport(), ch)
    item = win.view.calc.item
    assert item.region.editor.root.text() == "g(x)≔line{x+1;}"
    # Calculation ▸ Program ▸ Line inside the block: another line, not a new block
    win.act_prog_line.trigger()                  # the empty line already there
    QTest.keyClicks(win.view.viewport(), "2")
    assert win.view.calc.item.region.editor.root.text() == "g(x)≔line{x+1;2}"
    win.act_prog_line.trigger()                  # a third line
    QTest.keyClicks(win.view.viewport(), "3")
    assert win.view.calc.item.region.editor.root.text() == "g(x)≔line{x+1;2;3}"
    assert "] in an equation" in win.act_prog_line.toolTip()
