"""Every bar button with a menu, drawn, and its arrow found apart from its
icon and words — run in a process of its own, because the display scale
(QT_SCALE_FACTOR) is read once, when the application starts.

    QT_SCALE_FACTOR=1.25 python tests/menu_arrows_probe.py [light|dark] [out.png]

Prints one line per button, "ok …" or "OVERLAP …", and "done" at the end.
tests/test_menu_button_arrows.py runs it at 100 %, 125 % and 150 %.
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SANDBOX = tempfile.mkdtemp(prefix="calcforge-arrows-")
for _name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
    os.environ[_name] = os.path.join(_SANDBOX, _name.lower())
    os.makedirs(os.environ[_name], exist_ok=True)
os.environ["CALCFORGE_SETTINGS_FILE"] = os.path.join(_SANDBOX, "settings.ini")
os.environ["CALCFORGE_MARKFORGE_SETTINGS_FILE"] = os.path.join(_SANDBOX, "markforge.ini")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QRect, QRectF  # noqa: E402
from PySide6.QtGui import QColor, QIcon, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication, QToolBar, QToolButton  # noqa: E402


def pump(times: int = 6) -> None:
    for _ in range(times):
        QApplication.instance().processEvents()


def has_menu(button: QToolButton) -> bool:
    action = button.defaultAction()
    return button.menu() is not None or (action is not None and action.menu() is not None)


def drawn(button: QToolButton) -> QImage:
    return button.grab().toImage().convertToFormat(QImage.Format_ARGB32)


def ink_box(a: QImage, b: QImage) -> QRect:
    """Where two pictures of the same button differ."""
    box = QRect()
    for y in range(min(a.height(), b.height())):
        for x in range(min(a.width(), b.width())):
            if a.pixel(x, y) != b.pixel(x, y):
                box = box.united(QRect(x, y, 1, 1))
    return box


def check(button: QToolButton) -> tuple[bool, str]:
    # held at its size while its face is taken away, so the pictures line up
    size, least, most = button.size(), button.minimumSize(), button.maximumSize()
    button.setFixedSize(size)
    try:
        return _check(button)
    finally:
        button.setMinimumSize(least)
        button.setMaximumSize(most)


def _check(button: QToolButton) -> tuple[bool, str]:
    whole = drawn(button)
    # the arrow: what goes when only the arrow's picture is taken away
    button.setStyleSheet("QToolButton::menu-indicator { image: none; }"
                         "QToolButton::menu-arrow { image: none; }")
    pump(2)
    no_arrow = drawn(button)
    button.setStyleSheet("")
    pump(2)
    # the icon and the words: what goes when they are taken away
    text, picture = button.text(), button.icon()
    action = button.defaultAction()
    if action is not None:
        action_text, action_icon = action.text(), action.icon()
        action.setText(" ")
        action.setIcon(QIcon())
    button.setText(" ")
    button.setIcon(QIcon())
    pump(2)
    no_face = drawn(button)
    if action is not None:
        action.setText(action_text)
        action.setIcon(action_icon)
    button.setText(text)
    button.setIcon(picture)
    pump(2)
    arrow = ink_box(whole, no_arrow)
    face = ink_box(whole, no_face)
    if arrow.isEmpty() and button.popupMode() == QToolButton.MenuButtonPopup:
        # the platform's own split button: its arrow is drawn in the menu part
        from PySide6.QtWidgets import QStyle, QStyleOptionToolButton
        option = QStyleOptionToolButton()
        button.initStyleOption(option)
        part = button.style().subControlRect(QStyle.CC_ToolButton, option,
                                             QStyle.SC_ToolButtonMenu, button)
        ratio = whole.devicePixelRatio() or 1.0
        arrow = QRect(int(part.x() * ratio), int(part.y() * ratio),
                      int(part.width() * ratio), int(part.height() * ratio))
        arrow = arrow.adjusted(1, 1, -1, -1)
    name = button.objectName() or (action.text() if action is not None else text) or "?"
    ratio = whole.devicePixelRatio() or 1.0
    if button.property("menuButton") == "plain":
        # its face is its arrow (▾, »): no second one may be drawn beside it
        if not arrow.isEmpty():
            return False, f"{name}: a second arrow {arrow.getRect()} beside its own"
        return True, f"{name}: its face is its arrow, and no second one"
    if arrow.isEmpty():
        return False, f"{name}: no arrow drawn"
    if face.isEmpty():
        return False, f"{name}: no icon or words drawn"
    if arrow.intersects(face):
        return False, (f"{name}: the arrow {arrow.getRect()} is drawn over the face "
                       f"{face.getRect()} (device px, ratio {ratio:g})")
    return True, f"{name}: arrow {arrow.getRect()} clear of face {face.getRect()}"


def main() -> int:
    from calcforge.app import apply_theme, build_application
    application = QApplication.instance() or build_application([])
    theme = sys.argv[1] if len(sys.argv) > 1 else "light"
    apply_theme(application, theme)
    from calcforge.ui.mainwindow import MainWindow
    window = MainWindow()
    window.confirm_discard = lambda: True
    window.interactive_prompts = False
    window.resize(1280, 860)
    window.show()
    pump()
    if theme == "dark":
        window.toggle_theme(True)
        pump()
    failures = 0
    pictures = []
    checked: set = set()
    names: list = []

    def walk() -> None:
        nonlocal failures
        pump()
        for button in window.findChildren(QToolButton):
            if button.objectName() in ("qt_toolbar_ext_button", "qt_menubar_ext_button") \
                    or not has_menu(button):
                continue
            if not button.isVisible() or id(button) in checked:
                continue
            checked.add(id(button))
            good, said = check(button)
            failures += not good
            print(("ok " if good else "OVERLAP ") + said)
            names.append(said.split(":")[0])
            pictures.append(button.grab())

    # wide enough that no bar puts a button behind its »
    window.resize(2400, 1000)
    pump()
    # every panel shown, the Markups List too
    # every panel brought forward in turn (tabbed panels show one at a time),
    # the Markups List too
    for dock in window.panels:
        window.show_panel(dock.objectName(), True)
        dock.raise_()
        walk()
    if not window.markups_panel.isVisible():
        window.act_markups_list.setChecked(True)
    walk()
    # a markup picked: the Properties panel's Add to Tool Chest ▾
    from PySide6.QtCore import QPointF, QRectF as _Rect
    from calcforge.items.shapes import RectItem
    box = RectItem("rect", _Rect(0, 0, 120, 60))
    window.document.pages[0].frame.add_markup(box, QPointF(300, 400))
    window.select_tool("select")
    box.setSelected(True)
    window.refresh_selection()
    window.show_panel("dock_properties", True)
    walk()
    window.view.scene().clearSelection()
    window.refresh_selection()
    # a table open for its cells: its controls on the Properties bar, and the
    # formula bar's name box
    from tests.test_tables import make_table
    window.view.set_zoom(1.0)
    make_table(window)
    tables = window.view.tables
    if not tables.is_open() and tables.item is not None:
        tables.open(tables.item) if hasattr(tables, "open") else None
    walk()
    # a narrow window: what goes behind the status bar's own menu
    window.resize(800, 600)
    walk()
    # nothing with a menu may go unchecked: any never shown in these states
    # is named, and fails
    for button in window.findChildren(QToolButton):
        if button.objectName() in ("qt_toolbar_ext_button", "qt_menubar_ext_button") \
                or not has_menu(button) or id(button) in checked:
            continue
        failures += 1
        action = button.defaultAction()
        print("UNCHECKED " + (button.objectName() or button.text()
                              or (action.text() if action is not None else "?")))
    if len(sys.argv) > 2 and pictures:
        scale = 4
        width = int(max(p.width() / p.devicePixelRatio() for p in pictures) * scale) + 8
        height = int(sum(p.height() / p.devicePixelRatio() * scale + 8 for p in pictures))
        sheet = QImage(width, height, QImage.Format_ARGB32)
        sheet.fill(QColor("#808080"))
        painter = QPainter(sheet)
        y = 0.0
        for picture in pictures:
            w = picture.width() / picture.devicePixelRatio() * scale
            h = picture.height() / picture.devicePixelRatio() * scale
            painter.drawPixmap(QRectF(4, y + 4, w, h), picture, QRectF(picture.rect()))
            y += h + 8
        painter.end()
        sheet.save(sys.argv[2])
    print(f"done {len(checked)} buttons, {failures} overlapping")
    window.document.modified = False
    return 1 if failures or not checked else 0


if __name__ == "__main__":
    sys.exit(main())
