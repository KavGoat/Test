"""No bar button draws its arrow over its icon or words, at any display scale
(the user, 2026-10-18: Insert Pages' arrow lay over its icon on Windows at
125 %; Sketch to Scale's had the same fault, 2026-10-17).

Each scale runs tests/menu_arrows_probe.py in a process of its own, since
Qt reads QT_SCALE_FACTOR once, as the application starts. The probe walks
every button with a menu in the window — the toolbars, the Properties bar
with a table open, the status bar (narrow, for its »), every panel brought
forward in turn, the Properties panel with a markup picked — and fails any
it never managed to show. It draws each three ways — whole,
without its arrow, without its icon and words — and fails any whose arrow's
ink meets its face's.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.join(HERE, "menu_arrows_probe.py")


@pytest.mark.parametrize("scale", ["1", "1.25", "1.5"])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_every_menu_buttons_arrow_is_clear_of_its_face(scale, theme):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR=scale)
    done = subprocess.run([sys.executable, PROBE, theme], env=env, capture_output=True,
                          text=True, timeout=240)
    lines = [line for line in done.stdout.splitlines()
             if line.startswith(("ok ", "OVERLAP ", "UNCHECKED ", "done"))]
    said = "\n".join(lines) + "\n" + done.stderr[-2000:]
    assert done.returncode == 0, said
    names = [line.split(":")[0][3:] for line in lines if line.startswith("ok ")]
    # Insert Pages (split: icon, then its arrow part), the page layout and
    # Snap on the status bar; a table's Merge, Borders and Rows & Columns
    # (only a menu, its ▾ beside it); Thumbnails' Insert ▾ buttons; the
    # Properties panel's Add to Tool Chest ▾; the formula bar's ▾ and the
    # status bar's », whose face is their arrow
    for wanted in ("Pages", "Continuous", "Snap", "Merge", "Borders", "Rows && Columns",
                   "+", "▦", "addToToolChest", "▾", "statusMore"):
        assert wanted in names, said
    assert not any(line.startswith(("OVERLAP", "UNCHECKED")) for line in lines), said


def test_the_first_row_still_fits_1280_at_125_percent():
    """The split buttons' arrow parts take room: Main, Calculation and
    Measure still share the first row at 1280 px, at 125 % too."""
    code = (
        "import sys; sys.argv = ['x', 'light']\n"
        "import tests.menu_arrows_probe as p\n"
        "from PySide6.QtWidgets import QApplication\n"
        "from calcforge.app import build_application\n"
        "app = QApplication.instance() or build_application([])\n"
        "from calcforge.ui.mainwindow import MainWindow\n"
        "w = MainWindow(); w.resize(1280, 860); w.show(); p.pump(10)\n"
        "bars = {b.objectName(): b for b in w.toolbars}\n"
        "print('ROW', bars['toolbar_main'].y() == bars['toolbar_measure'].y()"
        " == bars['toolbar_calculation'].y())\n"
        "w.document.modified = False\n")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR="1.25",
               PYTHONPATH=os.path.dirname(HERE))
    done = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                          text=True, timeout=240, cwd=os.path.dirname(HERE))
    assert "ROW True" in done.stdout, done.stdout + done.stderr[-2000:]


def test_the_arrow_part_opens_the_menu(window, qapp):
    """Clicked as a person clicks: Insert Pages' arrow part opens its menu,
    and that arrow part is narrow and beside the icon, not over it."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QStyle, QStyleOptionToolButton, QToolButton
    from tests.test_markup_interaction_round6 import watching
    window.show()
    for _ in range(5):
        qapp.processEvents()
    main = next(bar for bar in window.toolbars if bar.objectName() == "toolbar_main")
    (button,) = [b for b in main.findChildren(QToolButton)
                 if b.popupMode() == QToolButton.MenuButtonPopup and b.isVisible()]
    assert button.property("menuButton") == "split"
    option = QStyleOptionToolButton()
    button.initStyleOption(option)
    arrow = button.style().subControlRect(QStyle.CC_ToolButton, option,
                                          QStyle.SC_ToolButtonMenu, button)
    assert 9 <= arrow.width() <= 14 and arrow.right() >= button.width() - 2
    assert arrow.left() >= button.iconSize().width(), "the icon has its own room"
    seen = {}

    def close(menu):
        seen["entries"] = [a.text() for a in menu.actions() if a.text()]
        menu.close()
    keep = watching(close)
    QTest.mouseClick(button, Qt.LeftButton, Qt.NoModifier,
                     QPoint(arrow.center().x(), button.height() // 2))
    for _ in range(5):
        qapp.processEvents()
    keep.stop()
    assert seen.get("entries"), "the arrow part opened the menu"
