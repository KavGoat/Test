"""Application palette and stylesheet."""
from __future__ import annotations

STYLESHEET = """
* { font-size: 12px; }
QMainWindow, QDialog { background: #eef1f5; }
QToolBar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #fbfcfd, stop:1 #e7ebf1);
    border: 0; border-bottom: 1px solid #d2d8e0; spacing: 2px; padding: 3px 4px;
}
QToolBar QToolButton { border: 1px solid transparent; border-radius: 4px; padding: 3px; }
QToolBar QToolButton:hover { background: #dbe6f5; border-color: #b9cbe6; }
QToolBar QToolButton:checked { background: #c6dbf5; border-color: #7ba6dc; }
QToolBar QLabel { color: #57606e; padding: 0 2px; }
QToolBar::separator { background: #d2d8e0; width: 1px; margin: 4px 4px; }

QMenuBar { background: #f6f8fa; border-bottom: 1px solid #d9dee6; }
QMenuBar::item { padding: 4px 10px; background: transparent; }
QMenuBar::item:selected { background: #d8e5f6; border-radius: 4px; }
QMenu { background: #ffffff; border: 1px solid #cdd4de; padding: 4px; }
QMenu::item { padding: 5px 24px 5px 22px; border-radius: 4px; }
QMenu::item:selected { background: #d8e5f6; }
QMenu::separator { height: 1px; background: #e2e7ee; margin: 4px 6px; }

QDockWidget { titlebar-close-icon: none; font-weight: 600; color: #3d4550; }
QDockWidget::title {
    background: #e3e8ef; padding: 5px 8px; border-bottom: 1px solid #d2d8e0;
}
QGroupBox {
    border: 1px solid #d7dce4; border-radius: 5px; margin-top: 9px;
    background: #fbfcfd; font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; color: #465060; }

QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QAbstractItemView {
    background: #ffffff; border: 1px solid #c6ccd6; border-radius: 4px; padding: 2px 4px;
    selection-background-color: #b9d3f2; selection-color: #10151d;
}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus { border-color: #4a90d9; }
QComboBox::drop-down { border: 0; width: 16px; }

QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #fdfdfe, stop:1 #eef1f5);
    border: 1px solid #c2c9d4; border-radius: 4px; padding: 4px 12px;
}
QPushButton:hover { background: #e6eefa; border-color: #9fbbe0; }
QPushButton:pressed { background: #d6e3f5; }

QTreeWidget, QTableWidget, QListWidget {
    background: #ffffff; border: 1px solid #d5dae2; border-radius: 4px;
    alternate-background-color: #f6f8fb; gridline-color: #e6eaf0;
}
QHeaderView::section {
    background: #eaeef4; border: 0; border-right: 1px solid #dde2ea;
    border-bottom: 1px solid #dde2ea; padding: 4px 6px; font-weight: 600; color: #47505f;
}
QStatusBar { background: #e9edf3; border-top: 1px solid #d5dae2; }
QStatusBar QLabel { color: #4a5261; }
QScrollBar:vertical { background: #f1f4f8; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: #c2cad6; border-radius: 5px; min-height: 26px; }
QScrollBar::handle:vertical:hover { background: #a8b4c4; }
QScrollBar:horizontal { background: #f1f4f8; height: 12px; margin: 0; }
QScrollBar::handle:horizontal { background: #c2cad6; border-radius: 5px; min-width: 26px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QTabBar::tab {
    background: #e3e8ef; border: 1px solid #d2d8e0; border-bottom: 0;
    padding: 5px 12px; border-top-left-radius: 4px; border-top-right-radius: 4px;
}
QTabBar::tab:selected { background: #ffffff; }
QCheckBox, QRadioButton { spacing: 6px; }
QToolTip {
    background: #2b3240; color: #f2f5f9; border: 0; padding: 5px 7px; border-radius: 4px;
}
"""
