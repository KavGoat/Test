"""Application entry point."""
from __future__ import annotations

import os
import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .theme import DARK, LIGHT, stylesheet
from .settings import APP_NAME, ORGANISATION, app_settings


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
    from .ui.icons import app_icon
    application.setWindowIcon(app_icon())
    apply_theme(application, current_theme())
    return application


def current_theme() -> str:
    """The theme the user last chose."""
    value = app_settings().value("theme", LIGHT)
    return DARK if str(value) == DARK else LIGHT


def apply_theme(application: QApplication, theme: str) -> None:
    from .theme import palette
    from .ui.icons import set_icon_theme

    # Icons are drawn at runtime, so they are re-tinted for the theme rather
    # than being a set of images that only suit one of them.
    set_icon_theme(theme)
    application.setPalette(palette(theme))
    application.setStyleSheet(stylesheet(theme))
    app_settings().setValue("theme", theme)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    application = build_application(argv)

    from .ui.mainwindow import MainWindow
    window = MainWindow()
    window.show()
    window.offer_recovery()

    for argument in argv[1:]:
        if argument.lower().endswith(".pdf") and os.path.exists(argument):
            try:
                window.open_path(argument)
                window.current_index = 0
                window.rebuild_scenes()
                window.apply_document_mode()
                window.view.fit_page()
                window.update_title()
            except Exception as exc:  # noqa: BLE001
                print(f"Could not open {argument}: {exc}", file=sys.stderr)
            break
        if argument in ("--sample", "-s"):
            window.load_sample()
            break

    return application.exec()
