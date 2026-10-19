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


# -- 6. the tooltips say what happens ------------------------------------------------------------
def test_the_wheel_and_preferences_tooltips_say_what_happens(win):
    from calcforge.ui import dialogs, preferences
    dialog = dialogs.PreferencesDialog(preferences.current(), win)
    tip = dialog.wheel.toolTip()
    assert "Ctrl+wheel scrolls" in tip and "Ctrl+wheel zooms" in tip
    assert "always zoom" not in tip
    dialog.deleteLater()
    assert "blocks" not in win.act_preferences.toolTip()


def test_ctrl_wheel_does_the_other_thing_from_the_setting(win, monkeypatch):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QWheelEvent
    from calcforge.ui import preferences

    def turn(mods):
        before = (win.view.zoom(), win.view.verticalScrollBar().value())
        centre = QPointF(win.view.viewport().rect().center())
        event = QWheelEvent(centre, QPointF(win.view.viewport().mapToGlobal(centre.toPoint())),
                            QPoint(0, 0), QPoint(0, -120), Qt.NoButton, mods, Qt.NoScrollPhase,
                            False)
        QApplication.sendEvent(win.view.viewport(), event)
        win.view.finish_scrolling()
        QApplication.processEvents()
        return before != (win.view.zoom(), win.view.verticalScrollBar().value()), \
            abs(win.view.zoom() - before[0]) > 1e-9

    win.view.set_zoom(2.0)
    current = preferences.current()
    monkeypatch.setattr(current, "wheel", preferences.WHEEL_SCROLL)
    moved, zoomed = turn(Qt.ControlModifier)
    assert zoomed                              # wheel scrolls: Ctrl+wheel zooms
    win.view.set_zoom(2.0)
    monkeypatch.setattr(current, "wheel", preferences.WHEEL_ZOOM)
    moved, zoomed = turn(Qt.ControlModifier)
    assert moved and not zoomed                # wheel zooms: Ctrl+wheel scrolls


# -- 7. the Count tool, as Revu's: it does not ask --------------------------------------------
def test_the_count_tool_counts_as_count_until_a_subject_is_set(win):
    from calcforge.items.measure import CountItem
    from calcforge.ui.tools import TOOLS
    from tests.test_usability import click
    (tool,) = [t for t in TOOLS if t.key == "count"]
    assert "Count subject" in tool.hint
    win.select_tool("count")
    p = win.document.pages[0].frame.mapToScene(QPointF(200, 200))
    win.view.centerOn(p)
    click(win.view, p.x(), p.y())
    assert QApplication.activeModalWidget() is None          # nothing asked
    counts = [i for i in win.view.scene().items() if isinstance(i, CountItem)]
    assert len(counts) == 1 and counts[0].subject == "Count"


# -- 8. a saved document's recovery copy is offered back --------------------------------------
def _press_in_message_box(text, seen):
    def press():
        box = QApplication.activeModalWidget()
        if not isinstance(box, QMessageBox):
            QTimer.singleShot(20, press)
            return
        seen.append(box.text())
        (button,) = [b for b in box.buttons() if b.text() == text]
        QTest.mouseClick(button, Qt.LeftButton)
    QTimer.singleShot(0, press)


def _saved_with_newer_recovery(win, tmp_path):
    from tests.test_calc_panels import an_equation
    path = str(tmp_path / "beam.pdf")
    win.document.path = path
    assert win.save_document()
    an_equation(win, "x:5", 100, 100)            # changed after the save
    recovery = win.write_autosave()
    assert recovery == path + ".autosave"
    later = os.path.getmtime(path) + 60
    os.utime(recovery, (later, later))
    win.document.modified = False
    win.undo_stack.setClean()
    win.new_document(confirm=False)
    return path, recovery


def _equation_texts(win):
    from calcforge.items.calc import CalcItem
    return [i.region.editor.root.text() for i in win.view.scene().items()
            if isinstance(i, CalcItem)]


def test_opening_a_document_with_a_newer_recovery_copy_offers_it(win, tmp_path):
    path, recovery = _saved_with_newer_recovery(win, tmp_path)
    win.interactive_prompts = True
    seen = []
    _press_in_message_box("Open Recovered", seen)
    win._open_chosen(path)
    assert seen and "A recovered version of beam.pdf exists from" in seen[0]
    assert "x≔5" in _equation_texts(win)
    assert win.document.path == path and win.document.modified
    assert win.save_document()
    assert not os.path.exists(recovery)          # saved: the copy has done its work


def test_open_saved_keeps_the_copy_and_discard_deletes_it(win, tmp_path):
    path, recovery = _saved_with_newer_recovery(win, tmp_path)
    win.interactive_prompts = True
    _press_in_message_box("Open Saved", [])
    win._open_chosen(path)
    assert "x≔5" not in _equation_texts(win) and os.path.exists(recovery)
    win.new_document(confirm=False)
    _press_in_message_box("Discard Recovered", [])
    win._open_chosen(path)
    assert "x≔5" not in _equation_texts(win) and not os.path.exists(recovery)


def test_an_older_recovery_copy_is_not_offered(win, tmp_path):
    path, recovery = _saved_with_newer_recovery(win, tmp_path)
    earlier = os.path.getmtime(path) - 60
    os.utime(recovery, (earlier, earlier))
    win.interactive_prompts = True
    win._open_chosen(path)                       # a question would block here
    assert "x≔5" not in _equation_texts(win)


# -- 9. HYPERLINK cells are links -----------------------------------------------------------------
def test_ctrl_click_on_a_hyperlink_cell_opens_it(win, monkeypatch):
    from tests.test_tables import cell_scene, click, enter, make_table, pump, type_text
    from tests.test_usability import hover
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl",
                        staticmethod(lambda url: opened.append(url.toString()) or True))
    win.view.set_zoom(1.0)
    table = make_table(win)
    type_text(win, '=HYPERLINK("https://example.com/eurocode","EN 1990")')
    enter(win)
    type_text(win, f'=HYPERLINK("#{table.name}!C3","go")')
    enter(win)
    assert table.sheet.value(0, 0) == "EN 1990"
    a1 = cell_scene(table, "A1")
    hover(win.view, a1.x(), a1.y())
    pump()
    assert win.view.viewport().cursor().shape() == Qt.PointingHandCursor
    click(win, a1)                               # a plain click selects the cell
    assert opened == [] and win.view.tables.active == (0, 0)
    click(win, a1, Qt.ControlModifier)
    assert opened == ["https://example.com/eurocode"]
    click(win, cell_scene(table, "A2"), Qt.ControlModifier)
    assert win.view.tables.active == (2, 2) and opened == ["https://example.com/eurocode"]
    # right-click ▸ Open Hyperlink, greyed on a cell without one
    win.view.tables.select((0, 0))
    menu = win.view.tables.cell_menu()
    (follow,) = [a for a in menu.actions() if a.text() == "Open Hyperlink"]
    assert follow.isEnabled()
    follow.trigger()
    assert opened == ["https://example.com/eurocode"] * 2
    win.view.tables.select((3, 2))
    menu = win.view.tables.cell_menu()
    (follow,) = [a for a in menu.actions() if a.text() == "Open Hyperlink"]
    assert not follow.isEnabled()


def test_a_link_to_a_file_is_not_opened_without_asking(win, monkeypatch):
    from tests.test_tables import cell_scene, click, enter, make_table, type_text
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl",
                        staticmethod(lambda url: opened.append(url.toString()) or True))
    table = make_table(win)
    type_text(win, '=HYPERLINK("C:/tools/run.exe","run")')
    enter(win)
    win.interactive_prompts = False              # nobody there to say yes
    click(win, cell_scene(table, "A1"), Qt.ControlModifier)
    assert opened == []
