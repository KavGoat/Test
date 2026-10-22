"""The Thumbnails panel as Revu's (the user, 2026-10-19, with a photo:
"This doesn't look like Bluebeam; also, why is page 3 not on the first
line — it can fit").

The pages fill every row that has room for them, at every panel width,
thumbnail size and display scale, and follow the panel as it is resized,
zoomed and as pages come and go. The header is Revu's: the panel's name is
its menu ("Thumbnails ▾"), its buttons small flat icons straight after it,
and every one of them still works by mouse and by key.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionToolButton, QToolButton

from calcforge.ui import bindable

HERE = os.path.dirname(os.path.abspath(__file__))


def settle(times: int = 6) -> None:
    for _ in range(times):
        QApplication.instance().processEvents()


def with_pages(window, count: int):
    window.show()
    settle()
    while len(window.document.pages) < count:
        window.add_page()
        settle(2)
    window.show_panel("dock_pages", True)
    settle()
    return window.pages_panel.list


def panel_width(window, width: int) -> None:
    window.resizeDocks([window.dock_pages], [width], Qt.Horizontal)
    settle(8)


def first_row(listed) -> int:
    """How many pages share the first row, by where Qt drew them."""
    tops = [listed.visualItemRect(listed.item(row)).top() for row in range(listed.count())]
    return sum(1 for top in tops if top == tops[0])


def check_rows(listed) -> int:
    """The first row holds every page that fits across the strip as shown
    (its scroll bar's width left out only while it is showing), and the
    cells sit inside the strip, side by side, without overlapping."""
    listed.scrollToTop()
    settle(2)
    cell = listed.cell_size()
    room = listed.viewport().width()
    # Qt starts a new row as soon as the next cell would reach the right
    # edge: n cells fit when they leave one pixel spare
    fits = max((room - 1) // cell.width(), 1)
    wanted = min(fits, listed.count())
    got = first_row(listed)
    assert got == wanted, f"{got} on the first row, room for {wanted} ({room} px, " \
                          f"cells {cell.width()} px)"
    boxes = [listed.visualItemRect(listed.item(row)) for row in range(got)]
    for box in boxes:
        assert box.left() >= 0 and box.right() < room, (box, room)
    for left, right in zip(boxes, boxes[1:]):
        assert left.right() < right.left()
    # the scroll bar is there only when the rows are taller than the strip
    rows = -(-listed.count() // got)
    assert listed.verticalScrollBar().isVisible() == (
        rows * cell.height() > listed.viewport().height())
    return got


@pytest.mark.parametrize("scale", [0.6, 1.0, 1.45])
def test_every_row_holds_as_many_pages_as_fit(window, scale):
    listed = with_pages(window, 7)
    window.pages_panel.set_thumbnail_scale(scale)
    settle()
    seen = set()
    for width in range(140, 760, 23):
        panel_width(window, width)
        seen.add(check_rows(listed))
    assert len(seen) >= 3, "several widths, several counts across"


def test_three_pages_share_the_row_they_fit_in(window):
    """The user's photo: three pages and room for three, at 100 %."""
    listed = with_pages(window, 3)
    window.pages_panel.set_thumbnail_scale(1.0)
    cell = listed.cell_size().width()
    for spare in (1, 5, 30):
        panel_width(window, 3 * cell + spare)
        assert listed.viewport().width() >= 3 * cell + 1 or first_row(listed) == 2
        if listed.viewport().width() >= 3 * cell + 1:
            assert first_row(listed) == 3
            assert not listed.verticalScrollBar().isVisible()


def test_the_rows_follow_pages_coming_and_going(window):
    listed = with_pages(window, 2)
    window.pages_panel.set_thumbnail_scale(1.0)
    cell = listed.cell_size().width()
    panel_width(window, 3 * cell + 12)
    assert check_rows(listed) == 2
    window.add_page()
    settle()
    assert check_rows(listed) == 3
    window.add_page()
    settle()
    assert check_rows(listed) == 3 and listed.count() == 4
    window.undo_stack.undo()
    settle()
    window.undo_stack.undo()
    settle()
    assert listed.count() == 2 and check_rows(listed) == 2


def test_ctrl_wheel_zoom_reflows_the_rows(window):
    listed = with_pages(window, 6)
    window.pages_panel.set_thumbnail_scale(1.0)
    panel_width(window, 420)
    before = check_rows(listed)
    centre = QPointF(listed.viewport().rect().center())
    for _ in range(4):
        event = QWheelEvent(centre, QPointF(listed.viewport().mapToGlobal(centre.toPoint())),
                            QPoint(), QPoint(0, 120), Qt.NoButton, Qt.ControlModifier,
                            Qt.NoScrollPhase, False)
        QApplication.sendEvent(listed.viewport(), event)
        settle(2)
    assert listed.scale > 1.5
    after = check_rows(listed)
    assert after < before
    window.pages_panel.set_thumbnail_scale(0.5)
    settle()
    assert check_rows(listed) > before


@pytest.mark.parametrize("scale", ["1.25", "1.5"])
def test_the_rows_fill_at_every_display_scale(scale):
    """At 125 % and 150 % too: Qt reads the display scale once, as the
    application starts, so each runs in a process of its own."""
    code = (
        "import os, sys, tempfile\n"
        "box = tempfile.mkdtemp(prefix='cf-thumbs-')\n"
        "for n in ('XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_CACHE_HOME', 'XDG_STATE_HOME'):\n"
        "    os.environ[n] = os.path.join(box, n.lower()); os.makedirs(os.environ[n])\n"
        "os.environ['CALCFORGE_SETTINGS_FILE'] = os.path.join(box, 's.ini')\n"
        "os.environ['CALCFORGE_MARKFORGE_SETTINGS_FILE'] = os.path.join(box, 'm.ini')\n"
        "from PySide6.QtWidgets import QApplication\n"
        "from calcforge.app import build_application\n"
        "app = QApplication.instance() or build_application([])\n"
        "from calcforge.ui.mainwindow import MainWindow\n"
        "import tests.test_thumbnails_look as t\n"
        "w = MainWindow(); w.confirm_discard = lambda: True; w.interactive_prompts = False\n"
        "w.resize(1280, 860)\n"
        "listed = t.with_pages(w, 5)\n"
        "counts = set()\n"
        "for width in range(150, 700, 41):\n"
        "    t.panel_width(w, width); counts.add(t.check_rows(listed))\n"
        "print('ROWS OK', sorted(counts))\n"
        "w.document.modified = False\n")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR=scale,
               PYTHONPATH=os.path.dirname(HERE))
    done = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                          text=True, timeout=240, cwd=os.path.dirname(HERE))
    assert "ROWS OK" in done.stdout, done.stdout + done.stderr[-3000:]
    assert len(done.stdout.split("ROWS OK")[1].split(",")) >= 3


# ---------------------------------------------------------------------------
# the look
# ---------------------------------------------------------------------------
def ring_is_flat(button) -> bool:
    """No frame drawn round *button*: its outermost pixels are the bar's own
    colour all the way round (a boxed button has an edge there)."""
    picture = button.grab().toImage().convertToFormat(QImage.Format_RGB32)
    ground = QColor(picture.pixel(0, 0))
    width, height = picture.width(), picture.height()
    ring = [(x, 0) for x in range(width)] + [(x, height - 1) for x in range(width)] + \
        [(0, y) for y in range(height)] + [(width - 1, y) for y in range(height)]
    return all(QColor(picture.pixel(x, y)) == ground for x, y in ring)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_header_is_revus_title_menu_and_flat_buttons(window, theme):
    from calcforge.app import current_theme
    from calcforge.theme import tokens
    with_pages(window, 2)
    window.toggle_theme(theme == "dark")
    panel_width(window, 460)
    QTest.mouseMove(window.view.viewport(), QPoint(5, 5))      # nothing hovered
    settle()
    panel = window.pages_panel
    bar = window.dock_pages.titleBarWidget()
    # the title is the menu, and the buttons are on the title's line
    assert panel.title_button.parentWidget() is bar
    assert panel.title_button.text() == "Thumbnails" and panel.title_button.menu()
    assert panel.title_button.popupMode() == QToolButton.InstantPopup
    assert bar.tools_on_the_title_line()
    assert not bar.label.isVisible()
    top = panel.title_button.geometry().center().y()
    for button in panel.page_buttons.values():
        assert abs(button.mapTo(bar, button.rect().center()).y() - top) <= 2
        assert button.autoRaise() and not button.icon().isNull() and not button.text()
        assert ring_is_flat(button), button.objectName()
    # evenly spaced: the same gap between each button and the next
    boxes = [button.geometry() for button in panel.page_buttons.values()]
    gaps = {right.left() - left.right() for left, right in zip(boxes, boxes[1:])}
    assert len(gaps) == 1, gaps
    # the pin, float, roll-up and close: small, flat, the same size
    for button in (bar.collapse, bar.pin, bar.float_button, bar.close_button):
        assert button.autoRaise() and button.size().width() <= 20
        assert ring_is_flat(button)
    assert ring_is_flat(panel.title_button)
    # the bar and the strip are one ground, as Revu's panel is
    ground = QColor(tokens(current_theme())["chrome"])
    strip = panel.list.viewport().grab().toImage()
    assert QColor(strip.pixel(2, strip.height() - 3)) == ground
    window.toggle_theme(False)


def test_a_narrow_panel_puts_the_buttons_under_its_title(window):
    with_pages(window, 1)
    bar = window.dock_pages.titleBarWidget()
    panel_width(window, 200)
    assert not bar.tools_on_the_title_line()
    assert window.pages_panel.header_tools.isVisible()
    for button in window.pages_panel.page_buttons.values():
        right = button.mapTo(bar, button.rect().topRight()).x()
        assert right < bar.width(), "every button whole, none cut off"
    panel_width(window, 520)
    assert bar.tools_on_the_title_line()


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_thumbnails_are_framed_as_revus(window, theme):
    """A thin neutral edge round each page; the page picked out framed in
    Revu's blue; its number centred under it, the scale under that."""
    from calcforge.app import current_theme
    from calcforge.core.document import PageScale
    from calcforge.theme import tokens
    listed = with_pages(window, 3)
    window.toggle_theme(theme == "dark")
    window.document.pages[2].scale = PageScale.from_ratio(50)
    window.pages_panel.rebuild(window.document, 1)
    panel_width(window, 460)
    QTest.mouseMove(window.view.viewport(), QPoint(5, 5))
    settle()
    colours = tokens(current_theme())
    picture = listed.viewport().grab().toImage()
    ratio = picture.devicePixelRatio()

    def at(x, y):
        return QColor(picture.pixel(int(x * ratio), int(y * ratio)))
    picked = listed.picture_rect(1)
    plain = listed.picture_rect(0)
    assert at(picked.center().x(), picked.top() - 2) == QColor(colours["thumb_picked"])
    assert at(plain.center().x(), plain.top() - 2) == QColor(colours["chrome"])
    assert at(plain.center().x(), plain.top()) == QColor(colours["thumb_edge"])
    assert at(plain.left(), plain.center().y()) == QColor(colours["thumb_edge"])
    # the words: centred under the page, the scale on a line of its own
    assert listed.item(2).text() == "3\n1:50"
    assert listed.caption_lines == 2
    box = listed.visualItemRect(listed.item(0))
    assert abs(box.center().x() - plain.center().x()) <= 1
    window.toggle_theme(False)


# ---------------------------------------------------------------------------
# every command still there, by mouse and by key
# ---------------------------------------------------------------------------
def test_thumbnails_menu_opens_from_its_title_with_the_options(window):
    from tests.test_markup_interaction_round6 import watching
    with_pages(window, 2)
    panel_width(window, 460)
    title = window.pages_panel.title_button
    seen = {}

    def read(menu):
        seen["entries"] = [bindable.clean(a.text()) for a in menu.actions() if a.text()]
        seen["ids"] = {bindable.clean(a.text()): a.property(bindable.COMMAND)
                       for a in menu.actions() if a.text()}
        seen["subs"] = {bindable.clean(a.text()): [bindable.clean(b.text())
                                                   for b in a.menu().actions()]
                        for a in menu.actions() if a.menu() is not None}
        menu.close()
    keep = watching(read)
    QTest.mouseClick(title, Qt.LeftButton, Qt.NoModifier, title.rect().center())
    settle()
    keep.stop()
    entries = seen.get("entries")
    assert entries, "the title opened its menu"
    for wanted in ("Insert Pages", "Insert Blank Page", "Insert Spreadsheet Page",
                   "Duplicate Page", "Delete Pages…", "Rotate Pages", "Page Setup…",
                   "Larger Thumbnails", "Smaller Thumbnails"):
        assert wanted in entries, (wanted, entries)
    assert seen["subs"]["Insert Blank Page"] == ["Before…", "After…"]
    assert seen["subs"]["Rotate Pages"] == ["Clockwise", "Anticlockwise"]
    for name, command in seen["ids"].items():
        assert command or name in seen["subs"], f"{name} has no command"


def test_larger_and_smaller_thumbnails_from_the_menu(window):
    with_pages(window, 2)
    listed = window.pages_panel.list
    window.pages_panel.set_thumbnail_scale(1.0)
    menu = window.pages_panel.build_options_menu()
    entry = {bindable.clean(a.text()): a for a in menu.actions()}
    entry["Larger Thumbnails"].trigger()
    settle()
    assert listed.scale == pytest.approx(1.15)
    entry["Smaller Thumbnails"].trigger()
    entry["Smaller Thumbnails"].trigger()
    settle()
    assert listed.scale == pytest.approx(1.0 / 1.15)
    known = {b.action_id for b in window.shortcuts.bindings()}
    assert {"command.thumbnails_larger", "command.thumbnails_smaller"} <= known


def test_every_header_button_works_by_mouse_and_by_key(window, monkeypatch):
    with_pages(window, 2)
    panel_width(window, 460)
    calls = []
    for name in ("quick_add_page", "insert_pdf", "add_page", "insert_sheet_page",
                 "duplicate_page", "delete_page"):
        monkeypatch.setattr(window, name,
                            lambda *args, _n=name, **kwargs: calls.append(_n))
    buttons = window.pages_panel.page_buttons
    wanted = {"quick_add_page": "quick_add_page", "insert_pdf": "insert_pdf",
              "add_page": "add_page",
              "add_sheet_page": "insert_sheet_page", "duplicate_page": "duplicate_page",
              "delete_page": "delete_page"}
    # by mouse: a click on each button's face (not its arrow part)
    for key, button in buttons.items():
        calls.clear()
        QTest.mouseClick(button, Qt.LeftButton, Qt.NoModifier,
                         QPoint(button.iconSize().width() // 2 + 2, button.height() // 2))
        settle(2)
        assert calls == [wanted[key]], (key, calls)
    # the arrow part offers Before / After
    from tests.test_markup_interaction_round6 import watching
    button = buttons["add_page"]
    option = QStyleOptionToolButton()
    button.initStyleOption(option)
    arrow = button.style().subControlRect(QStyle.CC_ToolButton, option,
                                          QStyle.SC_ToolButtonMenu, button)
    seen = {}

    def read(menu):
        seen["entries"] = [a.text() for a in menu.actions() if a.text()]
        menu.close()
    keep = watching(read)
    QTest.mouseClick(button, Qt.LeftButton, Qt.NoModifier, arrow.center())
    settle()
    keep.stop()
    assert seen.get("entries") == ["Before…", "After…"]
    # by key: each button is a command in Keyboard Shortcuts, and the keys
    # that come with them do what the buttons do
    window.commands.tag_buttons()
    known = {b.action_id for b in window.shortcuts.bindings()}
    from calcforge.ui.bindable_list import ALIASES
    for key, button in buttons.items():
        command = button.property(bindable.BUTTON)
        assert command, key
        assert ALIASES.get(command, command) in known, (key, command)
    window.activateWindow()
    window.view.setFocus()
    settle()
    for sequence, called in (("Ctrl+Shift+I", "insert_pdf"), ("Ctrl+Shift+N", "add_page"),
                             ("Ctrl+Shift+D", "delete_page")):
        calls.clear()
        from PySide6.QtGui import QKeySequence
        combo = QKeySequence(sequence)[0]
        QTest.keyClick(window.view, combo.key(), combo.keyboardModifiers())
        settle(2)
        assert called in calls, (sequence, calls)


def test_rename_page_label_edits_over_the_number_not_the_page(window):
    """F2 (Rename Page Label) opens its box where the number is shown,
    under the page's picture rather than over it."""
    listed = with_pages(window, 2)
    panel_width(window, 460)
    listed.setCurrentRow(1)
    listed.setFocus()
    settle()
    QTest.keyClick(listed, Qt.Key_F2)
    settle()
    editor = window.pages_panel.label_editor
    assert editor is not None and editor.isVisible()
    assert editor.geometry().top() >= listed.picture_rect(1).bottom()
    assert editor.geometry().intersects(
        listed.delegate.lines_rect(listed.visualItemRect(listed.item(1))))
    editor.selectAll()
    QTest.keyClicks(editor, "S-201")
    QTest.keyClick(editor, Qt.Key_Return)
    settle()
    assert window.document.pages[1].label == "S-201"
    assert "S-201" in listed.item(1).text()
