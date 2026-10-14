"""Application entry point."""
from __future__ import annotations

import os
import sys


def main() -> int:
    os.environ.setdefault("QT_FONT_DPI", "96")

    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler
    from PySide6.QtGui import QFont

    def _message_filter(msg_type, context, message):
        if "Cannot find font directory" in message:
            return
        if "propagateSizeHints" in message:
            return
        if "does not support" in message:
            return
        sys.stderr.write(message + "\n")

    qInstallMessageHandler(_message_filter)

    if sys.platform == "linux" and "QT_QPA_PLATFORM" not in os.environ and not os.environ.get("DISPLAY"):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    app = QApplication(sys.argv)
    from .core.typography import sans_family
    app.setFont(QFont(sans_family(), 9))
    app.setApplicationName("SMath Studio")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("SMath")

    file_path = None
    for arg in sys.argv[1:]:
        if not arg.startswith("-"):
            file_path = arg

    from .ui.mainwindow import MainWindow
    window = MainWindow(file_path=file_path)
    window.show()
    window.raise_()
    window.activateWindow()

    return app.exec()
