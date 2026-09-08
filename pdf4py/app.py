"""Application entry point."""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

APP_NAME = "PDF4Py"
ORGANISATION = "PDF4Py"


def _dark_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.Window, QColor("#1a1b26"))
    p.setColor(QPalette.WindowText, QColor("#c0caf5"))
    p.setColor(QPalette.Base, QColor("#1f2335"))
    p.setColor(QPalette.AlternateBase, QColor("#24283b"))
    p.setColor(QPalette.ToolTipBase, QColor("#1f2335"))
    p.setColor(QPalette.ToolTipText, QColor("#c0caf5"))
    p.setColor(QPalette.Text, QColor("#c0caf5"))
    p.setColor(QPalette.Button, QColor("#1f2335"))
    p.setColor(QPalette.ButtonText, QColor("#c0caf5"))
    p.setColor(QPalette.BrightText, QColor("#f7768e"))
    p.setColor(QPalette.Link, QColor("#7aa2f7"))
    p.setColor(QPalette.Highlight, QColor("#283457"))
    p.setColor(QPalette.HighlightedText, QColor("#c0caf5"))
    p.setColor(QPalette.Disabled, QPalette.Text, QColor("#565f89"))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#565f89"))
    p.setColor(QPalette.Disabled, QPalette.WindowText, QColor("#565f89"))
    return p


def build_application(argv: list[str]) -> QApplication:
    QApplication.setApplicationName(APP_NAME)
    QApplication.setOrganizationName(ORGANISATION)
    QApplication.setApplicationDisplayName(APP_NAME)
    application = QApplication(argv)
    font = QFont()
    font.setFamilies([".AppleSystemUIFont", "SF Pro Text", "Segoe UI",
                      "Inter", "DejaVu Sans", "Helvetica Neue", "sans-serif"])
    font.setPointSizeF(9.5)
    font.setHintingPreference(QFont.PreferNoHinting)
    application.setFont(font)
    application.setStyle("Fusion")
    application.setPalette(_dark_palette())
    return application


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    application = QApplication.instance() or build_application(argv)

    from .ui.mainwindow import MainWindow
    window = MainWindow()
    window.show()

    for argument in argv[1:]:
        if argument.lower().endswith(".pdf") and os.path.exists(argument):
            window.load(argument)
            break

    return application.exec()
