"""Launch WebSMath."""
from __future__ import annotations

import sys


def use_light_palette(app) -> None:
    """SMath Studio is always light.  With the system in dark mode Qt would
    give widgets white text on the replica's white panels and lists (the side
    panel symbols disappeared), so the whole app uses a fixed light palette."""
    from PySide6.QtGui import QColor, QPalette

    app.setStyle("Fusion")
    pal = QPalette()
    for role, color in (
        (QPalette.Window, "#f0f0f0"), (QPalette.WindowText, "#000000"), (QPalette.Base, "#ffffff"),
        (QPalette.AlternateBase, "#f7f7f7"), (QPalette.Text, "#000000"), (QPalette.Button, "#f0f0f0"),
        (QPalette.ButtonText, "#000000"), (QPalette.ToolTipBase, "#ffffe1"), (QPalette.ToolTipText, "#000000"),
        (QPalette.Highlight, "#3399ff"), (QPalette.HighlightedText, "#ffffff"), (QPalette.PlaceholderText, "#808080"),
        (QPalette.Link, "#0066cc"), (QPalette.BrightText, "#ff0000"),
    ):
        pal.setColor(role, QColor(color))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor("#a0a0a0"))
    app.setPalette(pal)


def main(argv: list[str] | None = None) -> int:
    from PySide6.QtWidgets import QApplication

    from tests.calc.legacy_ui.mainwindow import MainWindow

    argv = list(sys.argv if argv is None else argv)
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("WebSMath")
    use_light_palette(app)
    win = MainWindow(argv[1] if len(argv) > 1 else None)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
