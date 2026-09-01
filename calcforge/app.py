"""Application entry point."""
from __future__ import annotations

import os
import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .theme import STYLESHEET

APP_NAME = "CalcForge"
ORGANISATION = "CalcForge"


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
    application.setStyleSheet(STYLESHEET)
    return application


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    application = build_application(argv)

    from .ui.mainwindow import MainWindow
    window = MainWindow()
    window.show()

    for argument in argv[1:]:
        if argument.lower().endswith(".cfx") and os.path.exists(argument):
            from .io import project as project_io
            try:
                project_io.load_document(window.document, argument)
                window.current_index = 0
                window.rebuild_scenes()
                window.view.fit_page()
                window.update_title()
            except Exception as exc:  # noqa: BLE001
                print(f"Could not open {argument}: {exc}", file=sys.stderr)
            break
        if argument in ("--sample", "-s"):
            window.load_sample()
            break

    return application.exec()
