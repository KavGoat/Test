"""The user manual (the user, 2026-10-19: "a user manual inside the app that
describes the Bluebeam function, SMath functionality and spreadsheet
functionality in three sections … Keep this up to date").

The manual's reference tables are made from the program (tools/manual.py):
when a function, a preference, a default key or a markup tool is added, these
fail until the manual says so. Help ▸ User Manual opens it in a window of its
own, by the mouse and by the keyboard, with its three parts and a search box.
"""
from __future__ import annotations

import importlib.util
import re
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu

ROOT = Path(__file__).resolve().parents[1]
PARTS = ("Part 1 — Markup (Bluebeam Revu-style)",
         "Part 2 — Calculation (SMath-style)",
         "Part 3 — Spreadsheets and tables (Excel-style)")


def _generator():
    spec = importlib.util.spec_from_file_location("calcforge_manual_tool",
                                                  ROOT / "tools" / "manual.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pump(times: int = 3) -> None:
    for _ in range(times):
        QApplication.instance().processEvents()


def _wait(condition, limit: float = 3.0) -> bool:
    give_up = time.monotonic() + limit
    while not condition():
        if time.monotonic() > give_up:
            return False
        pump(1)
        time.sleep(0.005)
    return True


def _manual_shown(window) -> bool:
    manual = getattr(window, "_manual", None)
    return manual is not None and manual.isVisible()


# ---------------------------------------------------------------------------
# the manual says what the program does
# ---------------------------------------------------------------------------
def test_the_manual_is_up_to_date_with_the_program(window):
    """tools/manual.py --check: every SMath function, spreadsheet function,
    Preferences option and default key is in the generated tables, and the
    copy that ships with the app is the manual."""
    problems = _generator().check(window)
    assert not problems, "\n".join(problems)


def test_every_function_preference_and_key_is_in_the_manual(window):
    tool = _generator()
    text = (ROOT / "docs" / "USER_MANUAL.md").read_text(encoding="utf-8")
    for name in tool.sheet_function_names():
        assert f"`{name}(" in text, f"spreadsheet function {name} is not in the manual"
    sections = dict(re.findall(r"<!-- generated:([a-z-]+) -->\n(.*?)<!-- /generated -->",
                               text, re.S))
    smath = sections["smath-functions"]
    for name in tool.smath_function_names():
        assert re.search(rf"`{re.escape(name)}\b", smath), \
            f"SMath function {name} is not in the manual"
    words = tool._data().PREFERENCES
    for field in tool.preference_fields():
        _where, option, _words = words[field.name]
        assert f"**{option}**" in sections["preferences"]
    shortcuts = sections["shortcuts"]
    for _group, label, key, _where in tool.default_shortcuts(window):
        assert f"`{key.replace('|', chr(92) + '|')}`" in shortcuts, \
            f"{label}'s key {key} is not in the shortcut reference"


def test_every_markup_tool_is_described_in_part_1():
    """Each tool by its name in Part 1's own words, not only in the table
    made from the tools."""
    from calcforge.ui.tools import TOOLS
    text = (ROOT / "docs" / "USER_MANUAL.md").read_text(encoding="utf-8")
    part1 = text.split("## Part 1", 1)[1].split("## Part 2", 1)[0]
    words = re.sub(r"<!-- generated:[a-z-]+ -->.*?<!-- /generated -->", "", part1,
                   flags=re.S)
    missing = [tool.label for tool in TOOLS
               if not re.search(rf"(?<![\w-]){re.escape(tool.label)}(?![\w])", words)]
    assert not missing, f"Part 1 does not describe: {', '.join(missing)}"


def test_the_manual_ships_inside_the_package():
    from calcforge.ui import manual
    shipped = manual.MANUAL_PATH
    assert shipped == ROOT / "calcforge" / "data" / "USER_MANUAL.md"
    assert shipped.read_text(encoding="utf-8") == \
        (ROOT / "docs" / "USER_MANUAL.md").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"data/*.md"' in pyproject


# ---------------------------------------------------------------------------
# Help ▸ User Manual
# ---------------------------------------------------------------------------
def _click_menu_entry(window, menu_title: str, entry_text: str) -> list:
    """Click *menu_title* on the menu bar, then *entry_text* in the menu that
    opens, the pointer gliding onto it as a hand does."""
    bar = window.menuBar()
    top = next(a for a in bar.actions() if a.text().replace("&", "") == menu_title)
    seen = []

    def choose():
        menu = QApplication.activePopupWidget()
        if not isinstance(menu, QMenu) or seen:
            return
        entry = next((a for a in menu.actions() if a.text() == entry_text), None)
        if entry is None:
            return
        timer.stop()
        seen.append([a.text() for a in menu.actions() if not a.isSeparator()])
        rect = menu.actionGeometry(entry)
        for k in range(8, -1, -1):
            QTest.mouseMove(menu, QPoint(rect.center().x() - k * 3, rect.center().y()))
        _wait(lambda: menu.activeAction() is entry, 1.0)
        QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier, rect.center())

    timer = QTimer()
    timer.setInterval(5)
    timer.timeout.connect(choose)
    timer.start()
    QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier, bar.actionGeometry(top).center())
    _wait(lambda: bool(seen), 5.0)
    timer.stop()
    pump()
    return seen


def _three_parts(manual) -> None:
    headings = manual.headings()
    for part in PARTS:
        assert part in headings, f"{part} is not in the contents"
    assert manual.contents.topLevelItemCount() == 1      # the manual's title
    tops = [manual.contents.topLevelItem(0).child(k).text(0)
            for k in range(manual.contents.topLevelItem(0).childCount())]
    assert tops == ["Getting started", *PARTS, "Customisation",
                    "Keyboard shortcut reference"]


def test_help_user_manual_opens_by_mouse_with_the_three_parts(window):
    window.show()
    pump()
    seen = _click_menu_entry(window, "Help", "User Manual")
    assert seen and seen[0][0] == "User Manual"            # first on Help, as Revu's Help
    assert _wait(lambda: _manual_shown(window))
    manual = window._manual
    assert manual.windowTitle() == "CalcForge User Manual"
    _three_parts(manual)
    # a heading on the left, clicked, goes there
    item = next(i for i in manual._items if i.text(0) == PARTS[1])
    rect = manual.contents.visualItemRect(item)
    QTest.mouseClick(manual.contents.viewport(), Qt.LeftButton, Qt.NoModifier, rect.center())
    pump()
    cursor = manual.browser.textCursor()
    assert cursor.block().text() == PARTS[1]
    assert manual.browser.verticalScrollBar().value() > 0
    manual.close()


def test_help_user_manual_opens_by_its_key_and_by_the_menu_keys(window):
    window.show()
    window.activateWindow()
    pump()
    assert window.act_user_manual.shortcut().toString() == "Ctrl+F1"
    assert window.shortcuts.default("command.user_manual") == "Ctrl+F1"
    QTest.keyClick(window.view, Qt.Key_F1, Qt.ControlModifier)
    assert _wait(lambda: _manual_shown(window))
    _three_parts(window._manual)
    # the keyboard is the manual's once it is the active window, as it is when
    # a person types in it
    window._manual.activateWindow()
    assert _wait(lambda: QApplication.activeWindow() is window._manual)
    QTest.keyClick(window._manual.search, Qt.Key_Escape)   # Esc closes it
    assert _wait(lambda: not window._manual.isVisible())
    # Alt+H, then Enter on the first entry
    window.activateWindow()
    pump()
    QTest.keyClick(window, Qt.Key_H, Qt.AltModifier)
    assert _wait(lambda: isinstance(QApplication.activePopupWidget(), QMenu))
    menu = QApplication.activePopupWidget()
    entry = window.act_user_manual
    for _ in range(len(menu.actions()) + 2):
        if menu.activeAction() is entry:
            break
        QTest.keyClick(menu, Qt.Key_Down)
    assert menu.activeAction() is entry
    QTest.keyClick(menu, Qt.Key_Return)
    assert _wait(lambda: _manual_shown(window))
    window._manual.close()


def test_search_finds_a_word_typed_into_the_box(window):
    manual = window.show_user_manual()
    pump()
    manual.search.setFocus()
    QTest.keyClicks(manual.search, "interpolating")
    pump()
    found = manual.browser.textCursor()
    assert found.hasSelection() and found.selectedText().lower() == "interpolating"
    first = found.selectionStart()
    count = len(manual.matches())
    assert count >= 2 and manual.found_label.text() == f"1 of {count}"
    QTest.keyClick(manual.search, Qt.Key_Return)            # Enter: the next one
    assert manual.browser.textCursor().selectionStart() > first
    assert manual.found_label.text() == f"2 of {count}"
    QTest.keyClick(manual.search, Qt.Key_Return, Qt.ShiftModifier)   # back again
    assert manual.browser.textCursor().selectionStart() == first
    QTest.mouseClick(manual.next_button, Qt.LeftButton)
    assert manual.found_label.text() == f"2 of {count}"
    QTest.mouseClick(manual.previous_button, Qt.LeftButton)
    assert manual.found_label.text() == f"1 of {count}"
    manual.search.clear()
    QTest.keyClicks(manual.search, "zzqqxx")
    assert manual.found_label.text() == "Not found"
    manual.close()


def test_it_opens_at_a_heading_and_remembers_its_size(window):
    manual = window.show_user_manual("Units in cells")
    pump()
    assert manual.browser.textCursor().block().text() == "Units in cells"
    assert manual.contents.currentItem().text(0) == "Units in cells"
    manual.resize(700, 500)
    pump()
    manual.close()
    window._manual = None                                   # a new window remembers it
    again = window.show_user_manual()
    pump()
    assert (again.width(), again.height()) == (700, 500)
    again.close()


@pytest.mark.parametrize("dark", [True, False])
def test_it_follows_the_theme(window, dark):
    from calcforge.app import current_theme
    from calcforge.theme import DARK
    was = current_theme() == DARK
    window.toggle_theme(dark)
    manual = window.show_user_manual()
    pump()
    page = manual.browser.palette().color(manual.browser.viewport().backgroundRole())
    words = manual.browser.palette().color(manual.browser.foregroundRole())
    assert (page.lightness() < 128) == dark
    assert abs(page.lightness() - words.lightness()) > 100   # readable either way
    manual.close()
    window.toggle_theme(was)
