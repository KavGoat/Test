"""Found using the app on 2026-10-10: Properties kept showing a markup
after Escape had let it go (editing it there changed a markup nobody had
picked), and a blank page's thumbnail was white on the white list."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtWidgets import QLabel

from calcforge.items.shapes import RectItem
from tests.test_tables import pump, w  # noqa: F401


def visible_labels(w):
    return [label.text() for label in w.properties_panel.findChildren(QLabel) if label.isVisible()]


def test_properties_let_go_when_escape_does(w):
    box = RectItem()
    box.set_local_rect(QRectF(0, 0, 40, 20))
    w.document.pages[0].frame.add_markup(box, QPointF(100, 100))
    box.setSelected(True)
    w.refresh_selection()
    pump()
    assert "Rectangle" in visible_labels(w)
    w.view.escape_everything()
    pump()
    pump()
    assert "Rectangle" not in visible_labels(w)
    assert any(text.startswith("Nothing selected") for text in visible_labels(w))
    box.setSelected(True)                  # picked some other way than a click
    pump()
    pump()
    assert "Rectangle" in visible_labels(w)


def test_a_blank_pages_thumbnail_has_an_edge(w):
    w.add_page()
    pump()
    entry = w.pages_panel.list.item(1)
    icon = entry.icon()
    image = icon.pixmap(icon.availableSizes()[0]).toImage()
    corner, middle = image.pixelColor(0, image.height() // 2), image.pixelColor(image.width() // 2,
                                                                               image.height() // 2)
    assert middle.name() == "#ffffff" and corner.name() != "#ffffff", "white page, grey edge"


def test_new_markups_are_signed_with_the_persons_name(w, tmp_path, monkeypatch):
    """Answered 2026-10-10: as Bluebeam, a new markup carries the login name
    as its author (Preferences can change it), and the saved PDF says so."""
    import pymupdf

    from calcforge.ui import preferences
    from tests.test_tables import page_to_scene
    from tests.test_usability import drag
    prefs = preferences.current()
    monkeypatch.setattr(prefs, "author", "J. Engineer")
    w.select_tool("rect")
    a, b = page_to_scene(w, 80, 100), page_to_scene(w, 200, 140)
    w.view.centerOn(a)
    drag(w.view, a.x(), a.y(), b.x(), b.y())
    pump()
    (box,) = [i for i in w.document.pages[0].frame.markups() if isinstance(i, RectItem)]
    assert box.author == "J. Engineer"
    path = str(tmp_path / "signed.pdf")
    w.document.path = path
    assert w.save_document()
    with pymupdf.open(path) as pdf:
        authors = [annot.info.get("title") for annot in pdf[0].annots()]
    assert "J. Engineer" in authors


def test_the_author_preference_starts_as_the_login_name():
    from calcforge.ui.preferences import Preferences, login_name
    assert Preferences().author == login_name() != ""


def test_restyling_a_picked_markup_leaves_the_next_one_alone(w):
    """2026-10-10: changing a rectangle's hatch made the next rectangle drawn
    hatched too. Bluebeam keeps a markup's own change to itself; with
    nothing picked, the toolbar is what is drawn next."""
    from tests.test_tables import page_to_scene
    from tests.test_usability import drag

    def draw(y):
        w.select_tool("rect")
        a, b = page_to_scene(w, 80, y), page_to_scene(w, 200, y + 40)
        w.view.centerOn(a)
        drag(w.view, a.x(), a.y(), b.x(), b.y())
        pump()
        return max((i for i in w.document.pages[0].frame.markups() if isinstance(i, RectItem)),
                   key=lambda i: i.pos().y())

    first = draw(100)
    w.view.escape_everything()
    first.setSelected(True)
    w.refresh_selection()
    w.hatch_combo.setCurrentIndex(w.hatch_combo.findData("diagonal") if
                                  w.hatch_combo.findData("diagonal") >= 0 else 2)
    pump()
    assert first.style.hatch, "the picked rectangle is hatched"
    w.view.escape_everything()
    pump()
    assert not w.default_style.hatch
    second = draw(200)
    assert not second.style.hatch, "the next one is drawn as before"
    w.view.escape_everything()
    w.hatch_combo.setCurrentIndex(2)            # nothing picked: this is the default now
    pump()
    third = draw(300)
    assert third.style.hatch == w.hatch_combo.itemData(2)


def test_redo_after_a_page_was_added_and_taken_away(w):
    """Found 2026-10-10: undoing past an added page and redoing again lost
    the edit made after it — the redo wrote into a page frame that had been
    rebuilt. Each step now finds its page again."""
    from calcforge.items.shapes import RectItem as Rect
    w.add_page()
    pump()
    frame = w.document.pages[1].frame
    w.view.begin_snapshot([frame])
    box = Rect()
    box.set_local_rect(QRectF(0, 0, 30, 20))
    frame.add_markup(box, QPointF(100, 100))
    w.view.commit_snapshot("Draw")
    stack = w.undo_stack
    stack.undo()
    stack.undo()
    pump()
    assert len(w.document.pages) == 1
    stack.redo()
    stack.redo()
    pump()
    assert len(w.document.pages) == 2
    assert [type(i).__name__ for i in w.document.pages[1].frame.markups()] == ["RectItem"]


def test_escape_lets_go_of_an_equation_too(w):
    """A click on an equation opens it; Escape closes it and nothing is left
    picked, as for any markup (it used to keep the equation open)."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    import tests.calc.test_calcforge_window as cw
    from calcforge.items.calc import CalcItem
    from tests.test_tables import click
    v = cw.Sheet(w)
    v.type_at(36, 18, "")
    v.keys("x:1")
    v.press(Qt.Key_Return)
    v.calc.leave()
    (eq,) = [i for i in w.view.scene().items() if isinstance(i, CalcItem)]
    click(w, eq.mapToScene(eq.boundingRect().center()))
    pump()
    assert w.view.calc.editing()
    QTest.keyClick(w.view, Qt.Key_Escape)
    pump()
    assert not w.view.calc.editing() and not w.view.scene().selectedItems()


def test_shift_and_a_letter_is_a_shortcut_of_its_own(w):
    """The shortcut box records Shift+M, not the capital M (which plain M
    also matched); Shift+M runs only what is bound to Shift+M."""
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication
    from calcforge.ui.dialogs import ShortcutEdit
    box = ShortcutEdit("")
    QApplication.sendEvent(box, QKeyEvent(QEvent.KeyPress, Qt.Key_M, Qt.ShiftModifier, "M"))
    assert box.text() == "Shift+M"
    QApplication.sendEvent(box, QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.ShiftModifier, " "))
    assert box.text() == "Shift+Space"
    QApplication.sendEvent(box, QKeyEvent(QEvent.KeyPress, Qt.Key_QuoteDbl, Qt.ShiftModifier, '"'))
    assert box.text() == '"', "a character typed with Shift stays the character"
    shortcuts = w.shortcuts
    shortcuts.set_sequence("tool.measure_length", "m")
    shortcuts.set_sequence("tool.rect", "Shift+M")
    assert shortcuts.match_typed("m", Qt.NoModifier).action_id == "tool.measure_length"
    assert shortcuts.match_typed("M", Qt.ShiftModifier).action_id == "tool.rect"
    shortcuts.set_sequence("tool.rect", "R")
    assert shortcuts.match_typed("M", Qt.ShiftModifier) is None, "Shift+M is not M"
    assert shortcuts.match_typed("M", Qt.NoModifier).action_id == "tool.measure_length", \
        "Caps Lock's capital is still M"
    shortcuts.reset()


def test_every_spreadsheet_command_can_be_bound(w):
    """The Spreadsheet group lists the table's commands with Excel's keys,
    each one runs, and a key changed in Keyboard shortcuts is the one that
    works in an open table."""
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from calcforge.ui.shortcuts import SHEET_KEYS
    from calcforge.ui.tableedit import SHEET_COMMANDS
    from tests.test_tables import cell_scene, click, make_table
    assert {name for name, _l, _k in SHEET_KEYS} == set(SHEET_COMMANDS)
    assert w.shortcuts.conflicts() == {}
    table = make_table(w)
    click(w, cell_scene(table, "B2"))
    tables = w.view.tables

    def press(key, mods=Qt.NoModifier, text=""):
        event = QKeyEvent(QEvent.KeyPress, key, mods, text)
        assert tables.key_press(event)
        pump()

    press(Qt.Key_B, Qt.ControlModifier)                     # Excel's Ctrl+B
    assert table.sheet.workbook.style_of(table.sheet, 1, 1).bold
    w.shortcuts.set_sequence("sheet.bold", "Ctrl+Shift+B")
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_B, Qt.ControlModifier, "")
    assert not tables.wants_shortcut(event), "Ctrl+B is free again"
    press(Qt.Key_B, Qt.ControlModifier | Qt.ShiftModifier)
    assert not table.sheet.workbook.style_of(table.sheet, 1, 1).bold
    # a key Excel writes shifted: Ctrl+Shift+9 unhides rows however the keyboard spells it
    tables.select((2, 0))
    press(Qt.Key_9, Qt.ControlModifier)
    assert table.sheet.height(2) == 0
    press(Qt.Key_ParenLeft, Qt.ControlModifier | Qt.ShiftModifier)
    assert table.sheet.height(2) > 0
    w.shortcuts.reset()


def test_slow_downs_are_recorded_with_what_was_running(w, tmp_path, monkeypatch):
    """Help ▸ Record slow-downs: a stall is written down with the code that
    was running, in a file beside the crash log."""
    import time
    from PySide6.QtWidgets import QApplication
    import calcforge.app as app_module
    from calcforge.ui import stallwatch
    monkeypatch.setattr(app_module, "crash_log_path", lambda: str(tmp_path / "crash.log"))
    w.interactive_prompts = False
    w.act_record_slowdowns.setChecked(True)

    def slow_paint():
        time.sleep(0.25)
    end = time.perf_counter() + 0.1
    while time.perf_counter() < end:
        QApplication.processEvents()
    slow_paint()
    end = time.perf_counter() + 0.1
    while time.perf_counter() < end:
        QApplication.processEvents()
    w.act_record_slowdowns.setChecked(False)
    text = (tmp_path / "slowdowns.log").read_text(encoding="utf-8")
    assert "1 stalls" in text or "stalls over" in text
    assert "test_review_findings.py:test_slow_downs" in text or "slow_paint" in text
    assert stallwatch._running is None
