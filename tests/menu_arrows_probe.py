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
    name = button.objectName() or (action.text() if action is not None else text) or "?"
    ratio = whole.devicePixelRatio() or 1.0
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
    window.table_controls.show(True)          # a table's controls, on the same bar
    window.style_bar.layout().invalidate()
    pump()
    buttons = []
    for root in list(window.findChildren(QToolBar)) + [window.statusBar()]:
        for button in root.findChildren(QToolButton):
            if button.objectName() == "qt_toolbar_ext_button" or not has_menu(button):
                continue
            if not button.isVisible():
                continue
            buttons.append(button)
    failures = 0
    pictures = []
    for button in buttons:
        good, said = check(button)
        failures += not good
        print(("ok " if good else "OVERLAP ") + said)
        pictures.append(button.grab())
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
    print(f"done {len(buttons)} buttons, {failures} overlapping")
    window.document.modified = False
    return 1 if failures or not buttons else 0


if __name__ == "__main__":
    sys.exit(main())
