"""Application entry point."""
from __future__ import annotations

import os
import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

APP_NAME = "PDF4Py"
ORGANISATION = "PDF4Py"


def build_application(argv: list[str]) -> QApplication:
    QApplication.setApplicationName(APP_NAME)
    QApplication.setOrganizationName(ORGANISATION)
    QApplication.setApplicationDisplayName(APP_NAME)
    application = QApplication(argv)
    font = QFont()
    font.setFamilies(["Segoe UI", "Inter", "DejaVu Sans", "Helvetica Neue", "sans-serif"])
    font.setPointSizeF(9.5)
    application.setFont(font)
    application.setStyle("Fusion")
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
