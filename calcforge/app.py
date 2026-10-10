"""Application entry point."""
from __future__ import annotations

import os
import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .theme import DARK, LIGHT, stylesheet
from .settings import APP_NAME, ORGANISATION, app_settings, migrate_from_markforge


def build_application(argv: list[str]) -> QApplication:
    QApplication.setApplicationName(APP_NAME)
    QApplication.setOrganizationName(ORGANISATION)
    QApplication.setApplicationDisplayName(APP_NAME)
    application = QApplication(argv)
    # First start: MarkForge's shortcuts, tool sets, layout, dark mode and
    # markup defaults come across once, before anything reads them.
    migrate_from_markforge()
    from .core.typography import install_substitutions
    install_substitutions()
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


def crash_log_path() -> str:
    from PySide6.QtCore import QStandardPaths
    folder = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation) or \
        os.path.expanduser("~")
    return os.path.join(folder, "crash.log")


def keep_a_crash_log():
    """A record of how each run ended, in crash.log beside CalcForge's other
    files: a Python error with its traceback, a hard crash with where every
    thread was, or "closed normally". A window that just vanished leaves
    nothing behind otherwise (2026-10-10)."""
    import datetime
    import faulthandler
    import traceback
    path = crash_log_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path) and os.path.getsize(path) > 2_000_000:
            os.replace(path, path + ".old")
        log = open(path, "a", encoding="utf-8")
    except OSError:
        return None
    log.write(f"\n--- CalcForge started {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n")
    log.flush()
    faulthandler.enable(log, all_threads=True)
    before = sys.excepthook

    def told(kind, value, trace):
        log.write("".join(traceback.format_exception(kind, value, trace)))
        log.flush()
        before(kind, value, trace)
    sys.excepthook = told
    return log


def main(argv: list[str] | None = None) -> int:
    import multiprocessing
    multiprocessing.freeze_support()
    argv = list(sys.argv if argv is None else argv)
    application = build_application(argv)
    log = keep_a_crash_log()

    from .ui.mainwindow import MainWindow
    window = MainWindow()
    window.show()
    window.offer_recovery()

    for argument in argv[1:]:
        if argument.lower().endswith(".pdf") and os.path.exists(argument):
            try:
                window.open_from_command_line(argument)
            except Exception as exc:  # noqa: BLE001
                print(f"Could not open {argument}: {exc}", file=sys.stderr)
            break

    code = application.exec()
    if log is not None:
        log.write(f"--- closed normally ({code})\n")
        log.close()
    return code
