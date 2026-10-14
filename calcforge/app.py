"""Application entry point."""
from __future__ import annotations

import os
import sys


def main() -> int:
    os.environ.setdefault("QT_FONT_DPI", "96")

    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt, QtMsgType, qInstallMessageHandler
    from PySide6.QtGui import QFont

    _original_handler = None

    def _message_filter(msg_type, context, message):
        if "Cannot find font directory" in message:
            return
        if "propagateSizeHints" in message:
            return
        if _original_handler is not None:
            _original_handler(msg_type, context, message)
        elif msg_type == QtMsgType.QtFatalMsg:
            sys.stderr.write(message + "\n")

    _original_handler = qInstallMessageHandler(_message_filter)

    if "QT_QPA_PLATFORM" not in os.environ and not os.environ.get("DISPLAY"):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    app = QApplication(sys.argv)
    from .core.typography import sans_family
    app.setFont(QFont(sans_family(), 9))
    app.setApplicationName("CalcForge")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("CalcForge")

    file_path = None
    load_sample = False
    for arg in sys.argv[1:]:
        if arg == "--sample":
            load_sample = True
        elif not arg.startswith("-"):
            file_path = arg

    from .ui.mainwindow import MainWindow
    window = MainWindow(file_path=file_path)
    if load_sample:
        from .sample import create_sample_document
        window._document = create_sample_document()
        from .ui.canvas import DocumentScene
        window._scene = DocumentScene(window._document)
        window._canvas.setScene(window._scene)
        window._canvas._scene = window._scene
        window._thumb_panel.update_pages(len(window._document.pages))
        window._recalculate()
        window.setWindowTitle("CalcForge — Sample")
    window.show()

    return app.exec()
